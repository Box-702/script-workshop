# =====================================================================
# registry.py —— 插件注册表
#
# 管理已加载的插件，提供查询、启用/禁用、工具收集等接口。
# =====================================================================

from __future__ import annotations

import logging
import threading
from typing import Any

from langchain_core.tools import BaseTool

from .base import Plugin
from .loader import PluginLoader

log = logging.getLogger(__name__)


class PluginRegistry:
    """插件注册表。

    职责：
      - 持有已加载的 Plugin 实例
      - 提供按名称查找、启用/禁用
      - 收集所有已启用插件的 LangChain 工具
    """

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin] = {}
        self._lock = threading.Lock()

    def register(self, plugin: Plugin) -> None:
        """注册一个插件。"""
        with self._lock:
            self._plugins[plugin.name] = plugin
            log.debug("注册插件：%s (enabled=%s)", plugin.name, plugin.enabled)

    def list_plugins(self) -> list[dict[str, Any]]:
        """列出所有插件的摘要信息。"""
        with self._lock:
            return [p.to_dict() for p in self._plugins.values()]

    def list_enabled(self) -> list[Plugin]:
        """列出所有已启用的插件。"""
        with self._lock:
            return [p for p in self._plugins.values() if p.enabled and not p.error]

    def get_all_tools(self) -> list[BaseTool]:
        """收集所有已启用插件的 LangChain 工具。"""
        tools: list[BaseTool] = []
        for plugin in self.list_enabled():
            tools.extend(plugin.all_tools())
        return tools

    def enable(self, name: str) -> bool:
        """启用插件。"""
        with self._lock:
            p = self._plugins.get(name)
            if not p:
                return False
            p.manifest.enabled = True
            return True

    def disable(self, name: str) -> bool:
        """禁用插件。"""
        with self._lock:
            p = self._plugins.get(name)
            if not p:
                return False
            p.manifest.enabled = False
            return True

    def uninstall(self, name: str) -> bool:
        """卸载插件（从注册表移除 + 删除磁盘文件）。"""
        with self._lock:
            p = self._plugins.get(name)
            if not p:
                return False
            # 删除磁盘文件
            plugin_dir = p.manifest.path
            if plugin_dir.is_dir():
                import shutil
                shutil.rmtree(plugin_dir, ignore_errors=True)
                log.info("已删除插件目录：%s", plugin_dir)
            del self._plugins[name]
            return True

    def reload(self, name: str) -> bool:
        """重新加载插件。"""
        with self._lock:
            p = self._plugins.get(name)
            if not p:
                return False
            plugin_dir = p.manifest.path
            manifest_path = plugin_dir / "plugin.yaml"

        loader = PluginLoader()
        try:
            new_plugin = loader.load_plugin(plugin_dir, manifest_path)
            with self._lock:
                self._plugins[name] = new_plugin
            log.info("已重新加载插件：%s", name)
            return True
        except Exception as e:  # noqa: BLE001
            log.warning("重新加载插件 %s 失败：%s", name, e)
            return False


# ---- 全局单例 ----

_registry: PluginRegistry | None = None
_registry_lock = threading.Lock()


def get_plugin_registry(project_dir: str | None = None) -> PluginRegistry:
    """获取全局插件注册表单例。首次调用时自动扫描加载。"""
    global _registry
    if _registry is not None:
        return _registry
    with _registry_lock:
        if _registry is not None:
            return _registry
        _registry = PluginRegistry()
        loader = PluginLoader(project_dir=project_dir)
        for plugin in loader.discover():
            _registry.register(plugin)
        log.info("插件系统初始化完成，共加载 %d 个插件", len(_registry.list_plugins()))
    return _registry
