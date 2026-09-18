# =====================================================================
# test_api.py —— REST / SSE 接口层测试（无 RAG 版）
# =====================================================================

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.api as api_mod
import app.api.video as video_api
from app.agent.skills import SubAgentRunner
from app.main import create_app


@pytest.fixture()
def client(store, llm, settings, monkeypatch):
    # 路由统一通过 app.api.deps 取值，因此替换这一处即可覆盖全部路由。
    monkeypatch.setattr(api_mod.deps, "store", lambda: store)
    monkeypatch.setattr(api_mod.deps, "llm", lambda: llm)
    monkeypatch.setattr(api_mod.deps, "settings", lambda: settings)
    # 后台任务 runner 也要绑到测试库，否则会去连 .env 里的开发库。
    monkeypatch.setattr(
        api_mod.deps, "subagent_runner", lambda: SubAgentRunner(storage=store)
    )
    return TestClient(create_app())


def _import_project(client, sample_text):
    resp = client.post("/api/projects/import", data={"raw_text": sample_text, "title": "雨夜"})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_import_project_and_list(client, sample_text):
    data = _import_project(client, sample_text)
    assert data["title"] == "雨夜"
    assert data["conversation_id"]
    assert "genres" in data

    projects = client.get("/api/projects").json()
    assert len(projects) == 1
    assert projects[0]["title"] == "雨夜"


