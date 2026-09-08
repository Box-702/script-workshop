# =====================================================================
# runway.py —— Runway Gen-4 / Seedance 视频生成适配器
#
# API 文档：docs.dev.runwayml.com
# 认证：API Secret Key（RUNWAYML_API_SECRET）
# 模式：异步提交 → 轮询 → 视频 URL
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..base import VideoJobParams, VideoJobResponse, VideoJobStatus, VideoProvider

log = logging.getLogger(__name__)

# Runway API 分辨率映射（ratio 字符串）
_RESOLUTION_MAP: dict[str, str] = {
    "1280x720": "1280:720",
    "1920x1080": "1920:1080",
    "720x1280": "720:1280",
    "1080x1920": "1080:1920",
    "1024x1024": "1:1",
}


class RunwayProvider(VideoProvider):
    """Runway Gen-4 / Seedance 视频生成。"""

    name = "runway"
    label = "Runway Gen-4"
    supports_text_to_video = True
    supports_image_to_video = True
    max_duration_sec = 10.0
    pricing_per_sec = 0.12  # Gen-4 Turbo: $0.05; 标准: $0.12
    supported_resolutions = list(_RESOLUTION_MAP.keys())
    chinese_prompt_support = False  # 推荐英文

    def __init__(self, api_key: str = "", base_url: str = "", **kwargs: Any) -> None:
        super().__init__(api_key, base_url, **kwargs)
        if not self.base_url:
            self.base_url = "https://api.dev.runwayml.com"
        self._model = kwargs.get("model", "gen4_turbo")

    async def create_job(self, prompt: str, params: VideoJobParams | None = None) -> VideoJobResponse:
        params = params or VideoJobParams()
        ratio = _RESOLUTION_MAP.get(params.resolution, "1280:720")

        body: dict[str, Any] = {
            "model": self._model,
            "promptText": prompt,
            "ratio": ratio,
        }
        if params.image_url:
            body["promptImage"] = params.image_url
        if params.seed is not None:
            body["seed"] = params.seed
        body.update(params.extra)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/v1/image_to_video" if params.image_url else f"{self.base_url}/v1/videos",
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
                f"{self.base_url}/v1/videos/{external_task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        status_str = data.get("status", "unknown")
        status_map = {
            "PENDING": "queued",
            "RUNNING": "generating",
            "SUCCEEDED": "succeeded",
            "FAILED": "failed",
            "CANCELLED": "cancelled",
        }
        mapped = status_map.get(status_str, "queued")

        video_url = None
        if mapped == "succeeded":
            output = data.get("output")
            if isinstance(output, list) and output:
                video_url = output[0]
            elif isinstance(output, str):
                video_url = output

        return VideoJobStatus(
            external_task_id=external_task_id,
            status=mapped,
            progress=1.0 if mapped == "succeeded" else 0.5 if mapped == "generating" else 0.0,
            video_url=video_url,
            error_message=data.get("failure") or data.get("error"),
            raw=data,
        )

    async def cancel_job(self, external_task_id: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/v1/videos/{external_task_id}/cancel",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code in (200, 204)
        except Exception:  # noqa: BLE001
            return False
