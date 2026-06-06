"""Script version endpoints."""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import PlainTextResponse, Response

from .. import db as dbm
from ..schemas import (
    EditEventOut,
    ScriptVersionDetail,
    ScriptVersionDiffOut,
    ScriptVersionJsonSaveRequest,
    ScriptVersionOut,
    ScriptVersionSaveRequest,
)
from ..services.diff import compare_script_versions
from ..services.exports import script_to_json_text, script_to_markdown
from ..services.versions import (
    create_version_from_yaml,
    get_project_or_404,
    get_version_or_404,
    latest_version,
    restore_version,
)
from ..yaml_io import to_yaml
from .deps import CurrentUser, DbSession

router = APIRouter(prefix="/api", tags=["scripts"])


def _version_out(version: dbm.ScriptVersion) -> ScriptVersionOut:
    return ScriptVersionOut(
        id=version.id,
        project_id=version.project_id,
        parent_version_id=version.parent_version_id,
        source_type=version.source_type,
        label=version.label,
        notes=version.notes,
        validation_status=version.validation_status,
        validation_errors=version.validation_errors,
        created_at=version.created_at.isoformat(),
    )


def _version_detail(version: dbm.ScriptVersion) -> ScriptVersionDetail:
    return ScriptVersionDetail(
        **_version_out(version).model_dump(),
        yaml_content=version.yaml_content,
    )


def _edit_event_out(event: dbm.EditEvent) -> EditEventOut:
    return EditEventOut(
        id=event.id,
        project_id=event.project_id,
        version_id=event.version_id,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        edit_type=event.edit_type,
        target_path=event.target_path,
        before_snapshot=event.before_snapshot,
        after_snapshot=event.after_snapshot,
        patch=event.patch,
        note=event.note,
        created_at=event.created_at.isoformat(),
    )


@router.get("/projects/{project_id}/script.yaml")
def get_latest_yaml(project_id: str, db: DbSession, current_user: CurrentUser) -> Any:
    get_project_or_404(db, project_id, user_id=current_user.id)
    version = latest_version(db, project_id)
    if not version:
        raise HTTPException(404, "no script version yet")
    return PlainTextResponse(version.yaml_content, media_type="text/yaml")


@router.get("/projects/{project_id}/script.json")
def get_latest_json(project_id: str, db: DbSession, current_user: CurrentUser) -> Any:
    get_project_or_404(db, project_id, user_id=current_user.id)
    version = latest_version(db, project_id)
    if not version:
        raise HTTPException(404, "no script version yet")
    return Response(script_to_json_text(version.json_content), media_type="application/json")


@router.get("/projects/{project_id}/script.md")
def get_latest_markdown(project_id: str, db: DbSession, current_user: CurrentUser) -> Any:
    get_project_or_404(db, project_id, user_id=current_user.id)
    version = latest_version(db, project_id)
    if not version:
        raise HTTPException(404, "no script version yet")
    return PlainTextResponse(script_to_markdown(version.json_content), media_type="text/markdown")


@router.get("/projects/{project_id}/versions", response_model=list[ScriptVersionOut])
def list_versions(
    project_id: str, db: DbSession, current_user: CurrentUser
) -> list[ScriptVersionOut]:
    get_project_or_404(db, project_id, user_id=current_user.id)
    versions = (
        db.query(dbm.ScriptVersion)
        .filter_by(project_id=project_id)
        .order_by(dbm.ScriptVersion.created_at.desc())
        .all()
    )
    return [_version_out(version) for version in versions]


