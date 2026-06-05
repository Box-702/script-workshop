from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_versions import VALID_SCRIPT_YAML

from app.db import Base, EditEvent, Project
from app.routers import agent
from app.routers.deps import get_db
from app.schemas import AgentAdaptRequest
from app.services.agent import (
    accept_agent_run,
    create_agent_run,
    reject_agent_run,
    retry_agent_run,
)
from app.services.versions import create_version_from_yaml


class FakeAgentProvider:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate_structured(self, prompt, schema, *, stage):
        self.calls.append({"prompt": prompt, "schema": schema, "stage": stage})
        return self.response


MULTI_SCENE_SCRIPT_YAML = (
    VALID_SCRIPT_YAML
    + """    - id: scene_002
      title: Choice
      chapter_refs:
        - chapter_002
      location_id: loc_clinic
      characters:
        - char_doctor
      purpose: Force the doctor to choose.
      conflict: The patient refuses to explain the danger.
      action:
        - The doctor locks the cabinet.
      dialogue:
        - speaker: char_doctor
          line: Tell me what happened first.
"""
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
    app.include_router(agent.router)

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_create_agent_run_builds_review_patch():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    base = create_version_from_yaml(db, project, VALID_SCRIPT_YAML)

    run = create_agent_run(
        db,
        project,
        payload=AgentAdaptRequest(
            instruction="把第一场改得更悬疑",
            base_version_id=base.id,
            scene_ids=["scene_001"],
        ),
    )

    assert run.status == "waiting_review"
    assert run.base_version_id == base.id
    assert run.selected_context == {"scene_ids": ["scene_001"]}
    assert run.patch == [
        {
            "op": "set",
            "path": "/script/scenes/0/adaptation_notes/reason",
            "scene_id": "scene_001",
            "scene_title": "Knock",
            "before": None,
            "value": "AI 改编需求：把第一场改得更悬疑",
            "after": "AI 改编需求：把第一场改得更悬疑",
        }
    ]


def test_create_agent_run_can_target_multiple_selected_scenes():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, MULTI_SCENE_SCRIPT_YAML)

    run = create_agent_run(
        db,
        project,
        payload=AgentAdaptRequest(
            instruction="统一强化悬念",
            scene_ids=["scene_001", "scene_002"],
        ),
    )

    assert run.selected_context == {"scene_ids": ["scene_001", "scene_002"]}
    assert [item["path"] for item in run.patch] == [
        "/script/scenes/0/adaptation_notes/reason",
        "/script/scenes/1/adaptation_notes/reason",
    ]
    assert [item["scene_id"] for item in run.patch] == ["scene_001", "scene_002"]


def test_create_agent_run_uses_model_patch_for_scene_rewrite():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    base = create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    provider = FakeAgentProvider(
        {
            "plan": ["强化门外未知威胁", "压缩对白并增加动作悬念"],
            "changes": [
                {
                    "scene_id": "scene_001",
                    "purpose": "Open with a sharper suspense hook.",
                    "conflict": (
                        "The doctor wants safety, but the stranger brings danger to the door."
                    ),
                    "action": ["Rain rattles the sign.", "A bloodied hand hits the glass."],
                    "dialogue": [
                        {
                            "speaker": "char_doctor",
                            "line": "Who is out there?",
                            "emotion": "tense",
                        }
                    ],
                    "adaptation_reason": "强化悬疑钩子，减少解释性对白。",
                    "fidelity": "reordered",
                }
            ],
        }
    )

    run = create_agent_run(
        db,
        project,
        payload=AgentAdaptRequest(
            instruction="把第一场改得更悬疑，减少解释性对白",
            base_version_id=base.id,
            scene_ids=["scene_001"],
        ),
        provider=provider,
    )

    assert run.model == "openai-compatible-agent"
    assert provider.calls
    assert run.plan == ["强化门外未知威胁", "压缩对白并增加动作悬念"]
    assert [item["field"] for item in run.patch] == [
        "purpose",
        "conflict",
        "action",
        "dialogue",
        "adaptation_notes/reason",
        "adaptation_notes/fidelity",
    ]

    version = accept_agent_run(db, run)
    scene = version.json_content["script"]["scenes"][0]
    assert scene["purpose"] == "Open with a sharper suspense hook."
    assert scene["action"] == ["Rain rattles the sign.", "A bloodied hand hits the glass."]
    assert scene["dialogue"][0]["line"] == "Who is out there?"
    assert scene["adaptation_notes"]["reason"] == "强化悬疑钩子，减少解释性对白。"


