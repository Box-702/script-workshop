from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import db as dbm
from ..ids import gen_id
from ..providers.base import LLMProvider, Stage
from ..schemas import AgentAdaptRequest
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
}

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


def _build_agent_prompt(
    version: dbm.ScriptVersion, instruction: str, scene_ids: list[str]
) -> tuple[str, list[int]]:
    data = version.json_content
    script = data.get("script", {})
    scenes = script.get("scenes", [])
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
    context = {
        "script": {
            "title": script.get("title"),
            "language": script.get("language"),
            "logline": script.get("logline"),
            "themes": script.get("themes"),
        },
        "characters": characters,
        "locations": locations,
        "selected_scenes": [scenes[idx] for idx in selected_indexes],
    }
    prompt = f"""
你是剧本改编助手。请只改 selected_scenes 中的场景，不要新增场景、角色或地点。
用户改编需求：{instruction.strip()}

请输出 JSON：
- plan: 1-6 条中文计划，说明你将如何改。
- changes: 每个被修改场景一项，scene_id 必须来自 {sorted(selected_scene_ids)}。
- 只返回真正需要更新的字段；没有必要改的字段不要返回。
- dialogue 中 speaker 必须使用该场景已有 characters 列表里的角色 id。
- action 和 dialogue 如果返回，会整体替换该场景对应列表。
- adaptation_reason 要说明这次改编为什么这么做。

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

        if "action" in change:
            action = _clean_action(change.get("action"))
            if action is not None:
                op = _make_set_op(
                    scene_index=idx,
                    scene=scene,
                    field="action",
                    before=scene.get("action") or [],
                    after=action,
                )
                if op:
                    patch.append(op)

        if "dialogue" in change:
            dialogue = _clean_dialogue(change.get("dialogue"), allowed_speakers)
            if dialogue is not None:
                op = _make_set_op(
                    scene_index=idx,
                    scene=scene,
                    field="dialogue",
                    before=scene.get("dialogue") or [],
                    after=dialogue,
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
    version: dbm.ScriptVersion,
    instruction: str,
    scene_ids: list[str],
    provider: LLMProvider,
) -> tuple[list[str], list[dict[str, Any]]]:
    prompt, selected_indexes = _build_agent_prompt(version, instruction, scene_ids)
    response = provider.generate_structured(prompt, AGENT_RESPONSE_SCHEMA, stage=Stage.AGENT)
    return _patch_from_agent_response(version, response, selected_indexes, instruction)


def _apply_set_patch(data: dict[str, Any], patch: list[dict]) -> dict[str, Any]:
    next_data = deepcopy(data)
    for op in patch:
        if op.get("op") != "set":
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
        if len(field_path) == 1 and field_path[0] in EDITABLE_SCENE_FIELDS:
            scene[field_path[0]] = op.get("value")
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
