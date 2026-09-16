# =====================================================================
# deps.py —— API 层的依赖入口
#
# 路由统一通过 `from . import deps` 再 `deps.store()` 取值，而不是
# `from ..deps import store` 直接绑名字。这样有两个好处：
#   1. 测试里 monkeypatch `app.api.deps.store` 就能整体替换依赖，
#      不必逐个路由模块打补丁；
#   2. 依赖查找始终是运行时的，晚绑定不会拿到过期引用。
#
# 真正的单例定义在 app/deps.py（全项目唯一装配点）。
# =====================================================================

from __future__ import annotations

from ..deps import (  # noqa: F401
    llm,
    plugin_registry,
    settings,
    store,
    subagent_runner,
    video_manager,
)

__all__ = [
    "llm",
    "plugin_registry",
    "settings",
    "store",
    "subagent_runner",
    "video_manager",
]
