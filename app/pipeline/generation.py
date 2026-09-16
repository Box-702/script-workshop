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

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..config import Settings
from ..domain import (
    Adaptation,
    Character,
    Location,
    Scene,
    Script,
    ScriptBeat,
    Source,
    normalize_id,
)
from ..llm import LLM
from .patch import make_source_script
from .profiles import profile_for, profile_type
from .chunking import chunk_text

log = logging.getLogger(__name__)


class _CharacterIn(BaseModel):
    """容错人物：id 可缺省（模型常只给 name），后续按序号补齐。"""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str = "未命名人物"
    role: str | None = None
    goal: str | None = None
    motivation: str | None = None
    description: str | None = None
    arc: str | None = None


class _LocationIn(BaseModel):
    """容错地点：id 可缺省。"""

    model_config = ConfigDict(extra="ignore")

    id: str | None = None
    name: str = "未命名地点"
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

    @field_validator("text", "line", "action", "dialogue", "subtext", mode="before")
    @classmethod
    def _unwrap_text(cls, v: object) -> object:
        # 模型偶尔把 dialogue 输出成 {"line": ...} / {"text": ...} 对象，解包成字符串。
        if isinstance(v, dict):
            for key in ("line", "text", "dialogue", "action", "value"):
                if isinstance(v.get(key), str):
                    return v[key]
            return None
        return v

    @field_validator("speaker", mode="before")
    @classmethod
    def _unwrap_speaker(cls, v: object) -> object:
        if isinstance(v, dict):
            for key in ("id", "name", "speaker"):
                if isinstance(v.get(key), str):
                    return v[key]
            return None
        return v


class _SceneIn(BaseModel):
    """容错场景：兼容 scene_id/scene_title/location 与 id/title/location_id。

    同时兼容模型两种常见输出形态：
      - beats：标准的节拍流数组；
      - action / dialogue：旧式兼容层（动作字符串数组 + 对白对象数组），
        当 beats 为空时由生成器合成节拍，避免整场戏空掉。
    """

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
    time_of_day: str | None = None
    beats: list[_BeatIn] = Field(default_factory=list)
    action: list[str] = Field(default_factory=list)
    dialogue: list[Any] = Field(default_factory=list)


def _synth_beats(scene: _SceneIn) -> list[_BeatIn]:
    """beats 为空时，用 action/dialogue 兼容层合成节拍流。"""
    beats: list[_BeatIn] = []
    for act in scene.action or []:
        if isinstance(act, str) and act.strip():
            beats.append(_BeatIn(type="action", text=act.strip()))
    for d in scene.dialogue or []:
        if isinstance(d, dict):
            line = str(d.get("line") or d.get("text") or "").strip()
            if line:
                beats.append(_BeatIn(type="dialogue", speaker=d.get("speaker"), line=line,
                                     emotion=d.get("emotion")))
        elif isinstance(d, str) and d.strip():
            beats.append(_BeatIn(type="dialogue", line=d.strip()))
    return beats


class ScenePlan(BaseModel):
    scenes: list[_SceneIn] = Field(default_factory=list)


def _is_degenerate_plan(plan: ScenePlan, raw_text: str) -> bool:
    """判断场景规划是否「结构退化」：素材够长，却只拆出极少场景。

    影视剧逻辑下，多章素材必须切成多场（同一地点 + 连续时间 + 一个戏剧目标 = 一场）。
    只拆出 1-2 场，说明模型把整段塞进了一场，下游分镜必然被迫退化成「一人一切」的硬切。
    """
    n_scenes = len(plan.scenes or [])
    n_chars = len(raw_text or "")
    if n_chars >= 3000:
        return n_scenes < 3
    if n_chars >= 1200:
        return n_scenes < 2
    return False


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


