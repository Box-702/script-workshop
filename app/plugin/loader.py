# =====================================================================
# loader.py —— 插件加载器
#
# 从文件系统扫描、解析、加载插件。
# 扫描顺序（优先级从高到低）：
#   1. <project>/.plugins/       （项目级）
#   2. ~/.script-workshop/plugins/ （用户级）
#   3. app/plugins/builtin/      （内置）
# =====================================================================

from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Any

import yaml

from .base import (
    Plugin,
    PluginManifest,
    PluginType,
    ToolDef,
    ToolParamDef,
)

log = logging.getLogger(__name__)

# 插件扫描目录（按优先级排序）。
_USER_PLUGINS_DIR = Path.home() / ".script-workshop" / "plugins"
_BUILTIN_DIR = Path(__file__).parent.parent / "plugins" / "builtin"


class PluginLoader:
    """插件加载器：扫描文件系统、解析清单、加载 Python 模块。"""

    def __init__(self, project_dir: str | Path | None = None) -> None:
        self._project_dir = Path(project_dir) if project_dir else None

    def discover(self) -> list[Plugin]:
        """扫描所有插件目录，返回已加载的 Plugin 列表。"""
        plugins: list[Plugin] = []
        seen_names: set[str] = set()

        for scan_dir in self._scan_dirs():
            if not scan_dir.is_dir():
                continue
            for entry in sorted(scan_dir.iterdir()):
                if not entry.is_dir() or entry.name.startswith("."):
                    continue
                manifest_path = entry / "plugin.yaml"
                if not manifest_path.is_file():
                    continue
                try:
                    plugin = self.load_plugin(entry, manifest_path)
                    if plugin.name in seen_names:
                        log.debug("跳过重复插件 %s（来自 %s）", plugin.name, entry)
                        continue
                    seen_names.add(plugin.name)
                    plugins.append(plugin)
                    log.info("加载插件：%s v%s (%s)", plugin.name, plugin.manifest.version, entry)
                except Exception as e:  # noqa: BLE001
                    log.warning("加载插件 %s 失败：%s", entry.name, e)
                    # 创建一个带错误信息的占位 Plugin
                    plugins.append(Plugin(
                        manifest=PluginManifest(name=entry.name, path=entry),
                        error=str(e),
                    ))

        return plugins

    def _scan_dirs(self) -> list[Path]:
        """返回插件扫描目录列表（按优先级）。"""
        dirs: list[Path] = []
        if self._project_dir:
            proj_plugins = self._project_dir / ".plugins"
            dirs.append(proj_plugins)
        dirs.append(_USER_PLUGINS_DIR)
        dirs.append(_BUILTIN_DIR)
        return dirs

    def load_plugin(self, plugin_dir: Path, manifest_path: Path) -> Plugin:
        """加载单个插件：解析清单 + 加载 Python 模块。"""
        manifest = self._parse_manifest(manifest_path, plugin_dir)
        plugin = Plugin(manifest=manifest)

        # 加载 tools.py
        tools_py = plugin_dir / "tools.py"
        if tools_py.is_file():
            plugin.langchain_tools = self._load_tools_from_py(tools_py, manifest.tools)

        return plugin

    def _parse_manifest(self, path: Path, plugin_dir: Path) -> PluginManifest:
        """解析 plugin.yaml 清单文件。"""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        name = data.get("name", plugin_dir.name)
        if not isinstance(name, str) or not name:
            name = plugin_dir.name

        plugin_type = PluginType.TOOL
        raw_type = data.get("type", "tool")
        try:
            plugin_type = PluginType(raw_type)
        except ValueError:
            log.warning("未知插件类型 %s，回退为 tool", raw_type)

        tools: list[ToolDef] = []
        for t in data.get("tools", []):
            params = []
            for pname, pdef in (t.get("parameters") or {}).items():
                params.append(ToolParamDef(
                    name=pname,
                    type=pdef.get("type", "string"),
                    description=pdef.get("description", ""),
                    required=pdef.get("required", False),
                    default=pdef.get("default"),
                    enum=pdef.get("enum"),
                ))
            tools.append(ToolDef(
                name=t.get("name", ""),
                description=t.get("description", ""),
                parameters=params,
            ))

        return PluginManifest(
            name=name,
            version=str(data.get("version", "1.0")),
            description=data.get("description", ""),
            author=data.get("author", ""),
            type=plugin_type,
            tools=tools,
            config_schema=data.get("config", {}),
            path=plugin_dir,
        )

    def _load_tools_from_py(self, py_path: Path, tool_defs: list[ToolDef]) -> list[Any]:
        """从 tools.py 加载 @tool 装饰的函数。"""
        spec = importlib.util.spec_from_file_location(
            f"_plugin_{py_path.parent.name}_tools", str(py_path)
        )
        if spec is None or spec.loader is None:
            return []
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:  # noqa: BLE001
            log.warning("执行 %s 失败：%s", py_path, e)
            return []

        tools: list[Any] = []
        # 优先找 @tool 装饰的函数
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if hasattr(attr, "name") and hasattr(attr, "invoke"):
                # LangChain BaseTool
                tools.append(attr)

        # 如果没有找到 @tool，尝试根据清单中的 tools 定义从模块中找对应函数
        if not tools:
            for td in tool_defs:
                func = getattr(module, td.name, None)
                if func and callable(func):
                    # 包装为 LangChain tool
                    from langchain_core.tools import tool as lc_tool
                    wrapped = lc_tool(func)
                    tools.append(wrapped)

        return tools
