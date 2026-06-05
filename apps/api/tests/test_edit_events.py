from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_versions import VALID_SCRIPT_YAML

from app.db import Base, Project
from app.routers import scripts
from app.routers.deps import get_db
from app.services.versions import create_version_from_yaml


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
    app.include_router(scripts.router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_list_edit_events_returns_project_history():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    version = create_version_from_yaml(
        db,
        project,
        VALID_SCRIPT_YAML,
        label="Manual edit",
        notes="Saved by user.",
    )

    response = _client(db).get(f"/api/projects/{project.id}/edits")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["project_id"] == project.id
    assert body[0]["version_id"] == version.id
    assert body[0]["edit_type"] == "manual_save"
    assert body[0]["after_snapshot"]["script"]["title"] == "Smoke Script"


def test_list_edit_events_limits_result_count():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML, label="One")
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML, label="Two")

    response = _client(db).get(f"/api/projects/{project.id}/edits?limit=1")

    assert response.status_code == 200
    assert len(response.json()) == 1
