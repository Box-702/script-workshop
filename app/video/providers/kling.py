# =====================================================================
# kling.py —— 快手 Kling AI 视频生成适配器
#
# API：klingai.com / 通过 PiAPI 聚合
# 认证：JWT 或 API Key
# 特色：原生中文 Prompt、支持运镜控制
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..base import VideoJobParams, VideoJobResponse, VideoJobStatus, VideoProvider

log = logging.getLogger(__name__)


class KlingProvider(VideoProvider):
    """快手 Kling AI 视频生成。"""

    name = "kling"
    label = "Kling AI"
    supports_text_to_video = True
    supports_image_to_video = True
    max_duration_sec = 10.0
    pricing_per_sec = 0.10
    supported_resolutions = ["1280x720", "1920x1080", "720x1280", "1080x1920"]
    chinese_prompt_support = True

    def __init__(self, api_key: str = "", base_url: str = "", **kwargs: Any) -> None:
        super().__init__(api_key, base_url, **kwargs)
        if not self.base_url:
            self.base_url = "https://api.klingai.com"
        self._model = kwargs.get("model", "kling-v3")

    async def create_job(self, prompt: str, params: VideoJobParams | None = None) -> VideoJobResponse:
        params = params or VideoJobParams()

        body: dict[str, Any] = {
            "model_name": self._model,
            "prompt": prompt,
            "duration": str(params.duration_sec),
            "aspect_ratio": params.aspect_ratio,
        }
        if params.image_url:
            body["image"] = params.image_url
        if params.negative_prompt:
            body["negative_prompt"] = params.negative_prompt
        if params.seed is not None:
            body["seed"] = params.seed
        body.update(params.extra)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/v1/videos/text2video",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("data", {}).get("task_id", "")
        cost = self.estimate_cost(params.duration_sec)
        return VideoJobResponse(external_task_id=task_id, status="queued", cost_estimate=cost)

    async def poll_job(self, external_task_id: str) -> VideoJobStatus:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/v1/videos/text2video/{external_task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        task_data = data.get("data", {})
        status_str = task_data.get("task_status", "unknown")
        status_map = {
            "submitted": "queued",
            "processing": "generating",
            "succeed": "succeeded",
            "failed": "failed",
        }
        mapped = status_map.get(status_str, "queued")

        video_url = None
        if mapped == "succeeded":
            results = task_data.get("task_result", {})
            videos = results.get("videos", [])
            if videos:
                video_url = videos[0].get("url")

        return VideoJobStatus(
            external_task_id=external_task_id,
            status=mapped,
            progress=1.0 if mapped == "succeeded" else 0.5 if mapped == "generating" else 0.0,
            video_url=video_url,
            error_message=task_data.get("task_status_msg"),
            raw=data,
        )

    async def cancel_job(self, external_task_id: str) -> bool:
        # Kling API 可能不支持取消，返回 False
        log.info("Kling API 不支持取消任务 %s", external_task_id)
        return False
