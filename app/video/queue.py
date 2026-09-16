# =====================================================================
# queue.py —— 视频生成异步任务队列
#
# 管理视频生成任务的提交、轮询、完成回调。
# 使用线程池 + 定时轮询，适配桌面模式（无需 Redis/Celery）。
# 参考 SubAgentRunner 的设计模式。
# =====================================================================

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from typing import Any

from .base import VideoJobParams, VideoProvider

log = logging.getLogger(__name__)

# 轮询间隔（秒）
POLL_INTERVAL = 5
# 最大轮询次数（20分钟 / 5秒 = 240 次；MiniMax 高峰期排队可能超过 10 分钟）
MAX_POLLS = 240


class VideoJobManager:
    """视频生成任务管理器。

    职责：
      - 接收视频生成请求，提交给 provider
      - 后台轮询任务状态
      - 任务完成/失败时触发回调
      - 提供任务状态查询
    """

    def __init__(self, max_workers: int = 3) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="video-job")
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._callbacks: list[Callable[[str, dict[str, Any]], None]] = []
        # 已通知过的状态指纹，避免每轮轮询都重复触发回调。
        self._notified: dict[str, tuple[Any, ...]] = {}

    def on_complete(self, callback: Callable[[str, dict[str, Any]], None]) -> None:
        """注册任务完成回调。callback(job_id, job_info)。"""
        self._callbacks.append(callback)

    def submit(
        self,
        job_id: str,
        provider: VideoProvider,
        prompt: str,
        params: VideoJobParams | None = None,
    ) -> str:
        """提交视频生成任务到后台线程。

        Args:
            job_id: 内部任务 ID（vjob_xxx）。
            provider: 视频生成 provider 实例。
            prompt: 视频 prompt。
            params: 生成参数。

        Returns:
            job_id
        """
        with self._lock:
            self._jobs[job_id] = {
                "id": job_id,
                "status": "pending",
                "provider": provider.name,
                "external_task_id": None,
                "video_url": None,
                "error": None,
                "progress": 0.0,
                "submitted_at": datetime.now(UTC).isoformat(),
                "finished_at": None,
            }

        self._executor.submit(self._run_job, job_id, provider, prompt, params)
        return job_id

    def _run_job(
        self,
        job_id: str,
        provider: VideoProvider,
        prompt: str,
        params: VideoJobParams | None,
    ) -> None:
        """在线程中执行：提交 → 轮询 → 回调。"""
        loop = asyncio.new_event_loop()
        try:
            # 提交任务
            self._update(job_id, status="submitting")
            response = loop.run_until_complete(provider.create_job(prompt, params))
            external_id = response.external_task_id
            self._update(
                job_id,
                status="queued",
                external_task_id=external_id,
                progress=0.1,
            )

            # 轮询任务状态
            for _ in range(MAX_POLLS):
                time.sleep(POLL_INTERVAL)
                status = loop.run_until_complete(provider.poll_job(external_id))

                self._update(
                    job_id,
                    status=status.status,
                    progress=status.progress,
                    video_url=status.video_url,
                    error=status.error_message,
                )

                if status.status in ("succeeded", "failed", "cancelled"):
                    self._update(job_id, finished_at=datetime.now(UTC).isoformat())
                    break

            else:
                # 超时
                self._update(
                    job_id,
                    status="timeout",
                    error="轮询超时（超过最大等待时间）",
                    finished_at=datetime.now(UTC).isoformat(),
                )

        except Exception as e:  # noqa: BLE001
            log.warning("视频任务 %s 失败：%s", job_id, e)
            self._update(
                job_id,
                status="failed",
                error=str(e),
                finished_at=datetime.now(UTC).isoformat(),
            )
        finally:
            loop.close()

    def _update(self, job_id: str, **fields: Any) -> None:
        """更新内存任务状态；状态有实质变化时通知回调（回调会把状态写回 DB）。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(fields)
            snapshot = dict(job)

        fingerprint = (snapshot.get("status"), snapshot.get("video_url"), snapshot.get("error"))
        if self._notified.get(job_id) == fingerprint:
            return
        self._notified[job_id] = fingerprint
        for cb in self._callbacks:
            try:
                cb(job_id, snapshot)
            except Exception as e:  # noqa: BLE001
                log.warning("视频任务回调失败：%s", e)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_jobs(self, *, status: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.get("status") == status]
        jobs.sort(key=lambda j: j.get("submitted_at", ""), reverse=True)
        return jobs

    def cancel(self, job_id: str, provider: VideoProvider) -> bool:
        """取消正在运行的任务。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return False
            external_id = job.get("external_task_id")
            if not external_id:
                return False

        try:
            loop = asyncio.new_event_loop()
            try:
                result = loop.run_until_complete(provider.cancel_job(external_id))
                if result:
                    self._update(job_id, status="cancelled", finished_at=datetime.now(UTC).isoformat())
                return result
            finally:
                loop.close()
        except Exception as e:  # noqa: BLE001
            log.warning("取消视频任务 %s 失败：%s", job_id, e)
            return False

    def shutdown(self, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait)


# ---- 全局单例 ----

_manager: VideoJobManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> VideoJobManager:
    global _manager
    if _manager is None:
        with _manager_lock:
            if _manager is None:
                _manager = VideoJobManager()
    return _manager
