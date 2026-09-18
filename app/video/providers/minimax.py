# =====================================================================
# minimax.py —— MiniMax H3（海螺）视频生成适配器（V2 接口）
#
# API：https://api.minimax.cn / https://api.minimaxi.com（国内站，二选一）
# 文档：开发指南 > API > 视频 > MiniMax-H3 > 创建视频生成任务
# 认证：Bearer API Key
# 请求体为多模态 content 数组（文本 / 图片 / 视频 / 音频），
# 文生视频只需一个 text 项；duration 4-15s；分辨率 480P / 768P / 2K。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

import httpx

from ..base import VideoJobParams, VideoJobResponse, VideoJobStatus, VideoProvider

log = logging.getLogger(__name__)


class MiniMaxProvider(VideoProvider):
    """MiniMax H3（海螺）视频生成，V2 任务接口。"""

    name = "minimax"
    label = "MiniMax H3"
    supports_text_to_video = True
    supports_image_to_video = True
    max_duration_sec = 15.0
    pricing_per_sec = 0.045  # 粗略估算值，仅用于费用预估展示
    supported_resolutions = ["480P", "768P", "2K"]
    chinese_prompt_support = True

    def __init__(self, api_key: str = "", base_url: str = "", **kwargs: Any) -> None:
        import os
        api_key = api_key or os.environ.get("MINIMAX_API_KEY", "")
        super().__init__(api_key, base_url, **kwargs)
        if not self.base_url:
            self.base_url = "https://api.minimax.cn"
        self._model = kwargs.get("model", "MiniMax-H3")

    # ---- 多模态 content 组装（V2 接口：文本 / 图片 / 视频 / 音频） ----

    @staticmethod
    def _media(url: str) -> dict[str, Any]:
        """V2 的媒体地址是结构化对象：{"url": ...}。"""
        return {"url": url}

    def _build_content(self, prompt: str, params: VideoJobParams) -> list[dict[str, Any]]:
        """把统一参数组装成 V2 content 数组。

        项格式（经服务端实测确认）：
          {"type": "text", "text": ...}
          {"type": "image_url", "image_url": {"url": ...}, "role": "first_frame|last_frame|reference_image"}
          {"type": "video_url", "video_url": {"url": ...}, "role": "reference_video"}
          {"type": "audio_url", "audio_url": {"url": ...}}
        数量上限（官方文档）：首/尾帧各 ≤2、参考图 ≤9、参考视频 ≤3、参考音频 ≤3，混合 ≤12。
        """
        if params.content:
            return list(params.content)

        content: list[dict[str, Any]] = []
        if prompt.strip():
            content.append({"type": "text", "text": prompt})
        if params.image_url:
            content.append({"type": "image_url", "image_url": self._media(params.image_url), "role": "first_frame"})
        if params.last_frame_image:
            content.append({"type": "image_url", "image_url": self._media(params.last_frame_image), "role": "last_frame"})
        for url in params.reference_images:
            content.append({"type": "image_url", "image_url": self._media(url), "role": "reference_image"})
        for url in params.reference_videos:
            content.append({"type": "video_url", "video_url": self._media(url), "role": "reference_video"})
        for url in params.reference_audios:
            content.append({"type": "audio_url", "audio_url": self._media(url)})

        if not content:
            raise ValueError("prompt 与多模态输入（首尾帧 / 参考素材）至少要有一项")
        media_count = sum(1 for item in content if item.get("type") != "text")
        if media_count > 12:
            raise ValueError("多模态素材总数超过上限（≤12）")
        return content

    async def create_job(self, prompt: str, params: VideoJobParams | None = None) -> VideoJobResponse:
        params = params or VideoJobParams()
        content = self._build_content(prompt, params)

        extra = dict(params.extra)
        # 分辨率/画幅用本 provider 的方言（480P/768P/2K）。优先级：调用方显式
        # 指定 > extra > 全局默认配置（VIDEO_DEFAULT_RESOLUTION，默认 768P 低挡位）。
        from ..base import default_resolution
        resolution = (
            params.resolution
            if params.resolution in self.supported_resolutions
            else extra.pop("resolution", None)
            or (default_resolution() if default_resolution() in self.supported_resolutions else "768P")
        )
        body: dict[str, Any] = {
            "model": self._model,
            "content": content,
            # H3 支持 4-15 秒，夹到合法区间，缺省 6 秒。
            "duration": max(4, min(15, int(params.duration_sec or 6))),
            "resolution": resolution,
            "ratio": extra.pop("ratio", params.aspect_ratio or "16:9"),
        }
        body.update(extra)

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/v2/video_generation",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        # V2 的错误返回 {"type":"error","error":{"message":...}}，HTTP 状态也可能是 4xx。
        if data.get("type") == "error" or not data.get("task_id"):
            message = (data.get("error") or {}).get("message") if isinstance(data.get("error"), dict) else str(data)
            raise RuntimeError(f"MiniMax 提交失败：{message}")

        cost = self.estimate_cost(body["duration"])
        return VideoJobResponse(external_task_id=str(data["task_id"]), status="queued", cost_estimate=cost)

    async def poll_job(self, external_task_id: str) -> VideoJobStatus:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{self.base_url}/v2/query/video_generation/{external_task_id}",
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("type") == "error":
            err = data.get("error") or {}
            message = err.get("message") if isinstance(err, dict) else str(data)
            raise RuntimeError(f"MiniMax 查询失败：{message}")

        # V2 的任务对象嵌在 "task" 键下：{"task": {"id":..., "status":..., "content": {...}}}
        task = data.get("task") if isinstance(data.get("task"), dict) else data
        status_str = str(task.get("status", "")).lower()
        # 注意 "succeeded" 并不包含子串 "success"（中间是 "succee"），必须用 "succeed" 匹配。
        if "succeed" in status_str or status_str in {"completed", "done"}:
            mapped = "succeeded"
        elif "fail" in status_str:
            mapped = "failed"
        elif "cancel" in status_str:
            mapped = "cancelled"
        elif "queue" in status_str:
            mapped = "queued"
        else:
            mapped = "generating"

        # 成功后视频直链在 task.content.url（无需再用 file_id 换取）。
        video_url = None
        if mapped == "succeeded":
            content = task.get("content")
            if isinstance(content, dict):
                video_url = content.get("url")

        return VideoJobStatus(
            external_task_id=external_task_id,
            status=mapped,
            progress=1.0 if mapped == "succeeded" else 0.5 if mapped == "generating" else 0.0,
            video_url=video_url,
            error_message=str(data.get("error", "")) or None if mapped == "failed" else None,
            raw=data,
        )

    async def cancel_job(self, external_task_id: str) -> bool:
        log.info("MiniMax V2 取消任务 %s：需要 DELETE 接口，暂未接入", external_task_id)
        return False
