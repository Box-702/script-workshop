# =====================================================================
# plugin —— 万物皆插件系统
#
# 提供插件发现、加载、注册、执行的完整生命周期。
# 插件类型：tool（自定义工具，Agent 可调用）。
#
# 插件来源（优先级从高到低，同名高优先级生效）：
#   - 项目级插件（<project>/.plugins/，构造 PluginLoader 时传 project_dir）
#   - 用户级插件（~/.script-workshop/plugins/）
#   - 内置插件（app/plugins/builtin/）
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
