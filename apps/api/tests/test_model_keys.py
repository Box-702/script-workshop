from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.routers import model_keys
from app.routers.deps import get_db
from app.routers.projects import LLMRunOptions, _fill_options_from_saved_key
from app.services.model_keys import (
    create_model_key,
    decrypt_model_key,
    get_active_model_key,
    open_secret,
    seal_secret,
)


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def _client(db):
    app = FastAPI()
    app.include_router(model_keys.router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_secret_seal_roundtrip_hides_plaintext():
    sealed = seal_secret("sk-test-secret")

    assert "sk-test-secret" not in sealed
    assert open_secret(sealed) == "sk-test-secret"


def test_create_model_key_encrypts_and_replaces_active_key():
    db = _session()

    first = create_model_key(
        db,
        provider="openai",
        api_key="sk-first-secret",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    second = create_model_key(
        db,
        provider="openai",
        api_key="sk-second-secret",
        base_url="https://example.test/v1",
        model="gpt-4.1-mini",
    )

    db.refresh(first)
    active = get_active_model_key(db)

    assert first.status == "revoked"
    assert second.status == "active"
    assert active is not None
    assert active.id == second.id
    assert "sk-second-secret" not in second.encrypted_api_key
    assert decrypt_model_key(second).api_key == "sk-second-secret"


def test_create_model_key_rejects_masked_or_too_short_key():
    db = _session()

    for value in ("3000", "****3000", "https://api.openai.com/v1"):
        try:
            create_model_key(
                db,
                provider="openai",
                api_key=value,
                base_url="https://api.openai.com/v1",
                model="gpt-4o-mini",
            )
        except Exception as exc:  # noqa: BLE001
            assert "API key" in str(exc)
        else:  # pragma: no cover
            raise AssertionError(f"expected invalid key to be rejected: {value}")


def test_fill_options_from_saved_key_uses_active_key_when_header_is_missing():
    db = _session()
    create_model_key(
        db,
        provider="openai",
        api_key="sk-saved-secret",
        base_url="https://example.test/v1",
        model="gpt-4.1-mini",
    )

    options = _fill_options_from_saved_key(db, LLMRunOptions(provider="openai"))

    assert options.openai_api_key == "sk-saved-secret"
    assert options.openai_base_url == "https://example.test/v1"
    assert options.openai_model == "gpt-4.1-mini"


def test_fill_options_from_saved_key_prefers_request_key():
    db = _session()
    create_model_key(
        db,
        provider="openai",
        api_key="sk-saved-secret",
        base_url="https://saved.test/v1",
        model="saved-model",
    )

    options = _fill_options_from_saved_key(
        db,
        LLMRunOptions(
            provider="openai",
            openai_api_key="sk-request-secret",
            openai_base_url="https://request.test/v1",
            openai_model="request-model",
        ),
    )

    assert options.openai_api_key == "sk-request-secret"
    assert options.openai_base_url == "https://request.test/v1"
    assert options.openai_model == "request-model"


def test_model_key_api_lists_active_tests_and_revokes_key():
    db = _session()
    client = _client(db)

    saved = client.post(
        "/api/user/model-keys",
        json={
            "provider": "openai",
            "api_key": "sk-api-secret",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
    )
    assert saved.status_code == 200
    key_id = saved.json()["id"]

    active = client.get("/api/user/model-keys/active")
    assert active.status_code == 200
    assert active.json()["id"] == key_id
    assert active.json()["key_last4"] == "cret"

    tested = client.post(f"/api/user/model-keys/{key_id}/test")
    assert tested.status_code == 200
    assert tested.json()["ok"] is True
    assert "格式可用" in tested.json()["message"]

    revoked = client.delete(f"/api/user/model-keys/{key_id}")
    assert revoked.status_code == 200
    assert revoked.json()["ok"] is True

    listed = client.get("/api/user/model-keys")
    assert listed.status_code == 200
    assert listed.json()[0]["status"] == "revoked"


def test_model_key_api_is_scoped_to_current_user():
    db = _session()
    create_model_key(
        db,
        user_id="user_a",
        provider="openai",
        api_key="sk-user-a-secret",
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
    )
    key_b = create_model_key(
        db,
        user_id="user_b",
        provider="openai",
        api_key="sk-user-b-secret",
        base_url="https://example.test/v1",
        model="gpt-4.1-mini",
    )
    client = _client(db)

    listed = client.get("/api/user/model-keys", headers={"X-Dev-User-Id": "user_a"})
    active = client.get("/api/user/model-keys/active", headers={"X-Dev-User-Id": "user_a"})
    tested = client.post(
        f"/api/user/model-keys/{key_b.id}/test",
        headers={"X-Dev-User-Id": "user_a"},
    )
    revoked = client.delete(
        f"/api/user/model-keys/{key_b.id}",
        headers={"X-Dev-User-Id": "user_a"},
    )

    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["key_last4"] == "cret"
    assert active.status_code == 200
    assert active.json()["base_url"] == "https://api.openai.com/v1"
    assert tested.status_code == 200
    assert tested.json()["ok"] is False
    assert revoked.status_code == 404
