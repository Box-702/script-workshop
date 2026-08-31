# =====================================================================
# generation.py —— 剧本生成流水线
#
# 把一个项目从「原始文本」生成「结构化剧本」。这里采用『线性』的多步
# 结构化生成（而非有状态的 Agent 图），以和后面的「改编 Agent」
# 形成明显区分：
#   - 生成：确定性编排的多阶段结构化抽取（故事圣经 -> 场景/节拍）；
#   - 改编：有状态、可工具调用、可人机协同的 LangGraph Agent。
#
# 无模型（未配置 key）或任一阶段失败时，回退为 make_source_script
# 产出的最小有效剧本，从而保证「导入 -> 生成」链路始终能跑通、可演示。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from .config import Settings
from .domain import (
    Adaptation,
    Character,
    Location,
    Scene,
    Script,
    ScriptBeat,
    Source,
    normalize_id,
)
from .llm import LLM
from .patch import make_source_script
from .profiles import profile_for, profile_type
from .vector import chunk_text

log = logging.getLogger(__name__)


class _CharacterIn(BaseModel):
    id: str
    name: str
    role: str | None = None
    goal: str | None = None
    motivation: str | None = None


class _LocationIn(BaseModel):
    id: str
    name: str
    description: str | None = None


class Bible(BaseModel):
    title: str = "未命名故事"
    logline: str = "主角面对核心冲突。"
    themes: list[str] = Field(default_factory=list)
    characters: list[_CharacterIn] = Field(default_factory=list)
    locations: list[_LocationIn] = Field(default_factory=list)


class _SceneIn(BaseModel):
    id: str
    title: str
    chapter_refs: list[str] = Field(default_factory=list)
    location_id: str = "loc_main"
    characters: list[str] = Field(default_factory=list)
    purpose: str = "推进情节。"
    conflict: str = "角色面对压力。"
    entry_state: str | None = None
    exit_state: str | None = None
    beats: list[dict[str, Any]] = Field(default_factory=list)


class ScenePlan(BaseModel):
    scenes: list[_SceneIn] = Field(default_factory=list)


def _stage_bible(llm: LLM, settings: Settings, *, title: str, excerpts: list[str], prof: dict[str, Any], language: str) -> Bible:
    """第一阶段：生成故事圣经（标题、梗概、主题、人物、地点）。"""
    from .profiles import profile_prompt

    text = "\n\n".join(excerpts[:6])
    prompt = (
        f"请基于下面的原著片段生成剧本故事圣经。标题：{title}\n"
        f"改编类型 profile：\n{profile_prompt(prof, language=language)}\n\n"
        f"原著片段：\n{text[:4000]}"
    )
    return llm.structured(Bible).invoke(
        [{"role": "system", "content": llm.system_prompt()}, {"role": "user", "content": prompt}]
    )


def _stage_scenes(llm: LLM, settings: Settings, *, bible: Bible, excerpts: list[str], prof: dict[str, Any], language: str, chunks: list[str]) -> ScenePlan:
    """第二阶段：生成场景与节拍流（动作 / 对白 / cue）。"""
    from .profiles import profile_prompt

    characters = [c.model_dump() for c in bible.characters]
    locations = [l.model_dump() for l in bible.locations]
    prompt = (
        f"请为剧本规划场景，并为每个场景生成按阅读顺序混排的 beats 节拍流。\n"
        f"改编类型 profile：\n{profile_prompt(prof, language=language)}\n\n"
        f"人物：{characters}\n地点：{locations}\n"
        f"故事圣经：{bible.model_dump_json()}\n\n"
        f"原著片段：\n{'\\n'.join(excerpts[:8])[:4000]}"
    )
    return llm.structured(ScenePlan).invoke(
        [{"role": "system", "content": llm.system_prompt()}, {"role": "user", "content": prompt}]
    )


