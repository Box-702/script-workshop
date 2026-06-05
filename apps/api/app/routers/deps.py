from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from .. import db as dbm

LOCAL_USER_ID = "local_user"


def get_db():
    session = dbm.SessionLocal()
    try:
        yield session
    finally:
        session.close()


DbSession = Annotated[Session, Depends(get_db)]


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str


def _clean_user_id(value: str | None) -> str:
    cleaned = (value or "").strip()
    return cleaned or LOCAL_USER_ID


def get_current_user(
    dev_user_id: Annotated[str | None, Header(alias="X-Dev-User-Id")] = None,
) -> AuthenticatedUser:
    return AuthenticatedUser(id=_clean_user_id(dev_user_id))


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