def _stage_scenes(llm: LLM, settings: Settings, *, bible: Bible, excerpts: list[str], prof: dict[str, Any], language: str, chunks: list[str], critique: str = "") -> ScenePlan:
    """第二阶段：生成场景与节拍流（动作 / 对白 / cue）。

    核心是「影视剧的场景划分逻辑」：一场戏 = 同一地点 + 连续时间 + 一个戏剧目标
    + 一场冲突 + 人物状态变化。严禁把整段原著塞进一场戏。
    """
    from .profiles import profile_prompt

    characters = [c.model_dump() for c in bible.characters]
    locations = [loc.model_dump() for loc in bible.locations]
    excerpt_block = "\n".join(excerpts[:8])[:4000]
    prompt = (
        "请把原著改编成「一场一场的戏」，并为每场生成按阅读顺序混排的 beats 节拍流。\n"
        f"改编类型 profile：\n{profile_prompt(prof, language=language)}\n\n"
        "【影视剧的场景划分逻辑，必须遵守】\n"
        "- 一场戏 = 同一地点 + 连续时间 + 一个清晰的戏剧目标 + 一场冲突 + 人物状态前后发生变化。\n"
        "- 按「戏剧单元」划分，不要把整段原著塞进一场；一场戏的容量约等于「一次连续的对峙 / 行动 / 发现」。\n"
        "- 原著中跨地点、跨时间的段落，必须切成不同的场。\n"
        "- 每场都要填写 purpose（本场要达成什么）、conflict（谁在阻碍什么）、"
        "entry_state / exit_state（人物进场/出场时的状态变化）。\n"
        "- 场景数量由素材量决定，不要为省事而合并：三章左右的素材通常应产出 5–10 场戏。\n"
        "- 动作节拍要写「看得见的画面」：谁、在什么位置、做了什么物理动作、周围有什么道具与光源。\n"
        "  不要只写「他说」「他想了想」这类拍不出来的内容——下游会直接把动作节拍变成视频提示词。\n"
        "- 对白节拍之间与前后，要有可见的动作或空间信息，方便转成画面。\n"
    )
    if critique:
        prompt += f"\n上一版存在以下问题，请修正后重新输出：\n{critique}\n"
    prompt += (
        f"\n人物：{characters}\n地点：{locations}\n"
        f"故事圣经：{bible.model_dump_json()}\n\n"
        f"原著片段：\n{excerpt_block}"
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
            # 退化护栏：把多章素材挤进过少的场景（结构退化）时，带反馈重拆一次。
            if _is_degenerate_plan(plan, raw_text):
                log.warning("场景规划退化（%d 场 / %d 字），带反馈重拆", len(plan.scenes), len(raw_text))
                plan = _stage_scenes(
                    llm, settings, bible=bible, excerpts=excerpts, prof=prof, language=language, chunks=chunks,
                    critique=(
                        "上一版把多章素材挤进了过少的场景里（例如整段只拆出一场，或只拆出 2 场）。"
                        "请严格按「同一地点 + 连续时间 + 一个戏剧目标 + 一场冲突」重新切分，"
                        "跨地点、跨时间的段落必须切成不同的场。"
                    ),
                )
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
            for i, loc in enumerate(bible.locations):
                lid = normalize_id(loc.id, "loc", fallback=f"loc_{i + 1:03d}")
                if lid in used_locs:
                    lid = f"{lid}_{i + 1}"[: 40]
                used_locs.add(lid)
                locs.append(Location(id=lid, name=loc.name, description=loc.description))
            if not locs:
                locs = [Location(id="loc_main", name="主要场景")]

            char_id_set = {c.id for c in chars}
            char_list = [c.id for c in chars]
            loc_id = locs[0].id
            scenes: list[Scene] = []
            used_scene_ids: set[str] = set()
            for i, s in enumerate(plan.scenes or []):
                sid = normalize_id(s.scene_id or s.id, "scene", fallback=f"scene_{i + 1:03d}")
                # 模型常给出带后缀的场景 id（如 scene_01_wake_up），而 Scene.id
                # 规定纯数字（scene_NNN）：不合规时回退序号，并保证唯一。
                if not re.fullmatch(r"scene_[0-9]{3,}", sid):
                    sid = f"scene_{i + 1:03d}"
                n = i + 1
                while sid in used_scene_ids:
                    n += 1
                    sid = f"scene_{n:03d}"
                used_scene_ids.add(sid)
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
                # beats 为空时用 action/dialogue 兼容层合成，避免整场戏没有节拍。
                raw_beats = s.beats or _synth_beats(s)
                for bi, b in enumerate(raw_beats):
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
                        # 兼容字段 dialogue 必须与 beats 同步：留空会让后续
                        # 「只改 action」的 patch 重建节拍时把对白整体冲掉。
                        dialogue=[
                            {"speaker": b.speaker, "line": b.line}
                            for b in beats
                            if b.type == "dialogue" and b.speaker and b.line
                        ],
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
