# =====================================================================
# cogvideo.py —— 智谱 CogVideoX 视频生成适配器
#
# API：open.bigmodel.cn（ZhipuAI 平台，v4）
# 认证：API Key (Bearer)
# 特色：原生中文、cogvideox-flash 免费（带水印）、最高 4K
#
# 接口（实测确认，2026-09-10）：
#   创建：POST /videos/generations        -> {"id": task_id, "task_status": "PROCESSING"}
#   查询：GET  /async-result/{task_id}    -> {"task_status": "SUCCESS",
#                                              "video_result": [{"url": ...}]}
#   状态值为大写（PROCESSING / SUCCESS / FAIL），需大小写不敏感处理。
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
    max_duration_sec = 10.0
    pricing_per_sec = 0.0  # flash 免费，其余按量计费
    supported_resolutions = ["1280x720", "1920x1080", "3840x2160"]
    chinese_prompt_support = True

    def __init__(self, api_key: str = "", base_url: str = "", **kwargs: Any) -> None:
        import os
        api_key = api_key or os.environ.get("ZHIPUAI_API_KEY", "")
        super().__init__(api_key, base_url, **kwargs)
        if not self.base_url:
            self.base_url = "https://open.bigmodel.cn/api/paas/v4"
        self._model = kwargs.get("model", "cogvideox-flash")

    async def create_job(self, prompt: str, params: VideoJobParams | None = None) -> VideoJobResponse:
        params = params or VideoJobParams()

        body: dict[str, Any] = {
            "model": self._model,
            "prompt": prompt,
            # 智谱用 size 字段（WxH 格式）
            "size": params.resolution,
        }
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
        if not task_id:
            raise RuntimeError(f"智谱提交失败：{data}")
        return VideoJobResponse(external_task_id=task_id, status="queued")

    async def poll_job(self, external_task_id: str) -> VideoJobStatus:
        # 异步任务统一走 /async-result/{id}（不是 /videos/generations/{id}）。
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/async-result/{external_task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        status_str = str(data.get("task_status", "")).lower()
        if "success" in status_str or "succeed" in status_str:
            mapped = "succeeded"
        elif "fail" in status_str:
            mapped = "failed"
        elif "cancel" in status_str:
            mapped = "cancelled"
        elif "queue" in status_str or "pending" in status_str:
            mapped = "queued"
        else:
            mapped = "generating"

        video_url = None
        if mapped == "succeeded":
            results = data.get("video_result") or data.get("video_results") or []
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
        log.info("智谱 CogVideoX 取消任务 %s：未接入取消接口", external_task_id)
        return False
