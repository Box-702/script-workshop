"""User account utilities."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from .. import db as dbm
from .deps import CurrentUser, DbSession, _clean_local_user_id

router = APIRouter(prefix="/api", tags=["users"])


@router.post("/user/import-local-data")
def import_local_data(
    db: DbSession,
    current_user: CurrentUser,
    local_user_id: Annotated[str | None, Header(alias="X-Local-User-Id")] = None,
) -> dict[str, int]:
    source_user_id = _clean_local_user_id(local_user_id)
    target_user_id = current_user.id
    if target_user_id == source_user_id or target_user_id.startswith("local_"):
        raise HTTPException(400, "login before importing local data")

    project_count = (
        db.query(dbm.Project)
        .filter_by(owner_id=source_user_id)
        .update({dbm.Project.owner_id: target_user_id}, synchronize_session=False)
    )
    edit_event_count = (
        db.query(dbm.EditEvent)
        .filter_by(actor_id=source_user_id)
        .update({dbm.EditEvent.actor_id: target_user_id}, synchronize_session=False)
    )

    local_keys = db.query(dbm.UserModelKey).filter_by(user_id=source_user_id).all()
    active_providers = {key.provider for key in local_keys if key.status == "active"}
    if active_providers:
        (
            db.query(dbm.UserModelKey)
            .filter(
                dbm.UserModelKey.user_id == target_user_id,
                dbm.UserModelKey.status == "active",
                dbm.UserModelKey.provider.in_(active_providers),
            )
            .update({dbm.UserModelKey.status: "revoked"}, synchronize_session=False)
        )
    for key in local_keys:
        key.user_id = target_user_id

    db.commit()
    return {
        "projects": project_count,
        "edit_events": edit_event_count,
        "model_keys": len(local_keys),
    }