def test_video_prompt_review_creates_version_and_gates_batch(client, sample_text):
    project = _import_project(client, sample_text)
    shots = [
        {
            "id": "shot_scene_001_000",
            "scene_id": "scene_001",
            "order": 0,
            "subject": "齐夏",
            "video_prompt": "A close-up shot of Qi Xia looking toward the door.",
            "prompt_status": "needs_review",
        },
    ]
    created = client.post(
        f"/api/projects/{project['id']}/video-versions",
        json={"shots": shots, "label": "Prompt 草稿"},
    )
    assert created.status_code == 200, created.text
    version_id = created.json()["id"]

    reviewed = client.put(
        f"/api/projects/{project['id']}/video-versions/{version_id}/shots/"
        "shot_scene_001_000/prompt",
        json={
            "prompt": "A restrained close-up of Qi Xia turning toward the door.",
            "decision": "approve",
            "note": "保留克制的转身动作，避免多余表演。",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["prompt_status"] == "approved"
    assert reviewed.json()["approved_count"] == 1

    latest = client.get(f"/api/video-versions/{reviewed.json()['version_id']}")
    assert latest.status_code == 200
    assert latest.json()["shots"][0]["prompt_status"] == "approved"
    assert latest.json()["shots"][0]["prompt_review_note"].startswith("保留")

    unapproved = client.post(
        f"/api/projects/{project['id']}/video-versions",
        json={
            "shots": [{**shots[0], "prompt_status": "needs_review"}],
            "parent_version_id": reviewed.json()["version_id"],
            "label": "重新待审阅",
        },
    )
    assert unapproved.status_code == 200
    blocked = client.post(
        f"/api/projects/{project['id']}/video/generate-batch",
        json={"version_id": unapproved.json()["id"]},
    )
    assert blocked.status_code == 400
    assert "批准" in blocked.json()["detail"]


def test_single_video_generation_requires_approved_prompt(client, sample_text, monkeypatch):
    project = _import_project(client, sample_text)
    created = client.post(
        f"/api/projects/{project['id']}/video-versions",
        json={
            "shots": [
                {
                    "id": "shot_scene_001_000",
                    "scene_id": "scene_001",
                    "order": 0,
                    "video_prompt": "A close-up shot of Qi Xia looking toward the door.",
                    "prompt_status": "needs_review",
                },
            ],
            "label": "Prompt 草稿",
        },
    )
    assert created.status_code == 200, created.text

    monkeypatch.setattr(video_api, "_submit_video_job", lambda job: None)
    blocked = client.post(
        f"/api/projects/{project['id']}/video/generate",
        json={
            "shot_id": "shot_scene_001_000",
            "provider": "minimax",
            "model": "default",
            "prompt": "A close-up shot of Qi Xia looking toward the door.",
            "version_id": created.json()["id"],
        },
    )
    assert blocked.status_code == 409
    assert "尚未批准" in blocked.json()["detail"]


def test_bulk_prompt_review_exposes_version_summary_and_history(client, sample_text):
    project = _import_project(client, sample_text)
    created = client.post(
        f"/api/projects/{project['id']}/video-versions",
        json={
            "shots": [
                {
                    "id": "shot_scene_001_000",
                    "scene_id": "scene_001",
                    "order": 0,
                    "video_prompt": "A quiet close-up by the door.",
                    "prompt_status": "needs_review",
                },
                {
                    "id": "shot_scene_001_001",
                    "scene_id": "scene_001",
                    "order": 1,
                    "video_prompt": "A wide shot of the rainy street.",
                    "prompt_status": "needs_revision",
                },
            ],
            "label": "Prompt 草稿",
        },
    )
    assert created.status_code == 200, created.text
    version_id = created.json()["id"]

    reviewed = client.post(
        f"/api/projects/{project['id']}/video-versions/{version_id}/prompts/review",
        json={
            "shot_ids": ["shot_scene_001_000"],
            "decision": "approve",
            "note": "批量审阅后保留。",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["reviewed_count"] == 1
    assert reviewed.json()["approved_count"] == 1
    assert reviewed.json()["pending_count"] == 1

    versions = client.get(f"/api/projects/{project['id']}/video-versions")
    assert versions.status_code == 200
    latest = versions.json()[0]
    assert latest["current"] is True
    assert latest["prompt_summary"]["review_status"] == "mixed"
    assert latest["prompt_summary"]["approved_count"] == 1

    history = client.get(
        f"/api/projects/{project['id']}/video-versions/{reviewed.json()['version_id']}/"
        "shots/shot_scene_001_000/prompt-history"
    )
    assert history.status_code == 200, history.text
    assert len(history.json()["history"]) == 2
    assert history.json()["history"][0]["prompt_status"] == "approved"
    assert history.json()["history"][0]["prompt_changed"] is False
    assert history.json()["history"][0]["prompt_review_note"] == "批量审阅后保留。"

    edited = client.put(
        f"/api/projects/{project['id']}/video-versions/{reviewed.json()['version_id']}/"
        "shots/shot_scene_001_000/prompt",
        json={
            "prompt": "A restrained close-up by the rain-streaked door.",
            "decision": "save",
            "note": "补充雨痕细节。",
        },
    )
    assert edited.status_code == 200, edited.text
    changed_history = client.get(
        f"/api/projects/{project['id']}/video-versions/{edited.json()['version_id']}/"
        "shots/shot_scene_001_000/prompt-history"
    )
    assert changed_history.status_code == 200
    latest_entry = changed_history.json()["history"][0]
    assert latest_entry["prompt_changed"] is True
    assert any(line.startswith("+A restrained") for line in latest_entry["diff"])


def test_tasks_endpoint_degrades_without_db(monkeypatch):
    """后台任务落库不可用时 /api/tasks 不应 500（退化为纯内存列表）。"""

    def _boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(api_mod.deps, "store", _boom)
    monkeypatch.setattr(api_mod.deps, "subagent_runner", lambda: SubAgentRunner())
    resp = TestClient(create_app()).get("/api/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


def test_chat_stream_emits_done_frame(client, sample_text):
    data = _import_project(client, sample_text)
    events = []
    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"project_id": data["id"], "message": "帮我看看这部小说"},
    ) as resp:
        assert resp.status_code == 200
        event_name = None
        for line in resp.iter_lines():
            if line.startswith("event: "):
                event_name = line[len("event: "):].strip()
            elif line.startswith("data: ") and event_name:
                events.append((event_name, json.loads(line[len("data: "):])))
                event_name = None
    names = [name for name, _ in events]
    assert "done" in names, f"SSE 应以 done 事件收尾，实际：{names}"
    done = next(payload for name, payload in events if name == "done")
    assert done["reply"]
