from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.routers import deps


def _settings(auth_mode="local"):
    return SimpleNamespace(
        auth_mode=auth_mode,
        supabase_url="https://project.supabase.co",
        supabase_anon_key="anon-key",
    )


def test_current_user_defaults_to_local_user(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: _settings())

    user = deps.get_current_user()

    assert user.id == "local_user"


def test_current_user_uses_dev_user_header_in_local_mode(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: _settings())

    user = deps.get_current_user(dev_user_id="user_a")

    assert user.id == "user_a"


def test_supabase_mode_requires_bearer_token(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: _settings(auth_mode="supabase"))

    with pytest.raises(HTTPException) as exc_info:
        deps.get_current_user()

    assert exc_info.value.status_code == 401
    assert "bearer" in exc_info.value.detail


def test_supabase_mode_uses_verified_user_id(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: _settings(auth_mode="supabase"))
    monkeypatch.setattr(deps, "_fetch_supabase_user", lambda token: {"id": f"user_{token}"})

    user = deps.get_current_user(authorization="Bearer access-token")

    assert user.id == "user_access-token"


def test_supabase_mode_rejects_user_response_without_id(monkeypatch):
    monkeypatch.setattr(deps, "get_settings", lambda: _settings(auth_mode="supabase"))
    monkeypatch.setattr(deps, "_fetch_supabase_user", lambda token: {})

    with pytest.raises(HTTPException) as exc_info:
        deps.get_current_user(authorization="Bearer access-token")

    assert exc_info.value.status_code == 401
