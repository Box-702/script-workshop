# =====================================================================
# patch.py —— 剧本改写 patch 引擎
#
# 这是整个项目的灵魂模块。它的职责是：
#   1. 定义「改写提议」的受约束结构（PatchProposal）与「操作」结构（PatchOp）；
#   2. 把 LLM 的结构化输出规整为稳定、可审阅、可逐条接受的操作清单；
#   3. 把选中的操作应用到剧本上，形成新版本；
#   4. 提供校验，保证接受后的剧本仍然满足引用与 id 约束。
#
# 设计原则（与旧项目一致，但补强）：
#   - Agent 永远不整份覆盖剧本，只输出操作（add / set / remove）；
#   - 操作作用于「稳定 id」，尤其节拍 id（beat_数字）必须保持稳定；
#   - 兼容字段 action / dialogue 由 beats 主结构自动同步；
#   - 接受前必须校验，接受后必须生成新版本。
# =====================================================================

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .domain import (
    DialogueLine,
    Script,
    ScriptBeat,
    Scene,
    Source,
    normalize_id,
)

# 合法的节拍 id 形如 beat_数字（至少三位）。
BEAT_ID_RE = re.compile(r"^beat_[0-9]{3,}$")

# 允许被 Agent 直接编辑的场景字段（含时间 / 地点，供剧本编辑器与 Agent 都能改）。
EDITABLE_SCENE_FIELDS = {"title", "purpose", "conflict", "entry_state", "exit_state", "time", "location_id"}


# ---------- 受约束的改写提议结构 ----------


class DialogueChange(BaseModel):
    """提议中的对白行。speaker 必须引用场景内已有角色 id。"""

    speaker: str
    line: str
    emotion: str | None = None
    subtext: str | None = None


class BeatChange(BaseModel):
    """提议中的节拍。已有节拍必须保留原 id，新增可省略 id。

    兼容模型常见的 ``beat_id`` 写法（部分模型用 beat_id 而非 id）。
    """

    id: str | None = None
    beat_id: str | None = None
    type: Literal["action", "dialogue", "cue"] = "action"
    text: str | None = None
    speaker: str | None = None
    line: str | None = None
    emotion: str | None = None
    subtext: str | None = None


class SceneChange(BaseModel):
    """对单个场景的改写提议。只返回真正需要改的字段。

    兼容模型常见的 ``updates`` 写法（部分模型用 updates 而非 beats）。
    """

    scene_id: str
    title: str | None = None
    purpose: str | None = None
    conflict: str | None = None
    entry_state: str | None = None
    exit_state: str | None = None
    time: str | None = None
    location_id: str | None = None
    action: list[str] | None = None
    dialogue: list[DialogueChange] | None = None
    beats: list[BeatChange] | None = None
    updates: list[BeatChange] | None = None
    adaptation_reason: str | None = None
    fidelity: str | None = None


class PatchProposal(BaseModel):
    """Agent 的结构化输出：计划 + 逐场景改动。

    ``plan`` 兼容字符串或数组（部分模型把计划写成一段话）。
    """

    plan: list[str] | str = Field(default_factory=list)
    changes: list[SceneChange] = Field(default_factory=list)

    @field_validator("plan", mode="before")
    @classmethod
    def _plan_to_list(cls, v: object) -> object:
        if isinstance(v, str):
            return [v] if v.strip() else []
        return v


# ---------- 规范化后的 patch 操作 ----------


class PatchOp(BaseModel):
    """一条落地操作。``path`` 是稳定可寻址的 JSON 指针。

    说明：
    - ``before`` / ``after`` 用于前端字段级对比；
    - ``risk`` 用于高亮高风险改动（删除节拍、改变说话人等）。
    """

    op: Literal["add", "set", "remove"]
    path: str
    scene_id: str | None = None
    scene_title: str | None = None
    field: str | None = None
    beat_id: str | None = None
    beat_label: str | None = None
    risk: list[str] = Field(default_factory=list)
    before: Any = None
    value: Any = None
    after: Any = None


# ---------- 清洗工具 ----------


def _next_beat_id(used: set[str], start: int) -> str:
    """生成一个未被占用的 ``beat_数字`` id。"""
    number = max(1, start)
    while True:
        candidate = f"beat_{number:03d}"
        if candidate not in used:
            return candidate
        number += 1


