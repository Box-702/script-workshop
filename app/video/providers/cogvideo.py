# =====================================================================
# cogvideo.py —— 智谱 CogVideoX 视频生成适配器
#
# API：open.bigmodel.cn（ZhipuAI 平台）
# 认证：API Key (Bearer)
# 特色：原生中文、最高 4K、开源可自部署
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..base import VideoJobParams, VideoJobResponse, VideoJobStatus, VideoProvider

log = logging.getLogger(__name__)


class CogVideoProvider(VideoProvider):
    """智谱 CogVideoX 视频生成。"""

    name = "cogvideo"
    label = "CogVideoX (智谱)"
    supports_text_to_video = True
    supports_image_to_video = True
    max_duration_sec = 6.0
    pricing_per_sec = 0.0  # 按量计费，价格不固定
    supported_resolutions = ["1280x720", "1920x1080", "3840x2160"]
    chinese_prompt_support = True

    def __init__(self, api_key: str = "", base_url: str = "", **kwargs: Any) -> None:
        super().__init__(api_key, base_url, **kwargs)
        if not self.base_url:
            self.base_url = "https://open.bigmodel.cn/api/paas/v4"
        self._model = kwargs.get("model", "cogvideox-2")

    async def create_job(self, prompt: str, params: VideoJobParams | None = None) -> VideoJobResponse:
        params = params or VideoJobParams()

        body: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
        }
        # 智谱用 size 字段（WxH 格式）
        body["size"] = params.resolution
        if params.fps:
            body["fps"] = params.fps
        if params.image_url:
            body["image_url"] = params.image_url
        body.update(params.extra)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/videos/generations",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        task_id = data.get("id", "")
        return VideoJobResponse(external_task_id=task_id, status="queued")

    async def poll_job(self, external_task_id: str) -> VideoJobStatus:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/videos/generations/{external_task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        status_str = data.get("status", "unknown")
        status_map = {
            "pending": "queued",
            "processing": "generating",
            "success": "succeeded",
            "failed": "failed",
        }
        mapped = status_map.get(status_str, "queued")

        video_url = None
        if mapped == "succeeded":
            results = data.get("video_results", [])
            if results:
                video_url = results[0].get("url")

        return VideoJobStatus(
            external_task_id=external_task_id,
            status=mapped,
            progress=1.0 if mapped == "succeeded" else 0.5 if mapped == "generating" else 0.0,
            video_url=video_url,
            error_message=data.get("error", {}).get("message") if isinstance(data.get("error"), dict) else None,
            raw=data,
        )

    async def cancel_job(self, external_task_id: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self.base_url}/videos/generations/{external_task_id}/cancel",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code in (200, 204)
        except Exception:  # noqa: BLE001
            return False
