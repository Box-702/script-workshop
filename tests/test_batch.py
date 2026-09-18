# =====================================================================
# test_batch.py —— 批量生成编排（自动/审批模式）状态机测试
# =====================================================================

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.video.batch import BatchManager


def _job(shot_id: str, status: str = "succeeded", url: str | None = "http://v.mp4", err: str | None = None):
    return SimpleNamespace(shot_id=shot_id, status=status, video_url=url, error_message=err)


def _make(mode: str, shots: list[str]) -> tuple[BatchManager, str, list[str]]:
    """起一个批次，submit 记录提交顺序。返回 (mgr, batch_id, submitted)。"""
    mgr = BatchManager()
    submitted: list[str] = []

    def submit(shot_id: str) -> str | None:
        submitted.append(shot_id)
        return f"job_{len(submitted)}"

    batch = mgr.start("p1", shots, mode, submit)
    return mgr, batch.id, submitted


def test_auto_mode_runs_all_shots_serially():
    """自动模式：每镜成功自动提交下一镜，最后全部完成。"""
    mgr, bid, submitted = _make("auto", ["s0", "s1", "s2"])
    assert submitted == ["s0"]
    for i, sid in enumerate(["s0", "s1", "s2"]):
        batch = mgr.on_job_finished("p1", sid, _job(sid))
        if i < 2:
            assert batch.status == "running"
            assert submitted[-1] == f"s{i + 1}"
    assert batch.status == "done"
    assert batch.results == {"s0": "http://v.mp4", "s1": "http://v.mp4", "s2": "http://v.mp4"}


def test_approval_mode_pauses_after_each_shot():
    """审批模式：每镜完成暂停等命令，approve 放行下一镜。"""
    mgr, bid, submitted = _make("approval", ["s0", "s1", "s2"])
    batch = mgr.on_job_finished("p1", "s0", _job("s0"))
    assert batch.status == "awaiting_approval"
    assert submitted == ["s0"]  # 不会自动提交下一镜

    batch = mgr.approve(bid, submit=lambda sid: (submitted.append(sid), f"job_{sid}")[1])
    assert batch.status == "running" and submitted[-1] == "s1"

    batch = mgr.on_job_finished("p1", "s1", _job("s1"))
    assert batch.status == "awaiting_approval"

    # 最后一镜通过 → done
    batch = mgr.approve(bid, submit=lambda sid: (submitted.append(sid), f"job_{sid}")[1])
    assert submitted[-1] == "s2"
    mgr.on_job_finished("p1", "s2", _job("s2"))
    batch = mgr.approve(bid, submit=lambda sid: (submitted.append(sid), f"job_{sid}")[1])
    assert batch.status == "done"


def test_reroll_resubmits_current_shot():
    """审批模式 reroll：重新提交当前镜，不推进。"""
    mgr, bid, submitted = _make("approval", ["s0", "s1"])
    mgr.on_job_finished("p1", "s0", _job("s0"))
    batch = mgr.reroll(bid, submit=lambda sid: (submitted.append(sid), f"job_{sid}")[1])
    assert submitted == ["s0", "s0"]
    assert batch.status == "running"
    assert batch.current_shot_id == "s0"


def test_failed_shot_fails_batch_with_error():
    """镜头生成失败 → 批次 failed 并带错误信息，不推进。"""
    mgr, bid, submitted = _make("auto", ["s0", "s1"])
    batch = mgr.on_job_finished("p1", "s0", _job("s0", status="failed", url=None, err="超时"))
    assert batch.status == "failed"
    assert "超时" in batch.error
    assert submitted == ["s0"]  # 不会继续提交
    # 失败后 approve 被拒绝
    with pytest.raises(ValueError):
        mgr.approve(bid, submit=lambda sid: "job_x")


def test_abort_stops_batch():
    mgr, bid, _ = _make("approval", ["s0", "s1", "s2"])
    mgr.on_job_finished("p1", "s0", _job("s0"))
    batch = mgr.abort(bid)
    assert batch.status == "aborted"
    with pytest.raises(ValueError):
        mgr.approve(bid, submit=lambda sid: "job_x")


def test_unrelated_job_does_not_advance():
    """不属于当前镜的任务完成不推进批次（串行批次只认当前镜）。"""
    mgr, bid, submitted = _make("auto", ["s0", "s1"])
    batch = mgr.on_job_finished("p1", "s9", _job("s9"))
    assert batch is None
    assert submitted == ["s0"]
    # 当前镜成功照常推进
    batch = mgr.on_job_finished("p1", "s0", _job("s0"))
    assert batch.status == "running"


def test_start_rejects_bad_mode_and_empty_shots():
    mgr = BatchManager()
    with pytest.raises(ValueError):
        mgr.start("p1", ["s0"], "manual", lambda sid: "job")
    with pytest.raises(ValueError):
        mgr.start("p1", [], "auto", lambda sid: "job")
