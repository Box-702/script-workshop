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
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

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


class _BeatIn(BaseModel):
    """容错节拍：兼容模型常用的 action/dialogue 键与 text/line 键。"""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    type: str = "action"
    text: str | None = None
    line: str | None = None
    action: str | None = None
    dialogue: str | None = None
    speaker: str | None = None
    emotion: str | None = None
    subtext: str | None = None


class _SceneIn(BaseModel):
    """容错场景：兼容 scene_id/scene_title/location 与 id/title/location_id。"""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    scene_id: str | None = None
    title: str | None = None
    scene_title: str | None = None
    chapter_refs: list[str] = Field(default_factory=list)
    location_id: str | None = None
    location: str | None = None
    characters: list[str] = Field(default_factory=list)
    purpose: str = "推进情节。"
    conflict: str = "角色面对压力。"
    entry_state: str | None = None
    exit_state: str | None = None
    time: str | None = None
    beats: list[_BeatIn] = Field(default_factory=list)


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


def _norm_beat_id(value: object, index: int, used: set[str]) -> str:
    """把模型给的节拍 id 规整为 ``beat_数字``（非纯数字则回退序号，并保证唯一）。"""
    raw = str(value or "").strip()
    candidate = normalize_id(raw, "beat", fallback=str(index))
    if not re.fullmatch(r"beat_[0-9]{3,}", candidate):
        candidate = f"beat_{index:03d}"
    n = index
    while candidate in used:
        n += 1
        candidate = f"beat_{n:03d}"
    used.add(candidate)
    return candidate


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
            if not plan.scenes:
                # 思考模型输出不稳定：场景为空时重试一次。
                plan = _stage_scenes(llm, settings, bible=bible, excerpts=excerpts, prof=prof, language=language, chunks=chunks)
            if not plan.scenes:
                raise ValueError("场景生成为空")

            # ---- 人物：Bible 中若没有，从节拍说话人自动补全 ----
            used_chars: set[str] = set()
            chars: list[Character] = []
            for i, c in enumerate(bible.characters):
                cid = normalize_id(c.id, "char", fallback=f"char_{i + 1:03d}")
                if cid in used_chars:
                    cid = f"{cid}_{i + 1}"[: 40]
                used_chars.add(cid)
                chars.append(Character(id=cid, name=c.name, role=c.role, goal=c.goal, motivation=c.motivation))
            name_to_id = {c.name: c.id for c in chars}
            extra_speakers: list[str] = []
            for sc in plan.scenes:
                for b in sc.beats or []:
                    spk = str(b.speaker or "").strip()
                    if spk and spk not in name_to_id and spk not in extra_speakers:
                        extra_speakers.append(spk)
            for spk in extra_speakers:
                cid = normalize_id(spk, "char", fallback=f"char_{len(chars) + 1:03d}")
                # 保证与已有角色 id 不冲突（模型常把同一人写成不同名字）。
                if cid in used_chars:
                    suffix = 1
                    while f"{cid}_{suffix}" in used_chars:
                        suffix += 1
                    cid = f"{cid}_{suffix}"
                used_chars.add(cid)
                chars.append(Character(id=cid, name=spk, role="supporting"))
                name_to_id[spk] = cid
            if not chars:
                chars = [Character(id="char_protagonist", name="主角", role="protagonist")]

            # ---- 地点 ----
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

            char_id_set = {c.id for c in chars}
            char_list = [c.id for c in chars]
            loc_id = locs[0].id
            scenes: list[Scene] = []
            for i, s in enumerate(plan.scenes or []):
                sid = normalize_id(s.scene_id or s.id, "scene", fallback=f"scene_{i + 1:03d}")
                s_title = s.scene_title or s.title
                s_loc = s.location_id or s.location
                # 场景人物：显式人物（名字/ id 均可）+ 该场景节拍的说话人。
                sc_chars = [name_to_id.get(x, normalize_id(x, "char", fallback=x)) for x in s.characters]
                sc_chars = [c for c in sc_chars if c in char_id_set]
                for b in s.beats or []:
                    spk = str(b.speaker or "").strip()
                    sid2 = name_to_id.get(spk)
                    if sid2 and sid2 not in sc_chars:
                        sc_chars.append(sid2)
                sc_chars = sc_chars or [char_list[0]]
                beats: list[ScriptBeat] = []
                used_beat_ids: set[str] = set()
                for bi, b in enumerate(s.beats or []):
                    kind = str(b.type or "action")
                    if kind not in {"action", "dialogue", "cue"}:
                        kind = "dialogue" if (b.speaker or b.line or b.dialogue) else "action"
                    bid = _norm_beat_id(b.id, bi + 1, used_beat_ids)
                    if kind == "dialogue":
                        speaker = name_to_id.get(str(b.speaker or "").strip(), sc_chars[0])
                        line = str(b.line or b.dialogue or b.text or "").strip()
                        if not line:
                            continue
                        beats.append(ScriptBeat(id=bid, type="dialogue", speaker=speaker, line=line))
                    else:
                        text = str(b.text or b.action or b.line or "").strip()
                        if not text:
                            continue
                        beats.append(ScriptBeat(id=bid, type=kind, text=text))  # type: ignore[arg-type]
                scenes.append(
                    Scene(
                        id=sid,
                        title=s_title or f"第 {i + 1} 场",
                        chapter_refs=s.chapter_refs or ["ch_001"],
                        location_id=normalize_id(s_loc, "loc", fallback=loc_id),
                        time=s.time,
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
