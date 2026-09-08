# =====================================================================
# test_api.py —— REST / SSE 接口层测试（无 RAG 版）
# =====================================================================

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import app.api as api_mod
from app.main import create_app


@pytest.fixture()
def client(store, llm, settings, monkeypatch):
    monkeypatch.setattr(api_mod, "store", lambda: store)
    monkeypatch.setattr(api_mod, "llm", lambda: llm)
    monkeypatch.setattr(api_mod, "settings", lambda: settings)
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


def test_status_reports_memory_enabled(client):
    payload = client.get("/api/status").json()
    assert payload["memory"]["enabled"] is True
    assert payload["memory"]["backend"] == "database"


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