@router.get("/projects/{project_id}/diff", response_model=ScriptVersionDiffOut)
def diff_versions(
    project_id: str,
    db: DbSession,
    current_user: CurrentUser,
    from_version_id: Annotated[str, Query(alias="from")],
    to_version_id: Annotated[str | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    get_project_or_404(db, project_id, user_id=current_user.id)
    from_version = get_version_or_404(db, project_id, from_version_id)
    if to_version_id:
        to_version = get_version_or_404(db, project_id, to_version_id)
    else:
        to_version = latest_version(db, project_id)
    if not to_version:
        raise HTTPException(404, "target script version not found")
    return compare_script_versions(from_version, to_version)


@router.get("/projects/{project_id}/edits", response_model=list[EditEventOut])
def list_edit_events(
    project_id: str, db: DbSession, current_user: CurrentUser, limit: int = 50
) -> list[EditEventOut]:
    get_project_or_404(db, project_id, user_id=current_user.id)
    safe_limit = max(1, min(limit, 200))
    events = (
        db.query(dbm.EditEvent)
        .filter_by(project_id=project_id)
        .order_by(dbm.EditEvent.created_at.desc())
        .limit(safe_limit)
        .all()
    )
    return [_edit_event_out(event) for event in events]


@router.post("/projects/{project_id}/versions", response_model=ScriptVersionDetail)
def save_version(
    project_id: str,
    payload: ScriptVersionSaveRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> ScriptVersionDetail:
    project = get_project_or_404(db, project_id, user_id=current_user.id)
    version = create_version_from_yaml(
        db,
        project,
        payload.yaml,
        source_type="manual",
        label=payload.label,
        notes=payload.notes,
    )
    return _version_detail(version)


@router.post("/projects/{project_id}/versions/json", response_model=ScriptVersionDetail)
def save_version_json(
    project_id: str,
    payload: ScriptVersionJsonSaveRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> ScriptVersionDetail:
    project = get_project_or_404(db, project_id, user_id=current_user.id)
    version = create_version_from_yaml(
        db,
        project,
        to_yaml({"script": payload.script}),
        source_type="manual",
        label=payload.label,
        notes=payload.notes,
        edit_patch={"source_type": "structured_editor"},
    )
    return _version_detail(version)


@router.get(
    "/projects/{project_id}/versions/{version_id}",
    response_model=ScriptVersionDetail,
)
def get_version(
    project_id: str, version_id: str, db: DbSession, current_user: CurrentUser
) -> ScriptVersionDetail:
    get_project_or_404(db, project_id, user_id=current_user.id)
    version = get_version_or_404(db, project_id, version_id)
    return _version_detail(version)


@router.get("/projects/{project_id}/versions/{version_id}/script.yaml")
def get_version_yaml(
    project_id: str, version_id: str, db: DbSession, current_user: CurrentUser
) -> Any:
    get_project_or_404(db, project_id, user_id=current_user.id)
    version = get_version_or_404(db, project_id, version_id)
    return PlainTextResponse(version.yaml_content, media_type="text/yaml")


@router.get("/projects/{project_id}/versions/{version_id}/script.json")
def get_version_json(
    project_id: str, version_id: str, db: DbSession, current_user: CurrentUser
) -> Any:
    get_project_or_404(db, project_id, user_id=current_user.id)
    version = get_version_or_404(db, project_id, version_id)
    return Response(script_to_json_text(version.json_content), media_type="application/json")


@router.get("/projects/{project_id}/versions/{version_id}/script.md")
def get_version_markdown(
    project_id: str, version_id: str, db: DbSession, current_user: CurrentUser
) -> Any:
    get_project_or_404(db, project_id, user_id=current_user.id)
    version = get_version_or_404(db, project_id, version_id)
    return PlainTextResponse(script_to_markdown(version.json_content), media_type="text/markdown")


@router.post(
    "/projects/{project_id}/versions/{version_id}/restore",
    response_model=ScriptVersionDetail,
)
def restore_script_version(
    project_id: str, version_id: str, db: DbSession, current_user: CurrentUser
) -> ScriptVersionDetail:
    project = get_project_or_404(db, project_id, user_id=current_user.id)
    version = get_version_or_404(db, project_id, version_id)
    restored = restore_version(db, project, version)
    return _version_detail(restored)
