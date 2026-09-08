# =====================================================================
# sora.py —— OpenAI Sora 2 视频生成适配器
#
# API：api.openai.com 或 Azure OpenAI
# 认证：API Key (Bearer) 或 Azure api-key header
# 模式：异步提交 → 轮询 → 视频 URL
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..base import VideoJobParams, VideoJobResponse, VideoJobStatus, VideoProvider

log = logging.getLogger(__name__)

# Sora 分辨率映射
_RESOLUTION_MAP: dict[str, dict[str, int]] = {
    "1280x720": {"width": 1280, "height": 720},
    "1920x1080": {"width": 1920, "height": 1080},
    "720x1280": {"width": 720, "height": 1280},
    "1080x1920": {"width": 1080, "height": 1920},
    "1024x1024": {"width": 1024, "height": 1024},
    "480x480": {"width": 480, "height": 480},
}


class SoraProvider(VideoProvider):
    """OpenAI Sora 2 视频生成。"""

    name = "sora"
    label = "Sora 2 (OpenAI)"
    supports_text_to_video = True
    supports_image_to_video = True
    max_duration_sec = 20.0
    pricing_per_sec = 0.10
    supported_resolutions = list(_RESOLUTION_MAP.keys())
    chinese_prompt_support = False  # 推荐英文

    def __init__(self, api_key: str = "", base_url: str = "", **kwargs: Any) -> None:
        super().__init__(api_key, base_url, **kwargs)
        if not self.base_url:
            self.base_url = "https://api.openai.com/v1"
        self._model = kwargs.get("model", "sora-2")

    async def create_job(self, prompt: str, params: VideoJobParams | None = None) -> VideoJobResponse:
        params = params or VideoJobParams()
        dims = _RESOLUTION_MAP.get(params.resolution, {"width": 1280, "height": 720})

        body: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            "width": dims["width"],
            "height": dims["height"],
            "n_seconds": params.duration_sec,
        }
        if params.image_url:
            body["images"] = [{"url": params.image_url}]
        body.update(params.extra)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/videos",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("id", "")
        cost = self.estimate_cost(params.duration_sec)
        return VideoJobResponse(external_task_id=task_id, status="queued", cost_estimate=cost)

    async def poll_job(self, external_task_id: str) -> VideoJobStatus:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/videos/{external_task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        status_str = data.get("status", "unknown")
        status_map = {
            "queued": "queued",
            "preprocessing": "generating",
            "running": "generating",
            "processing": "generating",
            "succeeded": "succeeded",
            "failed": "failed",
            "cancelled": "cancelled",
        }
        mapped = status_map.get(status_str, "queued")

        video_url = None
        if mapped == "succeeded":
            generations = data.get("generations", [])
            if generations:
                video_url = generations[0].get("video_url") or generations[0].get("url")

        return VideoJobStatus(
            external_task_id=external_task_id,
            status=mapped,
            progress=1.0 if mapped == "succeeded" else 0.5 if mapped == "generating" else 0.0,
            video_url=video_url,
            error_message=data.get("failure_reason"),
            raw=data,
        )

    async def cancel_job(self, external_task_id: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/videos/{external_task_id}/cancel",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code in (200, 204)
        except Exception:  # noqa: BLE001
            return False
