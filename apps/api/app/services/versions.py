from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .. import db as dbm
from ..ids import gen_id
from ..validation import validate_script
from ..yaml_io import from_yaml
from .edit_events import record_edit_event


def get_project_or_404(db: Session, project_id: str) -> dbm.Project:
    project = db.get(dbm.Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    return project


def get_version_or_404(
    db: Session, project_id: str, version_id: str
) -> dbm.ScriptVersion:
    version = (
        db.query(dbm.ScriptVersion)
        .filter_by(project_id=project_id, id=version_id)
        .first()
    )
    if not version:
        raise HTTPException(404, "script version not found")
    return version


def latest_version(db: Session, project_id: str) -> dbm.ScriptVersion | None:
    project = db.get(dbm.Project, project_id)
    if project and project.current_version_id:
        current = (
            db.query(dbm.ScriptVersion)
            .filter_by(project_id=project_id, id=project.current_version_id)
            .first()
        )
        if current:
            return current
    return (
        db.query(dbm.ScriptVersion)
        .filter_by(project_id=project_id)
        .order_by(dbm.ScriptVersion.created_at.desc())
        .first()
    )


def _plain_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain_json(item) for item in value]
    return value


def parse_version_yaml(yaml_content: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        data = from_yaml(yaml_content)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"YAML parse error: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(400, "YAML root must be a mapping")

    data = _plain_json(data)
    errors = [err.model_dump() for err in validate_script(data)]
    return data, errors


def create_version_from_yaml(
    db: Session,
    project: dbm.Project,
    yaml_content: str,
    *,
    source_type: str = "manual",
    label: str | None = None,
    notes: str | None = None,
    parent_version_id: str | None = None,
    edit_type: str = "manual_save",
    edit_patch: Any = None,
    actor_type: str = "user",
) -> dbm.ScriptVersion:
    data, errors = parse_version_yaml(yaml_content)
    parent_version_id = parent_version_id or project.current_version_id
    before_version = (
        db.query(dbm.ScriptVersion)
        .filter_by(project_id=project.id, id=parent_version_id)
        .first()
        if parent_version_id
        else None
    )
    version = dbm.ScriptVersion(
        id=gen_id("ver"),
        project_id=project.id,
        parent_version_id=parent_version_id,
        source_type=source_type,
        label=label,
        notes=notes,
        yaml_content=yaml_content,
        json_content=data,
        validation_status="valid" if not errors else "invalid",
        validation_errors=errors,
    )
    db.add(version)
    record_edit_event(
        db,
        project=project,
        version=version,
        edit_type=edit_type,
        before_snapshot=before_version.json_content if before_version else None,
        after_snapshot=data,
        patch=edit_patch
        or {
            "source_type": source_type,
            "validation_status": "valid" if not errors else "invalid",
        },
        note=notes or label,
        actor_type=actor_type,
    )
    project.status = "ready" if not errors else "needs_review"
    project.current_version_id = version.id
    db.commit()
    db.refresh(version)
    return version


def restore_version(
    db: Session, project: dbm.Project, version: dbm.ScriptVersion
) -> dbm.ScriptVersion:
    before_version = latest_version(db, project.id)
    source_label = version.label or version.id
    restored = dbm.ScriptVersion(
        id=gen_id("ver"),
        project_id=project.id,
        parent_version_id=version.id,
        source_type="restore",
        label=f"回退到：{source_label}",
        notes=f"从快照「{source_label}」回退。",
        yaml_content=version.yaml_content,
        json_content=version.json_content,
        validation_status=version.validation_status,
        validation_errors=version.validation_errors,
    )
    db.add(restored)
    record_edit_event(
        db,
        project=project,
        version=restored,
        edit_type="restore",
        before_snapshot=before_version.json_content if before_version else None,
        after_snapshot=restored.json_content,
        patch={"restored_from_version_id": version.id},
        note=restored.notes,
    )
    project.status = "ready" if restored.validation_status == "valid" else "needs_review"
    project.current_version_id = restored.id
    db.commit()
    db.refresh(restored)
    return restored
