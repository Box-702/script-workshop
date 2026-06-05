from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Chapter, GenerationRun, Project, ScriptVersion
from app.routers.projects import _project_detail, _project_out


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


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
