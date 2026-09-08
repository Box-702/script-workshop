# =====================================================================
# providers —— 视频生成 Provider 适配器
#
# 每个模块实现一个 VideoProvider 子类，封装对应 API 的认证、提交、轮询逻辑。
# =====================================================================

from .cogvideo import CogVideoProvider
from .kling import KlingProvider
from .minimax import MiniMaxProvider
from .runway import RunwayProvider
from .sora import SoraProvider

__all__ = [
    "RunwayProvider",
    "KlingProvider",
    "CogVideoProvider",
    "SoraProvider",
    "MiniMaxProvider",
]
