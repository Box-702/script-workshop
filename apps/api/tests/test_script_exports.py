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
    assert "## 场景" in markdown_response.text
    assert "### 第 1 场：Knock" in markdown_response.text
    assert "**场景信息：** Clinic" in markdown_response.text
    assert "**Doctor**：We are closed." in markdown_response.text
    assert "## Scenes" not in markdown_response.text


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


def test_version_diff_compares_requested_snapshot_to_latest():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    first = create_version_from_yaml(db, project, VALID_SCRIPT_YAML, label="First")
    second_yaml = (
        VALID_SCRIPT_YAML
        .replace("Smoke Script", "Second Script")
        .replace("Open the story.", "Make the opening more urgent.")
        .replace("Rain hits the door.", "Rain hammers the clinic door.")
    )
    second = create_version_from_yaml(db, project, second_yaml, label="Second")
    client = _client(db)

    response = client.get(f"/api/projects/{project.id}/diff?from={first.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["from_version_id"] == first.id
    assert data["to_version_id"] == second.id
    labels = [item["label"] for item in data["items"]]
    assert "标题" in labels
    assert any("目的" in label for label in labels)
    assert any("动作" in label for label in labels)
    assert data["summary"]["剧本"] >= 1
    assert data["summary"]["场景"] >= 1


def test_version_diff_hides_other_users_projects():
    db = _session()
    project = Project(
        id="proj_private",
        owner_id="user_b",
        title="Private",
        adaptation_type="short_drama",
    )
    db.add(project)
    db.commit()
    version = create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    client = _client(db)

    response = client.get(
        f"/api/projects/{project.id}/diff?from={version.id}",
        headers={"X-Dev-User-Id": "user_a"},
    )

    assert response.status_code == 404


def test_script_routes_hide_other_users_projects():
    db = _session()
    project = Project(
        id="proj_private",
        owner_id="user_b",
        title="Private",
        adaptation_type="short_drama",
    )
    db.add(project)
    db.commit()
    version = create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    client = _client(db)
    headers = {"X-Dev-User-Id": "user_a"}

    assert client.get(f"/api/projects/{project.id}/script.json", headers=headers).status_code == 404
    assert client.get(f"/api/projects/{project.id}/versions", headers=headers).status_code == 404
    assert (
        client.get(
            f"/api/projects/{project.id}/versions/{version.id}/script.md",
            headers=headers,
        ).status_code
        == 404
    )