def _clean_beat_id(value: object, used: set[str], fallback_index: int) -> str:
    """保留合法且未重复的 beat id，否则自动分配。"""
    text = str(value).strip() if value is not None else ""
    if text:
        candidate = normalize_id(text, "beat", fallback=str(fallback_index))
        if BEAT_ID_RE.match(candidate) and candidate not in used:
            return candidate
    return _next_beat_id(used, fallback_index)


def _resolve_speaker(speaker: object, allowed: set[str], name_to_id: dict[str, str] | None) -> str:
    """把说话人解析到角色 id。

    解析顺序：已是合法角色 id -> 全剧人物名映射 -> 保留原值（规整成 char_ 形式，
    让 validate_script 报「说话人不是已有角色」，由 guard 回炉让模型自己修正）。
    不再静默指派给 allowed[0]——那会把台词安到错误人物头上，比解析失败更糟。
    """
    text = str(speaker or "").strip()
    if not text:
        return ""
    if text in allowed:
        return text
    if name_to_id:
        hit = name_to_id.get(text) or name_to_id.get(text.lower())
        if hit:
            return hit
    return normalize_id(text, "char", fallback=text)


def _clean_dialogue(
    value: object, allowed: list[str], name_to_id: dict[str, str] | None = None
) -> list[dict[str, Any]] | None:
    """清洗对白：去空行、把说话人规整到场景内角色。"""
    allowed_set = set(allowed)
    out: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        speaker = _resolve_speaker(item.get("speaker"), allowed_set, name_to_id)
        if not line:
            continue
        if not speaker:
            continue
        row: dict[str, Any] = {"speaker": speaker, "line": line}
        for key in ("emotion", "subtext"):
            text = str(item.get(key) or "").strip()
            if text:
                row[key] = text
        out.append(row)
    return out or None


def _clean_action(value: object) -> list[str] | None:
    """清洗动作列表：去空行。"""
    if not isinstance(value, list):
        return None
    cleaned = [str(x).strip() for x in value if str(x).strip()]
    return cleaned or None


def _clean_beats(
    value: object, allowed: list[str], name_to_id: dict[str, str] | None = None
) -> list[dict[str, Any]] | None:
    """清洗节拍流：规整类型、说话人、稳定 id。"""
    allowed_set = set(allowed)
    used_ids: set[str] = set()
    out: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return None
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        if kind not in {"action", "dialogue", "cue"}:
            kind = "dialogue" if item.get("speaker") or item.get("line") or item.get("dialogue") else "action"
        beat_id = _clean_beat_id(item.get("id") or item.get("beat_id"), used_ids, len(out) + 1)
        beat: dict[str, Any] = {"id": beat_id, "type": kind}
        if kind == "dialogue":
            line = str(item.get("line") or item.get("dialogue") or item.get("text") or "").strip()
            speaker = _resolve_speaker(item.get("speaker"), allowed_set, name_to_id)
            if not line or not speaker:
                continue
            beat["speaker"] = speaker
            beat["line"] = line
            for key in ("emotion", "subtext"):
                text = str(item.get(key) or "").strip()
                if text:
                    beat[key] = text
        else:
            text = str(item.get("text") or item.get("action") or item.get("line") or "").strip()
            if not text:
                continue
            beat["text"] = text
        used_ids.add(beat_id)
        out.append(beat)
    return out or None


def _action_from_beats(beats: list[dict[str, Any]]) -> list[str]:
    """从节拍流同步动作兼容字段。"""
    return [
        str(b.get("text") or "").strip()
        for b in beats
        if b.get("type") == "action" and str(b.get("text") or "").strip()
    ]


