from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import db as dbm
from ..adaptation_profiles import adaptation_profile_for, adaptation_profile_prompt
from ..ids import gen_id
from ..providers.base import LLMProvider, Stage
from ..schemas import AgentAdaptRequest, normalize_id
from ..yaml_io import to_yaml
from .versions import create_version_from_yaml, get_version_or_404, latest_version

EDITABLE_SCENE_FIELDS = {
    "title",
    "purpose",
    "conflict",
    "entry_state",
    "exit_state",
    "action",
    "dialogue",
    "beats",
}

BEAT_ID_RE = re.compile(r"^beat_[0-9]{3,}$")

AGENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["plan", "changes"],
    "properties": {
        "plan": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 6,
        },
        "changes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["scene_id"],
                "properties": {
                    "scene_id": {"type": "string"},
                    "title": {"type": "string"},
                    "purpose": {"type": "string"},
                    "conflict": {"type": "string"},
                    "entry_state": {"type": "string"},
                    "exit_state": {"type": "string"},
                    "action": {"type": "array", "items": {"type": "string"}},
                    "dialogue": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["speaker", "line"],
                            "properties": {
                                "speaker": {"type": "string"},
                                "line": {"type": "string"},
                                "emotion": {"type": "string"},
                                "subtext": {"type": "string"},
                            },
                        },
                    },
                    "beats": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["type"],
                            "properties": {
                                "id": {"type": "string"},
                                "type": {
                                    "type": "string",
                                    "enum": ["action", "dialogue", "cue"],
                                },
                                "text": {"type": "string"},
                                "speaker": {"type": "string"},
                                "line": {"type": "string"},
                                "emotion": {"type": "string"},
                                "subtext": {"type": "string"},
                            },
                        },
                    },
                    "adaptation_reason": {"type": "string"},
                    "fidelity": {
                        "type": "string",
                        "enum": ["faithful", "compressed", "reordered", "merged", "invented"],
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


def _selected_scene_indexes(version: dbm.ScriptVersion, scene_ids: list[str]) -> list[int]:
    scenes = version.json_content.get("script", {}).get("scenes", [])
    if not scenes:
        raise HTTPException(400, "base version has no scenes")
    if not scene_ids:
        return [0]

    wanted = set(scene_ids)
    indexes = [idx for idx, scene in enumerate(scenes) if scene.get("id") in wanted]
    if not indexes:
        raise HTTPException(400, "selected scenes were not found in base version")
    return indexes


def _fallback_patch(
    version: dbm.ScriptVersion, instruction: str, scene_ids: list[str]
) -> list[dict]:
    patch: list[dict] = []
    scenes = version.json_content.get("script", {}).get("scenes", [])
    for idx in _selected_scene_indexes(version, scene_ids):
        scene = scenes[idx]
        notes = scene.get("adaptation_notes") or {}
        next_value = f"AI 改编需求：{instruction.strip()}"
        patch.append(
            {
                "op": "set",
                "path": f"/script/scenes/{idx}/adaptation_notes/reason",
                "scene_id": scene.get("id"),
                "scene_title": scene.get("title"),
                "before": notes.get("reason"),
                "value": next_value,
                "after": next_value,
            }
        )
    return patch


def _text_excerpt(value: str, limit: int = 1200) -> str:
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _source_chapter_context(
    db: Session, project_id: str, chapter_refs: list[str]
) -> list[dict[str, Any]]:
    if not chapter_refs:
        return []
    chapters = (
        db.query(dbm.Chapter)
        .filter(dbm.Chapter.project_id == project_id)
        .filter(dbm.Chapter.id.in_(chapter_refs))
        .order_by(dbm.Chapter.order_index.asc())
        .all()
    )
    return [
        {
            "id": chapter.id,
            "title": chapter.title,
            "excerpt": _text_excerpt(chapter.content),
        }
        for chapter in chapters
    ]


def _recent_edit_context(db: Session, project_id: str, limit: int = 5) -> list[dict[str, Any]]:
    events = (
        db.query(dbm.EditEvent)
        .filter_by(project_id=project_id)
        .order_by(dbm.EditEvent.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "edit_type": event.edit_type,
            "target_path": event.target_path,
            "note": event.note,
            "patch_excerpt": _text_excerpt(json.dumps(event.patch, ensure_ascii=False), 500)
            if event.patch
            else "",
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]


def _build_agent_prompt(
    db: Session,
    project: dbm.Project,
    version: dbm.ScriptVersion,
    instruction: str,
    scene_ids: list[str],
) -> tuple[str, list[int]]:
    data = version.json_content
    script = data.get("script", {})
    scenes = script.get("scenes", [])
    adaptation = script.get("adaptation") if isinstance(script.get("adaptation"), dict) else {}
    adaptation_type = str(adaptation.get("type") or project.adaptation_type or "other")
    language = str(script.get("language") or project.language or "zh-CN")
    adaptation_profile = adaptation_profile_for(adaptation_type)
    selected_indexes = _selected_scene_indexes(version, scene_ids)
    selected_scene_ids = {scenes[idx].get("id") for idx in selected_indexes}
    characters = {
        item.get("id"): {
            "name": item.get("name"),
            "role": item.get("role"),
            "goal": item.get("goal"),
            "motivation": item.get("motivation"),
            "speech_style": item.get("speech_style"),
        }
        for item in script.get("characters", [])
        if isinstance(item, dict)
    }
    locations = {
        item.get("id"): {
            "name": item.get("name"),
            "description": item.get("description"),
        }
        for item in script.get("locations", [])
        if isinstance(item, dict)
    }
    selected_scenes = [scenes[idx] for idx in selected_indexes]
    chapter_refs = sorted(
        {
            str(chapter_id)
            for scene in selected_scenes
            for chapter_id in scene.get("chapter_refs", [])
            if str(chapter_id).strip()
        }
    )
    context = {
        "script": {
            "title": script.get("title"),
            "language": language,
            "adaptation": script.get("adaptation"),
            "adaptation_profile": adaptation_profile,
            "logline": script.get("logline"),
            "themes": script.get("themes"),
        },
        "characters": characters,
        "locations": locations,
        "selected_scenes": selected_scenes,
        "source_chapters": _source_chapter_context(db, project.id, chapter_refs),
        "recent_edits": _recent_edit_context(db, project.id),
    }
    prompt = f"""
你是剧本改编助手。请只改 selected_scenes 中的场景，不要新增场景、角色或地点。
用户改编需求：{instruction.strip()}

请输出 JSON：
- plan: 1-6 条中文计划，说明你将如何改。
- changes: 每个被修改场景一项，scene_id 必须来自 {sorted(selected_scene_ids)}。
- 必须遵守改编类型 profile，不要把电影/剧集/舞台剧都改成短剧节奏。
- 只返回真正需要更新的字段；没有必要改的字段不要返回。
- dialogue 中 speaker 必须使用该场景已有 characters 列表里的角色 id。
- 优先返回 beats 来修改剧本流；beats 是动作、对白、提示按阅读顺序混排的列表。
- 如果修改台词或动作且该场景已有 beats，请返回完整 beats，避免剧本流和兼容字段不一致。
- 返回已有节拍时必须保留原来的 beat id；新增节拍可以省略 id，或使用未占用的 beat_数字 id。
- action 和 dialogue 如果返回，会整体替换该场景对应列表。
- beats 如果返回，也会同步更新 action/dialogue 兼容字段。
- adaptation_reason 要说明这次改编为什么这么做。

改编类型 profile：
{adaptation_profile_prompt(adaptation_profile, language=language)}

当前上下文：
{json.dumps(context, ensure_ascii=False, indent=2)}
"""
    return prompt, selected_indexes


def _clean_dialogue(value: object, allowed_speakers: list[str]) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    cleaned: list[dict[str, Any]] = []
    allowed = set(allowed_speakers)
    fallback_speaker = allowed_speakers[0] if allowed_speakers else ""
    for item in value:
        if not isinstance(item, dict):
            continue
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        speaker = str(item.get("speaker") or "").strip()
        if speaker not in allowed:
            speaker = fallback_speaker
        if not speaker:
            continue
        next_item: dict[str, Any] = {"speaker": speaker, "line": line}
        for key in ("emotion", "subtext"):
            text = str(item.get(key) or "").strip()
            if text:
                next_item[key] = text
        cleaned.append(next_item)
    return cleaned


def _clean_action(value: object) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned if cleaned else None


def _next_available_beat_id(used_ids: set[str], start: int) -> str:
    number = max(1, start)
    while True:
        candidate = f"beat_{number:03d}"
        if candidate not in used_ids:
            return candidate
        number += 1


def _clean_beat_id(value: object, used_ids: set[str], fallback_index: int) -> str:
    if value is not None and str(value).strip():
        candidate = normalize_id(value, "beat", fallback=str(fallback_index))
        if BEAT_ID_RE.match(candidate) and candidate not in used_ids:
            return candidate
    return _next_available_beat_id(used_ids, fallback_index)


def _clean_beats(value: object, allowed_speakers: list[str]) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    cleaned: list[dict[str, Any]] = []
    used_ids: set[str] = set()
    allowed = set(allowed_speakers)
    fallback_speaker = allowed_speakers[0] if allowed_speakers else ""
    for item in value:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("type") or "").strip()
        if kind not in {"action", "dialogue", "cue"}:
            kind = "dialogue" if item.get("speaker") or item.get("line") else "action"
        beat_id = _clean_beat_id(item.get("id"), used_ids, len(cleaned) + 1)
        beat: dict[str, Any] = {"id": beat_id, "type": kind}
        if kind == "dialogue":
            line = str(item.get("line") or item.get("text") or "").strip()
            speaker = str(item.get("speaker") or "").strip()
            if speaker not in allowed:
                speaker = fallback_speaker
            if not line or not speaker:
                continue
            beat["speaker"] = speaker
            beat["line"] = line
            for key in ("emotion", "subtext"):
                text = str(item.get(key) or "").strip()
                if text:
                    beat[key] = text
        else:
            text = str(item.get("text") or item.get("line") or "").strip()
            if not text:
                continue
            beat["text"] = text
        used_ids.add(beat_id)
        cleaned.append(beat)
    return cleaned if cleaned else None


def _action_from_beats(beats: list[dict[str, Any]]) -> list[str]:
    return [
        str(beat.get("text") or "").strip()
        for beat in beats
        if beat.get("type") == "action" and str(beat.get("text") or "").strip()
    ]


def _dialogue_from_beats(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dialogue: list[dict[str, Any]] = []
    for beat in beats:
        if beat.get("type") != "dialogue":
            continue
        line = str(beat.get("line") or "").strip()
        speaker = str(beat.get("speaker") or "").strip()
        if not line or not speaker:
            continue
        item: dict[str, Any] = {"speaker": speaker, "line": line}
        for key in ("emotion", "subtext"):
            text = str(beat.get(key) or "").strip()
            if text:
                item[key] = text
        dialogue.append(item)
    return dialogue


def _beats_from_action_dialogue(
    action: list[str], dialogue: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    beats: list[dict[str, Any]] = []
    for text in action:
        clean = str(text or "").strip()
        if clean:
            beats.append(
                {
                    "id": f"beat_{len(beats) + 1:03d}",
                    "type": "action",
                    "text": clean,
                }
            )
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


def _beat_maps(beats: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(beat.get("id")): beat
        for beat in beats
        if isinstance(beat, dict) and beat.get("id")
    }


def _beat_label(beat_id: str, beat: dict[str, Any] | None) -> str:
    number = beat_id.removeprefix("beat_") if beat_id else ""
    kind = (beat or {}).get("type")
    type_label = {"action": "动作", "dialogue": "对白", "cue": "提示"}.get(kind, "节拍")
    return f"节拍 {number} · {type_label}" if number else type_label


def _beat_risks(
    before: dict[str, Any] | None, after: dict[str, Any] | None, op: str
) -> list[str]:
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


def _make_beat_op(
    *,
    scene_index: int,
    scene: dict[str, Any],
    beat_id: str,
    op: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    display_beat = after or before
    return {
        "op": op,
        "path": f"/script/scenes/{scene_index}/beats/{beat_id}",
        "scene_id": scene.get("id"),
        "scene_title": scene.get("title"),
        "field": "beats",
        "beat_id": beat_id,
        "beat_label": _beat_label(beat_id, display_beat),
        "risk": _beat_risks(before, after, op),
        "before": before,
        "value": after,
        "after": after,
    }


def _beat_patch_ops(
    *,
    scene_index: int,
    scene: dict[str, Any],
    next_beats: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_beats = scene.get("beats") if isinstance(scene.get("beats"), list) else []
    if not current_beats:
        current_beats = _beats_from_action_dialogue(
            scene.get("action") or [],
            scene.get("dialogue") or [],
        )
    before_map = _beat_maps(current_beats)
    after_map = _beat_maps(next_beats)
    ordered_ids = [str(beat.get("id")) for beat in next_beats if beat.get("id")]
    ordered_ids.extend(beat_id for beat_id in before_map if beat_id not in after_map)

    ops: list[dict[str, Any]] = []
    for beat_id in ordered_ids:
        before = before_map.get(beat_id)
        after = after_map.get(beat_id)
        if before == after:
            continue
        if before is None and after is not None:
            ops.append(
                _make_beat_op(
                    scene_index=scene_index,
                    scene=scene,
                    beat_id=beat_id,
                    op="add",
                    before=None,
                    after=after,
                )
            )
        elif before is not None and after is None:
            ops.append(
                _make_beat_op(
                    scene_index=scene_index,
                    scene=scene,
                    beat_id=beat_id,
                    op="remove",
                    before=before,
                    after=None,
                )
            )
        else:
            ops.append(
                _make_beat_op(
                    scene_index=scene_index,
                    scene=scene,
                    beat_id=beat_id,
                    op="set",
                    before=before,
                    after=after,
                )
            )
    return ops


def _make_set_op(
    *,
    scene_index: int,
    scene: dict[str, Any],
    field: str,
    before: Any,
    after: Any,
) -> dict[str, Any] | None:
    if before == after:
        return None
    return {
        "op": "set",
        "path": f"/script/scenes/{scene_index}/{field}",
        "scene_id": scene.get("id"),
        "scene_title": scene.get("title"),
        "field": field,
        "before": before,
        "value": after,
        "after": after,
    }


def _patch_from_agent_response(
    version: dbm.ScriptVersion,
    response: dict[str, Any],
    selected_indexes: list[int],
    instruction: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    scenes = version.json_content.get("script", {}).get("scenes", [])
    index_by_scene_id = {scenes[idx].get("id"): idx for idx in selected_indexes}
    patch: list[dict[str, Any]] = []
    changes = response.get("changes") if isinstance(response, dict) else []
    if not isinstance(changes, list):
        changes = []

    for change in changes:
        if not isinstance(change, dict):
            continue
        scene_id = change.get("scene_id")
        if scene_id not in index_by_scene_id:
            continue
        idx = index_by_scene_id[scene_id]
        scene = scenes[idx]
        allowed_speakers = [str(item) for item in scene.get("characters", [])]
        next_action: list[str] | None = None
        next_dialogue: list[dict[str, Any]] | None = None
        beats_were_set = False

        for field in ("title", "purpose", "conflict", "entry_state", "exit_state"):
            if field not in change:
                continue
            value = str(change.get(field) or "").strip()
            if value:
                op = _make_set_op(
                    scene_index=idx,
                    scene=scene,
                    field=field,
                    before=scene.get(field),
                    after=value,
                )
                if op:
                    patch.append(op)

        if "beats" in change:
            beats = _clean_beats(change.get("beats"), allowed_speakers)
            if beats is not None:
                beats_were_set = True
                patch.extend(
                    _beat_patch_ops(scene_index=idx, scene=scene, next_beats=beats)
                )

        if "action" in change and not beats_were_set:
            action = _clean_action(change.get("action"))
            if action is not None:
                next_action = action
                op = _make_set_op(
                    scene_index=idx,
                    scene=scene,
                    field="action",
                    before=scene.get("action") or [],
                    after=action,
                )
                if op:
                    patch.append(op)

        if "dialogue" in change and not beats_were_set:
            dialogue = _clean_dialogue(change.get("dialogue"), allowed_speakers)
            if dialogue is not None:
                next_dialogue = dialogue
                op = _make_set_op(
                    scene_index=idx,
                    scene=scene,
                    field="dialogue",
                    before=scene.get("dialogue") or [],
                    after=dialogue,
                )
                if op:
                    patch.append(op)

        if (
            not beats_were_set
            and scene.get("beats")
            and (next_action is not None or next_dialogue is not None)
        ):
            compatible_beats = _beats_from_action_dialogue(
                next_action if next_action is not None else scene.get("action") or [],
                next_dialogue if next_dialogue is not None else scene.get("dialogue") or [],
            )
            op = _make_set_op(
                scene_index=idx,
                scene=scene,
                field="beats",
                before=scene.get("beats") or [],
                after=compatible_beats,
            )
            if op:
                patch.append(op)

        reason = str(change.get("adaptation_reason") or "").strip()
        if reason:
            notes = scene.get("adaptation_notes") or {}
            op = _make_set_op(
                scene_index=idx,
                scene=scene,
                field="adaptation_notes/reason",
                before=notes.get("reason"),
                after=reason,
            )
            if op:
                patch.append(op)

        fidelity = str(change.get("fidelity") or "").strip()
        if fidelity:
            notes = scene.get("adaptation_notes") or {}
            op = _make_set_op(
                scene_index=idx,
                scene=scene,
                field="adaptation_notes/fidelity",
                before=notes.get("fidelity"),
                after=fidelity,
            )
            if op:
                patch.append(op)

    plan_raw = response.get("plan") if isinstance(response, dict) else None
    plan = [str(item).strip() for item in plan_raw or [] if str(item).strip()]
    if not plan:
        plan = [
            "读取当前剧本版本和用户选择范围。",
            "根据用户需求生成结构化场景修改。",
            "等待用户确认后生成新的剧本版本。",
        ]
    if not patch:
        patch = _fallback_patch(
            version,
            instruction,
            [str(scenes[idx].get("id")) for idx in selected_indexes],
        )
        plan.append("模型没有返回可落地字段，已保留为改编说明供审阅。")
    return plan, patch


def _build_model_patch(
    db: Session,
    project: dbm.Project,
    version: dbm.ScriptVersion,
    instruction: str,
    scene_ids: list[str],
    provider: LLMProvider,
) -> tuple[list[str], list[dict[str, Any]]]:
    prompt, selected_indexes = _build_agent_prompt(db, project, version, instruction, scene_ids)
    response = provider.generate_structured(prompt, AGENT_RESPONSE_SCHEMA, stage=Stage.AGENT)
    return _patch_from_agent_response(version, response, selected_indexes, instruction)


def _apply_set_patch(data: dict[str, Any], patch: list[dict]) -> dict[str, Any]:
    next_data = deepcopy(data)
    sync_beat_scene_indexes: set[int] = set()
    for op in patch:
        op_name = str(op.get("op") or "")
        if op_name not in {"set", "add", "remove"}:
            raise HTTPException(400, f"unsupported patch op: {op.get('op')}")
        path = str(op.get("path") or "")
        if not path.startswith("/script/scenes/"):
            raise HTTPException(400, f"unsupported patch path: {path}")

        parts = [part for part in path.split("/") if part]
        try:
            scene_index = int(parts[2])
        except ValueError as e:
            raise HTTPException(400, f"invalid patch path: {path}") from e
        scenes = next_data["script"]["scenes"]
        if scene_index < 0 or scene_index >= len(scenes):
            raise HTTPException(400, f"patch scene index is out of range: {scene_index}")
        scene = scenes[scene_index]
        field_path = parts[3:]
        if len(field_path) == 2 and field_path[0] == "beats":
            beat_id = field_path[1]
            beats = scene.setdefault("beats", [])
            if not isinstance(beats, list):
                raise HTTPException(400, f"invalid beats value in scene: {scene_index}")
            existing_index = next(
                (
                    idx
                    for idx, beat in enumerate(beats)
                    if isinstance(beat, dict) and beat.get("id") == beat_id
                ),
                -1,
            )
            if op_name == "remove":
                if existing_index >= 0:
                    beats.pop(existing_index)
            else:
                value = op.get("value")
                if not isinstance(value, dict):
                    raise HTTPException(400, f"invalid beat patch value: {path}")
                if existing_index >= 0:
                    beats[existing_index] = value
                else:
                    beats.append(value)
            sync_beat_scene_indexes.add(scene_index)
            continue
        if len(field_path) == 1 and field_path[0] in EDITABLE_SCENE_FIELDS:
            scene[field_path[0]] = op.get("value")
            if field_path[0] == "beats":
                sync_beat_scene_indexes.add(scene_index)
            continue
        if len(field_path) == 2 and field_path[0] == "adaptation_notes" and field_path[1] in {
            "reason",
            "fidelity",
        }:
            notes = scene.setdefault("adaptation_notes", {})
            notes[field_path[1]] = op.get("value", "")
            if field_path[1] == "reason":
                notes.setdefault("fidelity", "reordered")
            continue
        raise HTTPException(400, f"unsupported patch path: {path}")
    for scene_index in sync_beat_scene_indexes:
        _sync_scene_compat_from_beats(next_data["script"]["scenes"][scene_index])
    return next_data


def _select_patch_items(patch: list[dict], patch_indexes: list[int] | None) -> list[dict]:
    if patch_indexes is None:
        return patch
    if not patch_indexes:
        raise HTTPException(400, "at least one patch item must be selected")

    seen: set[int] = set()
    selected: list[dict] = []
    for index in patch_indexes:
        if index in seen:
            continue
        if index < 0 or index >= len(patch):
            raise HTTPException(400, f"patch index is out of range: {index}")
        seen.add(index)
        selected.append(patch[index])
    return selected


def _sync_scene_compat_from_beats(scene: dict[str, Any]) -> None:
    beats = scene.get("beats")
    if not isinstance(beats, list):
        return
    scene["action"] = _action_from_beats(beats)
    scene["dialogue"] = _dialogue_from_beats(beats)


def create_agent_run(
    db: Session,
    project: dbm.Project,
    payload: AgentAdaptRequest,
    *,
    provider: LLMProvider | None = None,
    provider_error: str | None = None,
) -> dbm.AgentRun:
    base_version = (
        get_version_or_404(db, project.id, payload.base_version_id)
        if payload.base_version_id
        else latest_version(db, project.id)
    )
    if base_version is None:
        raise HTTPException(404, "no script version yet")

    model = "local-rule-patch-v1"
    error_message = provider_error
    if provider is None:
        patch = _fallback_patch(base_version, payload.instruction, payload.scene_ids)
        plan = [
            "读取当前剧本版本和用户选择范围。",
            "当前没有可用模型，先把改编需求写入目标场景的 adaptation_notes。",
            "等待用户确认后生成新的剧本版本。",
        ]
    else:
        try:
            plan, patch = _build_model_patch(
                db,
                project,
                base_version,
                payload.instruction,
                payload.scene_ids,
                provider,
            )
            model = "openai-compatible-agent"
        except Exception as e:  # noqa: BLE001
            error_message = f"模型改编失败，已使用本地建议：{e}"
            patch = _fallback_patch(base_version, payload.instruction, payload.scene_ids)
            plan = [
                "读取当前剧本版本和用户选择范围。",
                "模型改编失败，已保留本地可审阅建议。",
                "等待用户确认后生成新的剧本版本。",
            ]
    run = dbm.AgentRun(
        id=gen_id("agent"),
        project=project,
        base_version_id=base_version.id,
        user_prompt=payload.instruction.strip(),
        selected_context={"scene_ids": payload.scene_ids},
        plan=plan,
        patch=patch,
        status="waiting_review",
        model=model,
        error_message=error_message,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_agent_run_or_404(db: Session, run_id: str) -> dbm.AgentRun:
    run = db.get(dbm.AgentRun, run_id)
    if not run:
        raise HTTPException(404, "agent run not found")
    return run


def accept_agent_run(
    db: Session, run: dbm.AgentRun, patch_indexes: list[int] | None = None
) -> dbm.ScriptVersion:
    if run.status != "waiting_review":
        raise HTTPException(400, f"agent run cannot be accepted from status {run.status}")

    project = db.get(dbm.Project, run.project_id)
    if not project:
        raise HTTPException(404, "project not found")
    base_version = get_version_or_404(db, run.project_id, run.base_version_id)
    selected_patch = _select_patch_items(run.patch or [], patch_indexes)
    next_data = _apply_set_patch(base_version.json_content, selected_patch)
    yaml_content = to_yaml(next_data)
    selection_note = (
        f"（接受 {len(selected_patch)}/{len(run.patch or [])} 项）"
        if patch_indexes is not None
        else ""
    )
    version = create_version_from_yaml(
        db,
        project,
        yaml_content,
        source_type="agent_adaptation",
        label="AI 改编",
        notes=f"用户需求：{run.user_prompt}{selection_note}",
        parent_version_id=base_version.id,
        edit_type="ai_patch",
        edit_patch={
            "agent_run_id": run.id,
            "accepted_patch_indexes": patch_indexes,
            "patch": selected_patch,
        },
        actor_type="agent",
    )
    run.status = "accepted"
    run.result_version_id = version.id
    db.commit()
    db.refresh(run)
    return version


def retry_agent_run(
    db: Session,
    run: dbm.AgentRun,
    *,
    provider: LLMProvider | None = None,
    provider_error: str | None = None,
) -> dbm.AgentRun:
    project = db.get(dbm.Project, run.project_id)
    if not project:
        raise HTTPException(404, "project not found")
    scene_ids = []
    if isinstance(run.selected_context, dict):
        raw_scene_ids = run.selected_context.get("scene_ids") or []
        if isinstance(raw_scene_ids, list):
            scene_ids = [str(item) for item in raw_scene_ids]
    return create_agent_run(
        db,
        project,
        AgentAdaptRequest(
            instruction=run.user_prompt,
            base_version_id=run.base_version_id,
            scene_ids=scene_ids,
        ),
        provider=provider,
        provider_error=provider_error,
    )


def reject_agent_run(db: Session, run: dbm.AgentRun) -> dbm.AgentRun:
    if run.status != "waiting_review":
        raise HTTPException(400, f"agent run cannot be rejected from status {run.status}")

    run.status = "rejected"
    db.commit()
    db.refresh(run)
    return run
