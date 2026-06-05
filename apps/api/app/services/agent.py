from __future__ import annotations

from copy import deepcopy
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import db as dbm
from ..ids import gen_id
from ..schemas import AgentAdaptRequest
from ..yaml_io import to_yaml
from .versions import create_version_from_yaml, get_version_or_404, latest_version


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


def _build_patch(version: dbm.ScriptVersion, instruction: str, scene_ids: list[str]) -> list[dict]:
    patch: list[dict] = []
    for idx in _selected_scene_indexes(version, scene_ids):
        patch.append(
            {
                "op": "set",
                "path": f"/script/scenes/{idx}/adaptation_notes/reason",
                "value": f"AI 改编需求：{instruction.strip()}",
            }
        )
    return patch


def _apply_set_patch(data: dict[str, Any], patch: list[dict]) -> dict[str, Any]:
    next_data = deepcopy(data)
    for op in patch:
        if op.get("op") != "set":
            raise HTTPException(400, f"unsupported patch op: {op.get('op')}")
        path = str(op.get("path") or "")
        if not path.startswith("/script/scenes/") or not path.endswith(
            "/adaptation_notes/reason"
        ):
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
        notes = scene.setdefault("adaptation_notes", {})
        notes["reason"] = op.get("value", "")
        notes.setdefault("fidelity", "reordered")
    return next_data


def create_agent_run(
    db: Session, project: dbm.Project, payload: AgentAdaptRequest
) -> dbm.AgentRun:
    base_version = (
        get_version_or_404(db, project.id, payload.base_version_id)
        if payload.base_version_id
        else latest_version(db, project.id)
    )
    if base_version is None:
        raise HTTPException(404, "no script version yet")

    patch = _build_patch(base_version, payload.instruction, payload.scene_ids)
    plan = [
        "读取当前剧本版本和用户选择范围。",
        "把改编需求写入目标场景的 adaptation_notes，保留原始场景结构。",
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
        model="local-rule-patch-v1",
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


def accept_agent_run(db: Session, run: dbm.AgentRun) -> dbm.ScriptVersion:
    if run.status != "waiting_review":
        raise HTTPException(400, f"agent run cannot be accepted from status {run.status}")

    project = db.get(dbm.Project, run.project_id)
    if not project:
        raise HTTPException(404, "project not found")
    base_version = get_version_or_404(db, run.project_id, run.base_version_id)
    next_data = _apply_set_patch(base_version.json_content, run.patch or [])
    yaml_content = to_yaml(next_data)
    version = create_version_from_yaml(
        db,
        project,
        yaml_content,
        source_type="agent_adaptation",
        label="AI 改编",
        notes=f"用户需求：{run.user_prompt}",
        parent_version_id=base_version.id,
        edit_type="ai_patch",
        edit_patch={"agent_run_id": run.id, "patch": run.patch},
        actor_type="agent",
    )
    run.status = "accepted"
    run.result_version_id = version.id
    db.commit()
    db.refresh(run)
    return version