def _dialogue_from_beats(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """从节拍流同步对白兼容字段。"""
    out: list[dict[str, Any]] = []
    for b in beats:
        if b.get("type") != "dialogue":
            continue
        line = str(b.get("line") or "").strip()
        speaker = str(b.get("speaker") or "").strip()
        if not line or not speaker:
            continue
        row: dict[str, Any] = {"speaker": speaker, "line": line}
        for key in ("emotion", "subtext"):
            text = str(b.get(key) or "").strip()
            if text:
                row[key] = text
        out.append(row)
    return out


def _beats_from_action_dialogue(
    action: list[str], dialogue: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """从兼容字段回建节拍流（用于老数据 / 未设置 beats 的场景）。"""
    beats: list[dict[str, Any]] = []
    for text in action:
        clean = str(text or "").strip()
        if clean:
            beats.append({"id": f"beat_{len(beats) + 1:03d}", "type": "action", "text": clean})
    for line in dialogue:
        if not isinstance(line, dict):
            continue
        speaker = str(line.get("speaker") or "").strip()
        text = str(line.get("line") or "").strip()
        if not speaker or not text:
            continue
        beat: dict[str, Any] = {
            "id": f"beat_{len(beats) + 1:03d}",
            "type": "dialogue",
            "speaker": speaker,
            "line": text,
        }
        for key in ("emotion", "subtext"):
            value = str(line.get(key) or "").strip()
            if value:
                beat[key] = value
        beats.append(beat)
    return beats


def _beat_map(beats: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """按 id 建立节拍映射，便于逐 id diff。"""
    return {str(b.get("id")): b for b in beats if isinstance(b, dict) and b.get("id")}


def _beat_label(beat_id: str, beat: dict[str, Any] | None) -> str:
    number = beat_id.removeprefix("beat_") if beat_id else ""
    kind = (beat or {}).get("type")
    label = {"action": "动作", "dialogue": "对白", "cue": "提示"}.get(kind, "节拍")
    return f"节拍 {number} · {label}" if number else label


def _beat_risks(before: dict[str, Any] | None, after: dict[str, Any] | None, op: str) -> list[str]:
    """识别高风险节拍改动，供前端提示。"""
    risks: list[str] = []
    if op == "remove":
        risks.append("会删除一个剧本节拍。")
    if op == "add":
        risks.append("会新增一个剧本节拍。")
    if before and after and before.get("type") != after.get("type"):
        risks.append("会改变节拍类型。")
    if before and after and before.get("speaker") != after.get("speaker"):
        risks.append("会改变对白说话人。")
    return risks


# ---------- 从提议构建操作 ----------


def _make_set_op(scene_idx: int, scene: dict[str, Any], field: str, before: Any, after: Any) -> PatchOp | None:
    """生成一个 set 操作；值没变化时返回 None。"""
    if before == after:
        return None
    return PatchOp(
        op="set",
        path=f"/script/scenes/{scene_idx}/{field}",
        scene_id=scene.get("id"),
        scene_title=scene.get("title"),
        field=field,
        before=before,
        value=after,
        after=after,
    )


def _make_beat_op(scene_idx: int, scene: dict[str, Any], beat_id: str, op: str, before: dict[str, Any] | None, after: dict[str, Any] | None) -> PatchOp:
    display = after or before
    return PatchOp(
        op=op,  # type: ignore[arg-type]
        path=f"/script/scenes/{scene_idx}/beats/{beat_id}",
        scene_id=scene.get("id"),
        scene_title=scene.get("title"),
        field="beats",
        beat_id=beat_id,
        beat_label=_beat_label(beat_id, display),
        risk=_beat_risks(before, after, op),
        before=before,
        value=after,
        after=after,
    )


def _beat_patch_ops(scene_idx: int, scene: dict[str, Any], next_beats: list[dict[str, Any]]) -> list[PatchOp]:
    """对单个场景的节拍流做逐 id diff，生成 add / set / remove 操作。"""
    current = scene.get("beats") if isinstance(scene.get("beats"), list) else []
    if not current:
        current = _beats_from_action_dialogue(scene.get("action") or [], scene.get("dialogue") or [])
    before_map = _beat_map(current)
    after_map = _beat_map(next_beats)
    ordered = [str(b.get("id")) for b in next_beats if b.get("id")]
    ordered.extend(bid for bid in before_map if bid not in after_map)

    ops: list[PatchOp] = []
    for beat_id in ordered:
        before = before_map.get(beat_id)
        after = after_map.get(beat_id)
        if before == after:
            continue
        if before is None:
            ops.append(_make_beat_op(scene_idx, scene, beat_id, "add", None, after))
        elif after is None:
            ops.append(_make_beat_op(scene_idx, scene, beat_id, "remove", before, None))
        else:
            ops.append(_make_beat_op(scene_idx, scene, beat_id, "set", before, after))
    return ops


def build_patch(
    proposal: PatchProposal,
    script: Script,
    *,
    selected_scene_ids: list[str],
    instruction: str,
) -> tuple[list[str], list[PatchOp]]:
    """把结构化提议规整为逐场景的稳定操作清单。

    这是「可审阅」的关键：一条提议 -> 多条原子操作，
    前端因此能逐条展示、逐条接受，而不是一次性整场覆盖。
    """
    data = script.model_dump(exclude_none=False)
    scenes = data.get("scenes", [])
    wanted = {normalize_id(sid, "scene", fallback=sid) for sid in selected_scene_ids} or {s.get("id") for s in scenes}
    index_by_id = {str(s.get("id")): idx for idx, s in enumerate(scenes)}
    # 全剧人物名 -> id 映射：LLM 常用「林然」这类名字指代说话人，先解析成 id。
    name_to_id = {c.name: c.id for c in script.characters}

    ops: list[PatchOp] = []
    for change in proposal.changes:
        # 表面 id 可能不是规范形式（scene_1 vs scene_001），统一规整后再查找。
        scene_id = normalize_id(change.scene_id, "scene", fallback=str(change.scene_id))
        idx = index_by_id.get(scene_id)
        # 模型可能提议修改用户未勾选的场景：严格限制在选中范围内。
        if idx is None or scene_id not in wanted:
            continue
        scene = scenes[idx]
        allowed = [str(c) for c in scene.get("characters", [])]
        beats_were_set = False

        for field in EDITABLE_SCENE_FIELDS:
            new_value = getattr(change, field)
            if new_value is None:
                continue
            value = str(new_value).strip()
            if value:
                op = _make_set_op(idx, scene, field, scene.get(field), value)
                if op:
                    ops.append(op)

        raw_beats = change.beats if change.beats is not None else change.updates
        if raw_beats is not None:
            beats = _clean_beats([b.model_dump(exclude_none=True) for b in raw_beats], allowed, name_to_id)
            if beats is not None:
                beats_were_set = True
                ops.extend(_beat_patch_ops(idx, scene, beats))

        if change.action is not None and not beats_were_set:
            action = _clean_action(change.action)
            if action is not None:
                op = _make_set_op(idx, scene, "action", scene.get("action") or [], action)
                if op:
                    ops.append(op)

        if change.dialogue is not None and not beats_were_set:
            dialogue = _clean_dialogue(
                [d.model_dump(exclude_none=True) for d in change.dialogue], allowed, name_to_id
            )
            if dialogue is not None:
                op = _make_set_op(idx, scene, "dialogue", scene.get("dialogue") or [], dialogue)
                if op:
                    ops.append(op)

        # 只改了 action/dialogue、而场景已有 beats 时，同步兼容 beats，避免不一致。
        if (
            not beats_were_set
            and scene.get("beats")
            and (change.action is not None or change.dialogue is not None)
        ):
            current_beats = scene.get("beats") or []
            next_action = _clean_action(change.action) if change.action is not None else None
            next_action = next_action or _action_from_beats(current_beats) or scene.get("action") or []
            next_dialogue = None
            if change.dialogue is not None:
                next_dialogue = _clean_dialogue(
                    [d.model_dump(exclude_none=True) for d in change.dialogue], allowed, name_to_id
                )
            # beats 是主结构：提议没带对白时，对白以既有节拍流为准，
            # 而不是可能过期的兼容字段（否则会把整场对白静默冲掉）。
            next_dialogue = next_dialogue or _dialogue_from_beats(current_beats) or []
            compatible = _beats_from_action_dialogue(next_action, next_dialogue)
            op = _make_set_op(idx, scene, "beats", scene.get("beats") or [], compatible)
            if op:
                ops.append(op)

        # 改编说明（始终记录，便于追溯）。
        notes = scene.get("adaptation_notes") or {}
        reason = str(change.adaptation_reason or "").strip()
        if reason:
            op = _make_set_op(idx, scene, "adaptation_notes/reason", notes.get("reason"), reason)
            if op:
                ops.append(op)
        fidelity = str(change.fidelity or "").strip()
        if fidelity:
            op = _make_set_op(idx, scene, "adaptation_notes/fidelity", notes.get("fidelity"), fidelity)
            if op:
                ops.append(op)

    plan = [str(p).strip() for p in proposal.plan if str(p).strip()]
    if not plan:
        plan = default_plan()
    if not ops:
        plan_a, ops_a = fallback_patch(script, instruction, selected_scene_ids)
        plan = plan_a
        ops = ops_a
        plan.append("模型没有返回可落地字段，已保留为改编说明供审阅。")
    return plan, ops


def default_plan() -> list[str]:
    """模型不可用或未返回计划时的兜底计划。"""
    return [
        "读取当前剧本版本与用户选择范围。",
        "根据用户需求生成结构化场景改动。",
        "等待用户确认后生成新的剧本版本。",
    ]


# ---------- 应用操作 ----------


def _sync_scene_compat(scene: dict[str, Any]) -> None:
    """从 beats 同步 action / dialogue 兼容字段。"""
    beats = scene.get("beats")
    if not isinstance(beats, list):
        return
    scene["action"] = _action_from_beats(beats)
    scene["dialogue"] = _dialogue_from_beats(beats)


def apply_patch(script: Script, ops: list[PatchOp]) -> Script:
    """把选中的操作应用到剧本副本，得到新版本。

    应用后重新校验并重建 Script，以规整 id 与同步兼容字段。
    """
    data = deepcopy(script.model_dump(exclude_none=False))
    sync_scene_indexes: set[int] = set()
    scenes = data.setdefault("scenes", [])

    for op in ops:
        path = op.path
        parts = [p for p in path.split("/") if p]
        if len(parts) < 4 or parts[0] != "script" or parts[1] != "scenes":
            raise ValueError(f"不支持的操作路径：{path}")
        try:
            scene_idx = int(parts[2])
        except ValueError as e:
            raise ValueError(f"无法解析场景下标：{path}") from e
        if scene_idx < 0 or scene_idx >= len(scenes):
            raise ValueError(f"场景下标越界：{scene_idx}")
        scene = scenes[scene_idx]
        field_path = parts[3:]

        if len(field_path) == 2 and field_path[0] == "beats":
            _apply_beat_op(scene, field_path[1], op)
            sync_scene_indexes.add(scene_idx)
            continue
        if len(field_path) == 1 and field_path[0] in EDITABLE_SCENE_FIELDS | {"beats", "action", "dialogue"}:
            scene[field_path[0]] = op.value
            if field_path[0] == "beats":
                sync_scene_indexes.add(scene_idx)
            continue
        if len(field_path) == 2 and field_path[0] == "adaptation_notes" and field_path[1] in {"reason", "fidelity"}:
            # model_dump 可能把 adaptation_notes 输出为 None，需先归一化为 dict。
            notes = scene.get("adaptation_notes")
            if not isinstance(notes, dict):
                notes = {}
                scene["adaptation_notes"] = notes
            notes[field_path[1]] = op.value
            continue
        raise ValueError(f"不支持的操作路径：{path}")

    for idx in sync_scene_indexes:
        _sync_scene_compat(scenes[idx])

    return Script.model_validate(data)


def _apply_beat_op(scene: dict[str, Any], beat_id: str, op: PatchOp) -> None:
    """在单个场景内应用节拍操作。"""
    beats = scene.setdefault("beats", [])
    if not isinstance(beats, list):
        beats = []
        scene["beats"] = beats
    existing = next(
        (i for i, b in enumerate(beats) if isinstance(b, dict) and b.get("id") == beat_id),
        -1,
    )
    if op.op == "remove":
        if existing >= 0:
            beats.pop(existing)
        return
    value = op.value
    if not isinstance(value, dict):
        raise ValueError(f"节拍补丁值必须是对象：{op.path}")
    if existing >= 0:
        beats[existing] = value
    else:
        beats.append(value)


# ---------- 校验 ----------


class ValidationIssue(BaseModel):
    """一条校验问题。"""

    path: str
    message: str
    severity: Literal["error", "warning"] = "error"


def validate_script(script: Script) -> list[ValidationIssue]:
    """检查引用一致性与 id 稳定性，返回问题列表。

    允许出现 warning（例如未设置 entry_state），但 error 必须清零才可落版。
    """
    issues: list[ValidationIssue] = []
    char_ids = {c.id for c in script.characters}
    loc_ids = {l.id for l in script.locations}
    scene_ids: set[str] = set()

    for si, scene in enumerate(script.scenes):
        if scene.id in scene_ids:
            issues.append(ValidationIssue(path=f"/scenes/{si}/id", message="场景 id 重复。"))
        scene_ids.add(scene.id)

        if not scene.title:
            issues.append(ValidationIssue(path=f"/scenes/{si}/title", message="场景标题为空。"))
        if not scene.purpose:
            issues.append(ValidationIssue(path=f"/scenes/{si}/purpose", message="场景目的为空。"))
        if not scene.conflict:
            issues.append(ValidationIssue(path=f"/scenes/{si}/conflict", message="场景冲突为空。"))
        if scene.location_id not in loc_ids:
            issues.append(ValidationIssue(path=f"/scenes/{si}/location_id", message=f"引用了不存在的地点：{scene.location_id}"))
        for cid in scene.characters:
            if cid not in char_ids:
                issues.append(ValidationIssue(path=f"/scenes/{si}/characters", message=f"引用了不存在的人物：{cid}"))
        if not scene.characters:
            issues.append(ValidationIssue(path=f"/scenes/{si}/characters", message="场景没有人物。"))

        beat_ids: set[str] = set()
        for bi, beat in enumerate(scene.beats):
            if beat.id in beat_ids:
                issues.append(ValidationIssue(path=f"/scenes/{si}/beats/{bi}/id", message="节拍 id 重复。"))
            beat_ids.add(beat.id)
            if beat.type == "dialogue":
                if beat.speaker not in char_ids:
                    issues.append(ValidationIssue(path=f"/scenes/{si}/beats/{bi}/speaker", message=f"节拍说话人不是已有角色：{beat.speaker}"))
                if not beat.line:
                    issues.append(ValidationIssue(path=f"/scenes/{si}/beats/{bi}/line", message="对白节拍缺少台词。"))
            elif not beat.text:
                issues.append(ValidationIssue(path=f"/scenes/{si}/beats/{bi}/text", message="动作 / 提示节拍缺少文本。"))

    if not script.characters:
        issues.append(ValidationIssue(path="/characters", message="剧本至少需要一个人物。"))
    if not script.scenes:
        issues.append(ValidationIssue(path="/scenes", message="剧本至少需要一个场景。"))
    if not script.logline:
        issues.append(ValidationIssue(path="/logline", message="缺少一句话梗概。"))
    return issues


# ---------- 无模型回退 ----------


def fallback_patch(script: Script, instruction: str, scene_ids: list[str]) -> tuple[list[str], list[PatchOp]]:
    """没有可用模型时，把改编需求写入目标场景的 adaptation_notes。

    这是一条「诚实」的兜底路径：不伪造内容到正文，而是让用户看到
    「Agent 已接收指令，但需要配置模型才能生成实质改写」。
    """
    ops: list[PatchOp] = []
    scenes = script.scenes
    wanted = {normalize_id(sid, "scene", fallback=sid) for sid in scene_ids} or {s.id for s in scenes}
    for idx, scene in enumerate(scenes):
        if scene.id not in wanted:
            continue
        notes = scene.adaptation_notes.model_dump() if scene.adaptation_notes else {}
        reason = f"AI 改编需求：{instruction.strip()}"
        op = _make_set_op(idx, {"id": scene.id, "title": scene.title}, "adaptation_notes/reason", notes.get("reason"), reason)
        if op:
            ops.append(op)
        # 记录 fidelity 为 reordered（缺省），让前端有可比对字段。
        if not notes.get("fidelity"):
            op2 = _make_set_op(idx, {"id": scene.id, "title": scene.title}, "adaptation_notes/fidelity", notes.get("fidelity"), "reordered")
            if op2:
                ops.append(op2)
    return default_plan(), ops


# ---------- 便捷构造函数 ----------


def make_source_script(
    title: str, raw_text: str, *, adaptation_type: str = "short_drama", language: str = "zh-CN"
) -> Script:
    """无模型时快速构造一个最小有效剧本，用于打通无 key 演示链路。"""
    from .profiles import profile_for, profile_type

    name = str(profile_type(adaptation_type))
    profile = profile_for(name)
    paragraphs = [p.strip() for p in raw_text.splitlines() if p.strip()]
    actions = [p for p in paragraphs[:8]] or ["（场景动作）主角推门进入。"]
    return Script(
        title=title or "未命名故事",
        version="1.0",
        language=language,
        adaptation={"type": name, "target_format": profile["target_format"], "tone": profile["tone"]},
        source=Source(chapter_count=1, chapter_ids=["ch_001"]),
        logline="主角面对核心冲突，开启一场改编冒险。",
        themes=["冲突", "成长"],
        characters=[{"id": "char_protagonist", "name": "主角", "role": "protagonist"}],
        locations=[{"id": "loc_main", "name": "主要场景"}],
        scenes=[
            Scene(
                id="scene_001",
                title="起始",
                chapter_refs=["ch_001"],
                location_id="loc_main",
                characters=["char_protagonist"],
                purpose="引出核心冲突。",
                conflict="主角必须做出选择。",
                action=actions,
                dialogue=[],
                beats=[
                    ScriptBeat(id=f"beat_{i + 1:03d}", type="action", text=a)
                    for i, a in enumerate(actions)
                ],
            )
        ],
    )