def test_accept_agent_run_creates_version_and_edit_event():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    run = create_agent_run(
        db,
        project,
        payload=AgentAdaptRequest(instruction="减少解释性对白", scene_ids=[]),
    )

    version = accept_agent_run(db, run)
    db.refresh(run)

    assert run.status == "accepted"
    assert run.result_version_id == version.id
    assert version.source_type == "agent_adaptation"
    assert version.parent_version_id == run.base_version_id
    scene = version.json_content["script"]["scenes"][0]
    assert scene["adaptation_notes"]["reason"] == "AI 改编需求：减少解释性对白"
    event = db.query(EditEvent).filter_by(version_id=version.id).one()
    assert event.edit_type == "ai_patch"
    assert event.actor_type == "agent"
    assert event.patch["agent_run_id"] == run.id


def test_accept_agent_run_can_apply_selected_patch_items_only():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    provider = FakeAgentProvider(
        {
            "plan": ["局部修改测试"],
            "changes": [
                {
                    "scene_id": "scene_001",
                    "purpose": "Open with a sharper suspense hook.",
                    "conflict": "The stranger pulls danger into the clinic.",
                    "adaptation_reason": "只接受部分建议。",
                }
            ],
        }
    )
    run = create_agent_run(
        db,
        project,
        payload=AgentAdaptRequest(instruction="给我三个建议", scene_ids=["scene_001"]),
        provider=provider,
    )

    version = accept_agent_run(db, run, patch_indexes=[0, 2])
    scene = version.json_content["script"]["scenes"][0]

    assert scene["purpose"] == "Open with a sharper suspense hook."
    assert scene["conflict"] == "The doctor wants to close, but someone needs help."
    assert scene["adaptation_notes"]["reason"] == "只接受部分建议。"
    event = db.query(EditEvent).filter_by(version_id=version.id).one()
    assert event.patch["accepted_patch_indexes"] == [0, 2]
    assert len(event.patch["patch"]) == 2


def test_retry_agent_run_reuses_original_context_and_prompt():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    base = create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    run = create_agent_run(
        db,
        project,
        payload=AgentAdaptRequest(
            instruction="强化悬疑",
            base_version_id=base.id,
            scene_ids=["scene_001"],
        ),
    )
    provider = FakeAgentProvider(
        {
            "plan": ["重新生成更强的悬疑版本"],
            "changes": [
                {
                    "scene_id": "scene_001",
                    "purpose": "Open with a sharper suspense hook.",
                }
            ],
        }
    )

    retried = retry_agent_run(db, run, provider=provider)

    assert retried.id != run.id
    assert retried.base_version_id == base.id
    assert retried.user_prompt == "强化悬疑"
    assert retried.selected_context == {"scene_ids": ["scene_001"]}
    assert retried.model == "openai-compatible-agent"
    assert retried.patch[0]["field"] == "purpose"


def test_reject_agent_run_does_not_create_version():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    run = create_agent_run(
        db,
        project,
        payload=AgentAdaptRequest(instruction="只做审稿，不保存", scene_ids=[]),
    )

    rejected = reject_agent_run(db, run)

    assert rejected.status == "rejected"
    assert rejected.result_version_id is None
    assert len(project.versions) == 1


def test_agent_routes_create_get_and_accept_run():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    client = _client(db)

    created = client.post(
        f"/api/projects/{project.id}/agent/adapt",
        json={"instruction": "强化短剧钩子", "scene_ids": ["scene_001"]},
    )
    assert created.status_code == 200
    run_id = created.json()["id"]

    fetched = client.get(f"/api/agent-runs/{run_id}")
    assert fetched.status_code == 200
    assert fetched.json()["status"] == "waiting_review"

    accepted = client.post(f"/api/agent-runs/{run_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["source_type"] == "agent_adaptation"


def test_agent_route_reject_run():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    client = _client(db)

    created = client.post(
        f"/api/projects/{project.id}/agent/adapt",
        json={"instruction": "先不要落版", "scene_ids": ["scene_001"]},
    )
    assert created.status_code == 200
    run_id = created.json()["id"]

    rejected = client.post(f"/api/agent-runs/{run_id}/reject")
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    accepted = client.post(f"/api/agent-runs/{run_id}/accept")
    assert accepted.status_code == 400


def test_agent_route_retry_run():
    db = _session()
    project = Project(id="proj_test", title="Test", adaptation_type="short_drama")
    db.add(project)
    db.commit()
    create_version_from_yaml(db, project, VALID_SCRIPT_YAML)
    client = _client(db)

    created = client.post(
        f"/api/projects/{project.id}/agent/adapt",
        json={"instruction": "重新强化", "scene_ids": ["scene_001"]},
    )
    run_id = created.json()["id"]

    retried = client.post(f"/api/agent-runs/{run_id}/retry")

    assert retried.status_code == 200
    assert retried.json()["id"] != run_id
    assert retried.json()["user_prompt"] == "重新强化"
    assert retried.json()["selected_context"] == {"scene_ids": ["scene_001"]}
