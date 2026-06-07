from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .. import db as dbm
from ..config import get_settings

LOCAL_USER_ID = "local_user"
LOCAL_USER_ID_PREFIX = "local_"


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


def _clean_local_user_id(value: str | None) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(401, "missing bearer token or local user id")
    if len(cleaned) > 96 or not cleaned.startswith(LOCAL_USER_ID_PREFIX):
        raise HTTPException(401, "invalid local user id")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
    if any(char not in allowed for char in cleaned):
        raise HTTPException(401, "invalid local user id")
    return cleaned


def get_current_user(
    dev_user_id: Annotated[str | None, Header(alias="X-Dev-User-Id")] = None,
    local_user_id: Annotated[str | None, Header(alias="X-Local-User-Id")] = None,
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> AuthenticatedUser:
    settings = get_settings()
    mode = (settings.auth_mode or "local").strip().lower()
    if mode == "local":
        return AuthenticatedUser(id=_clean_user_id(dev_user_id))
    if mode == "supabase":
        return _get_supabase_user(authorization)
    if mode == "hybrid":
        if _bearer_token(authorization):
            return _get_supabase_user(authorization)
        return AuthenticatedUser(id=_clean_local_user_id(local_user_id))
    raise HTTPException(500, f"unsupported AUTH_MODE: {settings.auth_mode}")


def _get_supabase_user(authorization: str | None) -> AuthenticatedUser:
    token = _bearer_token(authorization)
    if not token:
        raise HTTPException(401, "missing bearer token")
    user = _fetch_supabase_user(token)
    user_id = str(user.get("id") or "").strip()
    if not user_id:
        raise HTTPException(401, "invalid Supabase user token")
    return AuthenticatedUser(id=user_id)


def _bearer_token(authorization: str | None) -> str:
    value = (authorization or "").strip()
    prefix = "bearer "
    if not value.lower().startswith(prefix):
        return ""
    return value[len(prefix) :].strip()


def _fetch_supabase_user(token: str) -> dict:
    settings = get_settings()
    supabase_url = settings.supabase_url.rstrip("/")
    anon_key = settings.supabase_anon_key.strip()
    if not supabase_url or not anon_key:
        raise HTTPException(500, "Supabase auth is not configured")
    try:
        response = httpx.get(
            f"{supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {token}",
                "apikey": anon_key,
            },
            timeout=8,
        )
    except httpx.HTTPError as e:
        raise HTTPException(401, "Supabase auth verification failed") from e
    if response.status_code == 401 or response.status_code == 403:
        raise HTTPException(401, "invalid Supabase user token")
    if response.status_code >= 400:
        raise HTTPException(401, "Supabase auth verification failed")
    data = response.json()
    if not isinstance(data, dict):
        raise HTTPException(401, "invalid Supabase user response")
    return data


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