def generate_script(
    llm: LLM,
    settings: Settings,
    *,
    title: str,
    raw_text: str,
    adaptation_type: str,
    language: str,
) -> tuple[Script, dict[str, Any]]:
    """生成剧本。返回 (Script, artifacts)。失败时回退最小剧本。"""
    prof = profile_for(adaptation_type)
    artifacts: dict[str, Any] = {"mode": "local-fallback"}

    if llm.available:
        try:
            chunks = chunk_text(raw_text or "", chunk_size=1200, overlap=160)
            if not chunks:
                chunks = [raw_text or ""]
            excerpts = chunks[:12]
            bible = _stage_bible(llm, settings, title=title, excerpts=excerpts, prof=prof, language=language)
            plan = _stage_scenes(llm, settings, bible=bible, excerpts=excerpts, prof=prof, language=language, chunks=chunks)

            # 规整到领域模型。
            used_chars: set[str] = set()
            chars: list[Character] = []
            for i, c in enumerate(bible.characters):
                cid = normalize_id(c.id, "char", fallback=f"char_{i + 1:03d}")
                if cid in used_chars:
                    cid = f"{cid}_{i + 1}"[: 40]
                used_chars.add(cid)
                chars.append(Character(id=cid, name=c.name, role=c.role, goal=c.goal, motivation=c.motivation))
            if not chars:
                chars = [Character(id="char_protagonist", name="主角", role="protagonist")]

            used_locs: set[str] = set()
            locs: list[Location] = []
            for i, l in enumerate(bible.locations):
                lid = normalize_id(l.id, "loc", fallback=f"loc_{i + 1:03d}")
                if lid in used_locs:
                    lid = f"{lid}_{i + 1}"[: 40]
                used_locs.add(lid)
                locs.append(Location(id=lid, name=l.name, description=l.description))
            if not locs:
                locs = [Location(id="loc_main", name="主要场景")]

            char_list = [c.id for c in chars]
            loc_id = locs[0].id
            scenes: list[Scene] = []
            for i, s in enumerate(plan.scenes or []):
                sid = normalize_id(s.id, "scene", fallback=f"scene_{i + 1:03d}")
                # 场景内人物规整到全局人物 id。
                sc_chars = [normalize_id(x, "char", fallback=x) for x in s.characters]
                sc_chars = [c for c in sc_chars if c in set(char_list)] or [char_list[0]]
                beats: list[ScriptBeat] = []
                for bi, b in enumerate(s.beats or []):
                    kind = str(b.get("type") or "action")
                    if kind not in {"action", "dialogue", "cue"}:
                        kind = "dialogue" if b.get("speaker") or b.get("line") else "action"
                    bid = normalize_id(b.get("id"), "beat", fallback=f"beat_{bi + 1:03d}")
                    if kind == "dialogue":
                        speaker = normalize_id(b.get("speaker"), "char", fallback=sc_chars[0])
                        line = str(b.get("line") or b.get("text") or "").strip()
                        if not line:
                            continue
                        beats.append(ScriptBeat(id=bid, type="dialogue", speaker=speaker, line=line))
                    else:
                        text = str(b.get("text") or b.get("line") or "").strip()
                        if not text:
                            continue
                        beats.append(ScriptBeat(id=bid, type=kind, text=text))  # type: ignore[arg-type]
                scenes.append(
                    Scene(
                        id=sid,
                        title=s.title or f"第 {i + 1} 场",
                        chapter_refs=s.chapter_refs or ["ch_001"],
                        location_id=normalize_id(s.location_id, "loc", fallback=loc_id),
                        time=s.time if hasattr(s, "time") else None,
                        characters=sc_chars,
                        purpose=s.purpose,
                        conflict=s.conflict,
                        entry_state=s.entry_state,
                        exit_state=s.exit_state,
                        action=[b.text for b in beats if b.type == "action" and b.text],
                        dialogue=[],
                        beats=beats,
                    )
                )
            if not scenes:
                raise ValueError("场景生成为空")

            script = Script(
                title=bible.title or title,
                version="1.0",
                language=language,
                adaptation=Adaptation(type=profile_type(adaptation_type), target_format=prof["target_format"], tone=prof["tone"]),
                source=Source(chapter_count=len(chunks), chapter_ids=[f"ch_{i + 1:03d}" for i in range(len(chunks))]),
                logline=bible.logline,
                themes=bible.themes,
                characters=chars,
                locations=locs,
                scenes=scenes,
            )
            artifacts = {"mode": "llm", "bible": bible.model_dump(), "scene_count": len(scenes)}
            return script, artifacts
        except Exception as e:  # noqa: BLE001
            log.warning("LLM 生成失败，回退本地规则剧本：%s", e)
            artifacts = {"mode": "local-fallback", "error": str(e)}

    script = make_source_script(title, raw_text, adaptation_type=adaptation_type, language=language)
    return script, artifacts
