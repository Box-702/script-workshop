from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Project
from app.services.versions import create_version_from_yaml, restore_version

VALID_SCRIPT_YAML = """
script:
  title: Smoke Script
  version: "1.0"
  language: en-US
  source:
    chapter_count: 3
    chapter_ids:
      - chapter_001
      - chapter_002
      - chapter_003
  logline: A doctor meets a stranger and must decide whether to help tonight.
  themes:
    - trust
  characters:
    - id: char_doctor
      name: Doctor
      role: protagonist
  locations:
    - id: loc_clinic
      name: Clinic
  scenes:
    - id: scene_001
      title: Knock
      chapter_refs:
        - chapter_001
      location_id: loc_clinic
      characters:
        - char_doctor
      purpose: Open the story.
      conflict: The doctor wants to close, but someone needs help.
      action:
        - Rain hits the door.
      dialogue:
        - speaker: char_doctor
          line: We are closed.
"""


def _session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    return Session()


def test_create_version_from_yaml_persists_valid_snapshot():
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

    assert version.id.startswith("ver_")
    assert version.source_type == "manual"
    assert version.label == "Manual edit"
    assert version.notes == "Saved by user."
    assert version.validation_status == "valid"
    assert version.validation_errors == []
    assert version.json_content["script"]["title"] == "Smoke Script"
    assert project.status == "ready"
    assert project.current_version_id == version.id


def test_create_version_from_yaml_keeps_parseable_invalid_snapshot():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()

    version = create_version_from_yaml(db, project, "script:\n  title: Too Small\n")

    assert version.validation_status == "invalid"
    assert version.validation_errors
    assert project.status == "needs_review"
    assert project.current_version_id == version.id


def test_restore_version_creates_new_latest_snapshot():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    original = create_version_from_yaml(db, project, VALID_SCRIPT_YAML)

    restored = restore_version(db, project, original)

    assert restored.id != original.id
    assert restored.parent_version_id == original.id
    assert restored.source_type == "restore"
    assert restored.yaml_content == original.yaml_content
    assert restored.validation_status == original.validation_status
    assert project.current_version_id == restored.id
