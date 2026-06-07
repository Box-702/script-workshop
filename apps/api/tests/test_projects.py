from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_versions import VALID_SCRIPT_YAML

from app.db import Base, Chapter, EditEvent, GenerationRun, Project, ScriptVersion
from app.routers import projects
from app.routers.deps import get_db
from app.routers.projects import (
    LLMRunOptions,
    _options_for_project_language,
    _project_detail,
    _project_out,
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
    app.include_router(projects.router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_project_summary_includes_counts_and_latest_state():
    db = _session()
    project = Project(
        id="proj_test",
        title="Test",
        adaptation_type="short_drama",
        language="en-US",
    )
    db.add(project)
    db.add_all(
        [
            Chapter(
                id="chapter_001",
                project_id=project.id,
                title="One",
                content="chapter one",
                order_index=0,
            ),
            ScriptVersion(
                id="ver_old",
                project_id=project.id,
                yaml_content="script: {}",
                json_content={"script": {}},
                source_type="generation",
                label="Old",
                validation_status="valid",
                validation_errors=[],
            ),
            ScriptVersion(
                id="ver_current",
                project_id=project.id,
                yaml_content="script: {}",
                json_content={"script": {}},
                source_type="manual",
                label="Current",
                validation_status="invalid",
                validation_errors=[{"path": "script", "message": "missing fields"}],
            ),
            GenerationRun(
                id="run_test",
                project_id=project.id,
                status="done",
                current_step="done",
                progress=100,
            ),
        ]
    )
    project.current_version_id = "ver_current"
    db.commit()
    db.refresh(project)

    summary = _project_out(db, project)

    assert summary.chapter_count == 1
    assert summary.owner_id == "local_user"
    assert summary.current_version_id == "ver_current"
    assert summary.version_count == 2
    assert summary.latest_version is not None
    assert summary.latest_version.id == "ver_current"
    assert summary.latest_version.source_type == "manual"
    assert summary.latest_version.label == "Current"
    assert summary.latest_version.validation_status == "invalid"
    assert summary.latest_run is not None
    assert summary.latest_run.status == "done"


def test_project_detail_includes_ordered_chapters():
    db = _session()
    project = Project(
        id="proj_test",
        title="Test",
        adaptation_type="short_drama",
        language="en-US",
    )
    db.add(project)
    db.add_all(
        [
            Chapter(
                id="chapter_002",
                project_id=project.id,
                title="Two",
                content="two",
                order_index=1,
            ),
            Chapter(
                id="chapter_001",
                project_id=project.id,
                title="One",
                content="one",
                order_index=0,
            ),
        ]
    )
    db.commit()
    db.refresh(project)

    detail = _project_detail(db, project)

    assert [chapter.id for chapter in detail.chapters] == ["chapter_001", "chapter_002"]


def test_delete_project_removes_project_assets():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.add_all(
        [
            Chapter(
                id="chapter_001",
                project_id=project.id,
                title="One",
                content="one",
                order_index=0,
            ),
            GenerationRun(
                id="run_test",
                project_id=project.id,
                status="failed",
                current_step="failed",
                progress=10,
            ),
            ScriptVersion(
                id="ver_test",
                project_id=project.id,
                yaml_content="script: {}",
                json_content={"script": {}},
                source_type="generation",
                label="AI generated draft",
                validation_status="valid",
                validation_errors=[],
            ),
            EditEvent(
                id="edit_test",
                project_id=project.id,
                version_id="ver_test",
                actor_type="user",
                edit_type="manual_save",
                target_path="script",
            ),
        ]
    )
    db.commit()
    client = _client(db)

    response = client.delete(f"/api/projects/{project.id}")

    assert response.status_code == 204
    assert db.get(Project, project.id) is None
    assert db.query(Chapter).count() == 0
    assert db.query(GenerationRun).count() == 0
    assert db.query(ScriptVersion).count() == 0
    assert db.query(EditEvent).count() == 0


def test_project_routes_are_scoped_to_current_user():
    db = _session()
    own = Project(
        id="proj_own",
        owner_id="user_a",
        title="Own",
        adaptation_type="short_drama",
        language="en-US",
    )
    other = Project(
        id="proj_other",
        owner_id="user_b",
        title="Other",
        adaptation_type="short_drama",
        language="en-US",
    )
    db.add_all([own, other])
    db.commit()
    client = _client(db)

    listed = client.get("/api/projects", headers={"X-Dev-User-Id": "user_a"})

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == ["proj_own"]

    own_detail = client.get("/api/projects/proj_own", headers={"X-Dev-User-Id": "user_a"})
    other_detail = client.get("/api/projects/proj_other", headers={"X-Dev-User-Id": "user_a"})

    assert own_detail.status_code == 200
    assert other_detail.status_code == 404


def test_generation_options_use_resolved_project_language():
    options = LLMRunOptions(openai_api_key="sk-test", language="")

    resolved = _options_for_project_language(options, "zh-CN")

    assert resolved.language == "zh-CN"
    assert resolved.openai_api_key == options.openai_api_key


def test_import_script_project_creates_snapshot_without_generation_run():
    db = _session()
    client = _client(db)

    response = client.post(
        "/api/projects/import-script",
        json={"content": VALID_SCRIPT_YAML, "format": "yaml"},
    )

    assert response.status_code == 200
    data = response.json()
    project = db.get(Project, data["project_id"])
    assert project is not None
    assert project.title == "Smoke Script"
    assert project.status == "ready"
    assert project.current_version_id == data["version_id"]
    assert len(project.chapters) == 3
    assert db.query(GenerationRun).count() == 0

    version = db.get(ScriptVersion, data["version_id"])
    assert version is not None
    assert version.source_type == "import"
    assert version.label == "导入剧本源码"
    assert version.json_content["script"]["title"] == "Smoke Script"

    event = db.query(EditEvent).filter_by(version_id=version.id).one()
    assert event.edit_type == "import"
