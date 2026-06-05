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


def test_latest_script_json_and_markdown_exports():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    client = _client(db)

    json_response = client.get(f"/api/projects/{project.id}/script.json")
    assert json_response.status_code == 200
    assert json_response.headers["content-type"].startswith("application/json")
    assert json_response.json()["script"]["title"] == "Smoke Script"

    markdown_response = client.get(f"/api/projects/{project.id}/script.md")
    assert markdown_response.status_code == 200
    assert markdown_response.headers["content-type"].startswith("text/markdown")
    assert "# Smoke Script" in markdown_response.text
    assert "## Scenes" in markdown_response.text
    assert "**Doctor**: We are closed." in markdown_response.text


def test_version_markdown_export_uses_requested_version():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    first = create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    second_yaml = VALID_SCRIPT_YAML.replace("Smoke Script", "Second Script")
    create_version_from_yaml(db, project, second_yaml)
    client = _client(db)

    response = client.get(f"/api/projects/{project.id}/versions/{first.id}/script.md")

    assert response.status_code == 200
    assert "# Smoke Script" in response.text
    assert "# Second Script" not in response.text


def test_save_structured_json_creates_version():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    client = _client(db)

    base = client.get(f"/api/projects/{project.id}/script.json").json()["script"]
    base["title"] = "Structured Save"
    base["scenes"][0]["purpose"] = "Show the structured editor save path."

    saved = client.post(
        f"/api/projects/{project.id}/versions/json",
        json={"script": base, "label": "结构化保存", "notes": "Saved from structured editor."},
    )

    assert saved.status_code == 200
    assert saved.json()["label"] == "结构化保存"
    assert "Structured Save" in saved.json()["yaml_content"]
    latest = client.get(f"/api/projects/{project.id}/script.json")
    assert latest.json()["script"]["title"] == "Structured Save"
