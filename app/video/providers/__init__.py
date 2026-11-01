# =====================================================================
# providers —— 视频生成 Provider 适配器
#
# 产品只走 MiniMax 一家（见 D-08）。这里曾经有 Runway / Kling / CogVideo /
# Sora 四个适配器，全都从未被启用过——它们只是把「将来可能支持」写成了代码，
# 代价是每次改 VideoProvider 接口都要跟着改四份没人跑的实现。
#
# 现在只保留产线里真的在跑的那一个。要加新厂商时，按 base.VideoProvider 实现
# 一个模块、在 registry._register_builtins 里注册一行即可——接口已经足够稳定，
# 不需要提前占位。
# =====================================================================

from .minimax import MiniMaxProvider

__all__ = ["MiniMaxProvider"]
