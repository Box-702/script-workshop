# =====================================================================
# video —— 视频生成 Provider 抽象层
#
# 统一封装各视频生成 API（Runway / Kling / CogVideo / Sora / MiniMax），
# 提供一致的提交 → 轮询 → 下载接口。
# =====================================================================

from .base import VideoJobParams, VideoJobResponse, VideoJobStatus, VideoProvider
from .registry import ProviderRegistry, get_provider, get_registry, list_providers

__all__ = [
    "VideoProvider",
    "VideoJobParams",
    "VideoJobResponse",
    "VideoJobStatus",
    "ProviderRegistry",
    "get_provider",
    "get_registry",
    "list_providers",
]
