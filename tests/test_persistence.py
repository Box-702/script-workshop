# =====================================================================
# test_persistence.py —— 本轮重构新增的持久化能力
#
# 覆盖：视觉风格指南读写 / 分镜方案读写 / 后台任务历史落库。
# =====================================================================

from __future__ import annotations

import time

from app.agent.skills import SubAgentRunner, SubAgentTask


def _project(store):
    return store.create_project(
        title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text="原文。"
    )


# ---------- 视觉风格指南 ----------


def test_video_style_roundtrip_and_merge(store):
    p = _project(store)
    assert store.get_video_style(p.id) == {}

    store.set_video_style(p.id, {"mood": "冷峻", "character_appearances": {"齐夏": "黑色风衣"}})
    assert store.get_video_style(p.id)["mood"] == "冷峻"

    # 局部合并不能丢掉已有字段（回填 reference_images 时依赖这一点）
    merged = store.merge_video_style(p.id, {"reference_images": {"齐夏": "http://img"}})
    assert merged["mood"] == "冷峻"
    assert merged["reference_images"] == {"齐夏": "http://img"}
    assert store.get_video_style(p.id)["mood"] == "冷峻"


def test_video_style_on_missing_project_is_empty(store):
    assert store.get_video_style("proj_missing") == {}
    assert store.set_video_style("proj_missing", {"a": 1}) == {}


# ---------- 分镜方案 ----------


def test_version_breakdown_roundtrip(store):
    p = _project(store)
    script = store.latest_version(p)
    assert script is None

    from app.domain import Character, Location, Scene, Script, Source

    s = Script(
        title="t", logline="l", themes=[],
        source=Source(chapter_count=1, chapter_ids=["ch_001"]),
        characters=[Character(id="char_a", name="齐夏")],
        locations=[Location(id="loc_room", name="密室")],
        scenes=[Scene(id="scene_001", title="第一场", chapter_refs=["ch_001"],
                      location_id="loc_room", characters=["char_a"], purpose="p", conflict="c")],
    )
    v = store.create_version(p, s, source_type="generation", label="初稿")
    assert store.get_version_breakdown(v.id) == []

    shots = [{"scene_id": "scene_001", "order": 0, "subject": "齐夏"}]
    assert store.set_version_breakdown(v.id, shots) is True
    assert store.get_version_breakdown(v.id) == shots
    assert store.set_version_breakdown("ver_missing", shots) is False


# ---------- 后台任务历史 ----------


def test_subagent_task_store_roundtrip(store):
    store.save_subagent_task({
        "id": "task_0001", "name": "导演拆解", "status": "done",
        "steps": [{"label": "提取场景数据", "status": "done", "detail": "3 个场景"}],
        "result": "报告正文", "created_at": None, "finished_at": None,
    })
    row = store.get_subagent_task("task_0001")
    assert row is not None
    assert row["status"] == "done"
    assert row["steps"][0]["label"] == "提取场景数据"

    # upsert：同一 id 再写一次应更新而不是插入
    store.save_subagent_task({
        "id": "task_0001", "name": "导演拆解", "status": "failed",
        "steps": [], "result": "失败原因", "created_at": None, "finished_at": None,
    })
    assert store.get_subagent_task("task_0001")["status"] == "failed"
    assert len(store.list_subagent_tasks()) == 1

    assert store.get_subagent_task("task_missing") is None


def test_runner_persists_lifecycle(store):
    """后台任务应在启动与结束时各落库一次，重启后历史仍可查。"""
    runner = SubAgentRunner(storage=store)

    def _job(task: SubAgentTask) -> str:
        runner.update_step(task.id, "干活", "running")
        return "干完了"

    task_id = runner.start("测试任务", _job)

    # 等后台线程结束（最多 2 秒，避免测试抖动）
    for _ in range(200):
        row = store.get_subagent_task(task_id)
        if row and row["status"] in ("done", "failed"):
            break
        time.sleep(0.01)

    row = store.get_subagent_task(task_id)
    assert row is not None
    assert row["status"] == "done"
    assert row["result"] == "干完了"
    assert row["finished_at"] is not None


def test_runner_without_storage_still_works():
    runner = SubAgentRunner()
    task_id = runner.start("无持久化任务", lambda task: "ok")
    assert task_id.startswith("task_")


def test_attach_storage_after_construction(store):
    """落库必须能后置挂载：单例先被谁拿到、存储是否可用，都不该让持久化静默失效。"""
    runner = SubAgentRunner()          # 先构造（模拟单例已被取走）
    assert runner._storage is None
    runner.attach_storage(store)       # 装配时才挂上存储

    task_id = runner.start("后置挂载", lambda task: "done")
    for _ in range(200):
        if store.get_subagent_task(task_id):
            break
        time.sleep(0.01)
    assert store.get_subagent_task(task_id)["name"] == "后置挂载"
