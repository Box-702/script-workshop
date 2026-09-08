# =====================================================================
# minimax.py —— MiniMax 海螺 (Hailuo) 视频生成适配器
#
# API：api.minimax.chat / platform.minimaxi.com
# 认证：API Key
# 特色：原生中文、价格低、支持首尾帧控制
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..base import VideoJobParams, VideoJobResponse, VideoJobStatus, VideoProvider

log = logging.getLogger(__name__)


class MiniMaxProvider(VideoProvider):
    """MiniMax 海螺 (Hailuo) 视频生成。"""

    name = "minimax"
    label = "MiniMax 海螺"
    supports_text_to_video = True
    supports_image_to_video = True
    max_duration_sec = 10.0
    pricing_per_sec = 0.045
    supported_resolutions = ["1280x720", "768x768", "512x512"]
    chinese_prompt_support = True

    def __init__(self, api_key: str = "", base_url: str = "", **kwargs: Any) -> None:
        import os
        api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        super().__init__(api_key, base_url, **kwargs)
        if not self.base_url:
            self.base_url = "https://api.minimaxi.com"
        self._model = kwargs.get("model", "MiniMax-Hailuo-01")

    async def create_job(self, prompt: str, params: VideoJobParams | None = None) -> VideoJobResponse:
        params = params or VideoJobParams()

        body: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
        }
        if params.image_url:
            body["first_frame_image"] = params.image_url
        if params.duration_sec:
            body["duration"] = params.duration_sec
        body.update(params.extra)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/v1/video_generation",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("task_id", "")
        cost = self.estimate_cost(params.duration_sec)
        return VideoJobResponse(external_task_id=task_id, status="queued", cost_estimate=cost)

    async def poll_job(self, external_task_id: str) -> VideoJobStatus:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/v1/query/video_generation?task_id={external_task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        status_str = data.get("status", "unknown")
        status_map = {
            "Queueing": "queued",
            "Preparing": "generating",
            "Processing": "generating",
            "Success": "succeeded",
            "Fail": "failed",
        }
        mapped = status_map.get(status_str, "queued")

        video_url = None
        if mapped == "succeeded":
            file_id = data.get("file_id", "")
            if file_id:
                video_url = f"{self.base_url}/v1/files/retrieve?file_id={file_id}"

        return VideoJobStatus(
            external_task_id=external_task_id,
            status=mapped,
            progress=1.0 if mapped == "succeeded" else 0.5 if mapped == "generating" else 0.0,
            video_url=video_url,
            error_message=data.get("status_msg"),
            raw=data,
        )

    async def cancel_job(self, external_task_id: str) -> bool:
        log.info("MiniMax API 不支持取消任务 %s", external_task_id)
        return False
