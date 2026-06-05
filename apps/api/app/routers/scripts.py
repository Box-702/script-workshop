"""Script version endpoints."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from .. import db as dbm
from ..schemas import (
    ScriptVersionDetail,
    ScriptVersionOut,
    ScriptVersionSaveRequest,
)
from ..services.versions import (
    create_version_from_yaml,
    get_project_or_404,
    get_version_or_404,
    latest_version,
    restore_version,
)
from .deps import DbSession

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


@router.get("/projects/{project_id}/script.yaml")
def get_latest_yaml(project_id: str, db: DbSession) -> Any:
    get_project_or_404(db, project_id)
    version = latest_version(db, project_id)
    if not version:
        raise HTTPException(404, "no script version yet")
    return PlainTextResponse(version.yaml_content, media_type="text/yaml")


@router.get("/projects/{project_id}/versions", response_model=list[ScriptVersionOut])
def list_versions(project_id: str, db: DbSession) -> list[ScriptVersionOut]:
    get_project_or_404(db, project_id)
    versions = (
        db.query(dbm.ScriptVersion)
        .filter_by(project_id=project_id)
        .order_by(dbm.ScriptVersion.created_at.desc())
        .all()
    )
    return [_version_out(version) for version in versions]


@router.post("/projects/{project_id}/versions", response_model=ScriptVersionDetail)
def save_version(
    project_id: str, payload: ScriptVersionSaveRequest, db: DbSession
) -> ScriptVersionDetail:
    project = get_project_or_404(db, project_id)
    version = create_version_from_yaml(
        db,
        project,
        payload.yaml,
        source_type="manual",
        label=payload.label,
        notes=payload.notes,
    )
    return _version_detail(version)


@router.get(
    "/projects/{project_id}/versions/{version_id}",
    response_model=ScriptVersionDetail,
)
def get_version(
    project_id: str, version_id: str, db: DbSession
) -> ScriptVersionDetail:
    get_project_or_404(db, project_id)
    version = get_version_or_404(db, project_id, version_id)
    return _version_detail(version)


@router.get("/projects/{project_id}/versions/{version_id}/script.yaml")
def get_version_yaml(project_id: str, version_id: str, db: DbSession) -> Any:
    get_project_or_404(db, project_id)
    version = get_version_or_404(db, project_id, version_id)
    return PlainTextResponse(version.yaml_content, media_type="text/yaml")


@router.post(
    "/projects/{project_id}/versions/{version_id}/restore",
    response_model=ScriptVersionDetail,
)
def restore_script_version(
    project_id: str, version_id: str, db: DbSession
) -> ScriptVersionDetail:
    project = get_project_or_404(db, project_id)
    version = get_version_or_404(db, project_id, version_id)
    restored = restore_version(db, project, version)
    return _version_detail(restored)
