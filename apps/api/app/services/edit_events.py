from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .. import db as dbm
from ..ids import gen_id

LOCAL_ACTOR_ID = "local_user"


def record_edit_event(
    db: Session,
    *,
    project: dbm.Project,
    version: dbm.ScriptVersion | None,
    edit_type: str,
    before_snapshot: Any = None,
    after_snapshot: Any = None,
    patch: Any = None,
    target_path: str = "script",
    note: str | None = None,
    actor_type: str = "user",
    actor_id: str | None = None,
) -> dbm.EditEvent:
    event = dbm.EditEvent(
        id=gen_id("edit"),
        project=project,
        version=version,
        actor_type=actor_type,
        actor_id=actor_id or project.owner_id or LOCAL_ACTOR_ID,
        edit_type=edit_type,
        target_path=target_path,
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
        patch=patch,
        note=note,
    )
    db.add(event)
    return event
