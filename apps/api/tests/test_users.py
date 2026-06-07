from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import db as dbm
from app.db import Base
from app.routers import deps, users
from app.routers.deps import get_db
from app.services.model_keys import create_model_key


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


def _client(db, monkeypatch):
    app = FastAPI()
    app.include_router(users.router)

    def override_get_db():
        yield db

    monkeypatch.setattr(
        deps,
        "get_settings",
        lambda: SimpleNamespace(
            auth_mode="hybrid",
            supabase_url="https://project.supabase.co",
            supabase_anon_key="anon-key",
        ),
    )
    monkeypatch.setattr(deps, "_fetch_supabase_user", lambda token: {"id": "cloud_user"})
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_import_local_data_moves_browser_data_to_current_user(monkeypatch):
    db = _session()
    client = _client(db, monkeypatch)
    local_user_id = "local_browser"

    db.add(dbm.Project(id="proj_local", owner_id=local_user_id, title="Local story"))
    db.add(
        dbm.EditEvent(
            id="edit_local",
            project_id="proj_local",
            actor_id=local_user_id,
            edit_type="manual_save",
        )
    )
    create_model_key(
        db,
        user_id="cloud_user",
        provider="openai",
        api_key="sk-cloud-secret",
        base_url="https://cloud.test/v1",
        model="cloud-model",
    )
    local_key = create_model_key(
        db,
        user_id=local_user_id,
        provider="openai",
        api_key="sk-local-secret",
        base_url="https://local.test/v1",
        model="local-model",
    )

    response = client.post(
        "/api/user/import-local-data",
        headers={
            "Authorization": "Bearer access-token",
            "X-Local-User-Id": local_user_id,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"projects": 1, "edit_events": 1, "model_keys": 1}
    assert db.get(dbm.Project, "proj_local").owner_id == "cloud_user"
    assert db.get(dbm.EditEvent, "edit_local").actor_id == "cloud_user"
    db.refresh(local_key)
    assert local_key.user_id == "cloud_user"
    assert local_key.status == "active"
    active_keys = (
        db.query(dbm.UserModelKey)
        .filter_by(user_id="cloud_user", provider="openai", status="active")
        .all()
    )
    assert [key.id for key in active_keys] == [local_key.id]


def test_import_local_data_requires_logged_in_user(monkeypatch):
    db = _session()
    client = _client(db, monkeypatch)

    response = client.post(
        "/api/user/import-local-data",
        headers={"X-Local-User-Id": "local_browser"},
    )

    assert response.status_code == 400
