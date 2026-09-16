# =====================================================================
# base.py —— 插件基础模型
#
# 定义插件的清单格式、类型枚举、以及 Plugin 运行时对象。
# =====================================================================

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from langchain_core.tools import BaseTool

log = logging.getLogger(__name__)


class PluginType(str, Enum):
    """插件类型。"""
    TOOL = "tool"
    AGENT = "agent"
    SKILL = "skill"


@dataclass
class ToolParamDef:
    """工具参数定义（来自 plugin.yaml）。"""
    name: str
    type: str = "string"
    description: str = ""
    required: bool = False
    default: Any = None
    enum: list[str] | None = None


@dataclass
class ToolDef:
    """工具定义（来自 plugin.yaml 的 tools 列表项）。"""
    name: str
    description: str = ""
    parameters: list[ToolParamDef] = field(default_factory=list)


@dataclass
class MCPServerDef:
    """MCP Server 定义（来自 plugin.yaml 的 mcp 段）。"""
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""  # HTTP 传输的远程 URL


@dataclass
class PluginManifest:
    """插件清单（解析自 plugin.yaml）。

    这是插件的「声明」层——描述插件是什么、提供什么能力。
    """
    name: str
    version: str = "1.0"
    description: str = ""
    author: str = ""
    type: PluginType = PluginType.TOOL
    tools: list[ToolDef] = field(default_factory=list)
    mcp: MCPServerDef | None = None
    config_schema: dict[str, Any] = field(default_factory=dict)
    # ---- 运行时填充 ----
    path: Path = field(default_factory=Path)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "type": self.type.value,
            "tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "parameters": [
                        {"name": p.name, "type": p.type, "description": p.description,
                         "required": p.required, "default": p.default, "enum": p.enum}
                        for p in t.parameters
                    ],
                }
                for t in self.tools
            ],
            "mcp": {
                "command": self.mcp.command,
                "args": self.mcp.args,
                "url": self.mcp.url,
            } if self.mcp else None,
            "config_schema": self.config_schema,
            "path": str(self.path),
            "enabled": self.enabled,
        }


@dataclass
class Plugin:
    """插件运行时对象。

    包含清单 + 已加载的工具/Agent 实例。
    """
    manifest: PluginManifest
    langchain_tools: list[BaseTool] = field(default_factory=list)
    crew_agents: list[Any] = field(default_factory=list)
    mcp_tools: list[BaseTool] = field(default_factory=list)
    error: str | None = None

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def enabled(self) -> bool:
        return self.manifest.enabled

    def all_tools(self) -> list[BaseTool]:
        """返回该插件提供的所有 LangChain 工具。"""
        return self.langchain_tools + self.mcp_tools

    def to_dict(self) -> dict[str, Any]:
        d = self.manifest.to_dict()
        d["tool_count"] = len(self.all_tools())
        d["agent_count"] = len(self.crew_agents)
        d["error"] = self.error
        return d
