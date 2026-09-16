# =====================================================================
# plugin —— 万物皆插件系统
#
# 提供插件发现、加载、注册、执行的完整生命周期。
# 支持三种插件类型：
#   - tool：自定义工具（Agent 可调用）
#   - agent：自定义 Agent（剧组成员）
#   - skill：技能指令（用户可触发）
#
# 插件来源：
#   - 内置插件（app/plugins/builtin/）
#   - 用户级插件（~/.script-workshop/plugins/）
#   - 项目级插件（<project>/.plugins/）
# =====================================================================

from .base import Plugin, PluginManifest, PluginType
from .loader import PluginLoader
from .registry import PluginRegistry, get_plugin_registry

__all__ = [
    "Plugin",
    "PluginManifest",
    "PluginType",
    "PluginLoader",
    "PluginRegistry",
    "get_plugin_registry",
]
