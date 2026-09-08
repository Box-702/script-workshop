# =====================================================================
# base.py —— 视频生成 Provider 抽象基类
#
# 所有视频生成适配器继承 VideoProvider，实现统一的异步接口：
#   create_job  → 提交生成任务
#   poll_job    → 查询任务状态
#   cancel_job  → 取消任务
#   download    → 下载生成结果
#
# 参考 Runway / Kling / Sora 等 API 的共性模式：
# 全部走异步提交 + 轮询，返回视频 URL。
# =====================================================================

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


# ---- 请求 / 响应数据结构 ----


@dataclass
class VideoJobParams:
    """视频生成请求参数（统一格式）。"""

    resolution: str = "1280x720"  # WxH 格式
    duration_sec: int = 5
    fps: int = 24
    aspect_ratio: str = "16:9"
    seed: int | None = None
    negative_prompt: str | None = None
    image_url: str | None = None  # 图生视频的输入图
    extra: dict[str, Any] = field(default_factory=dict)  # provider 特有参数


@dataclass
class VideoJobResponse:
    """提交任务后的响应。"""

    external_task_id: str  # provider 返回的任务 ID
    status: str = "queued"  # queued / pending / generating
    message: str = ""
    cost_estimate: float | None = None  # 预估费用（美元）


@dataclass
class VideoJobStatus:
    """任务状态查询结果。"""

    external_task_id: str
    status: str  # queued / generating / succeeded / failed / cancelled
    progress: float = 0.0  # 0.0 ~ 1.0
    video_url: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)  # 原始响应


# ---- 抽象基类 ----


class VideoProvider(ABC):
    """视频生成 Provider 抽象基类。

    子类必须实现四个异步方法和一组类属性。
    类属性描述 provider 的能力边界，用于前端展示和路由选择。
    """

    # ---- 子类必须设置的类属性 ----
    name: str = ""  # 唯一标识，如 "runway" / "kling"
    label: str = ""  # 显示名，如 "Runway Gen-4" / "Kling AI"
    supports_text_to_video: bool = True
    supports_image_to_video: bool = False
    max_duration_sec: float = 10.0
    pricing_per_sec: float = 0.0  # 美元/秒，0 表示未知
    supported_resolutions: list[str] = field(default_factory=lambda: ["1280x720", "1920x1080"])
    chinese_prompt_support: bool = False

    def __init__(self, api_key: str = "", base_url: str = "", **kwargs: Any) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/") if base_url else ""
        self._config = kwargs

    @abstractmethod
    async def create_job(self, prompt: str, params: VideoJobParams | None = None) -> VideoJobResponse:
        """提交视频生成任务。

        Args:
            prompt: 视频描述文本。
            params: 生成参数（分辨率、时长等）。

        Returns:
            VideoJobResponse 含 external_task_id。
        """
        ...

    @abstractmethod
    async def poll_job(self, external_task_id: str) -> VideoJobStatus:
        """轮询任务状态。

        Args:
            external_task_id: create_job 返回的任务 ID。

        Returns:
            VideoJobStatus 含最新状态和视频 URL（如果完成）。
        """
        ...

    @abstractmethod
    async def cancel_job(self, external_task_id: str) -> bool:
        """取消正在运行的任务。返回是否成功。"""
        ...

    async def download_video(self, video_url: str) -> bytes:
        """下载生成的视频文件。

        默认用 httpx GET；子类可覆盖处理签名 URL 等特殊情况。
        """
        import httpx

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(video_url)
            resp.raise_for_status()
            return resp.content

    def estimate_cost(self, duration_sec: float) -> float | None:
        """估算生成费用。返回 None 表示无法估算。"""
        if self.pricing_per_sec <= 0:
            return None
        return round(self.pricing_per_sec * duration_sec, 4)

    def validate_params(self, params: VideoJobParams) -> list[str]:
        """校验参数是否在 provider 支持范围内。返回问题列表（空=通过）。"""
        issues: list[str] = []
        if params.duration_sec > self.max_duration_sec:
            issues.append(
                f"时长 {params.duration_sec}s 超过 {self.label} 上限 {self.max_duration_sec}s"
            )
        if params.resolution not in self.supported_resolutions:
            issues.append(
                f"分辨率 {params.resolution} 不在 {self.label} 支持列表中："
                f"{', '.join(self.supported_resolutions)}"
            )
        if params.image_url and not self.supports_image_to_video:
            issues.append(f"{self.label} 不支持图生视频")
        return issues

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} label={self.label!r}>"
