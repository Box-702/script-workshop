# =====================================================================
# mcp.py —— MCP (Model Context Protocol) 适配器
#
# 连接外部 MCP Server，将其工具转为 LangChain Tool。
# 支持两种传输：
#   - stdio：启动子进程，通过 stdin/stdout 通信
#   - HTTP：连接远程 MCP Server（Streamable HTTP）
# =====================================================================

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from langchain_core.tools import BaseTool, tool

from .base import MCPServerDef

log = logging.getLogger(__name__)


class MCPConnection:
    """MCP Server 连接。"""

    def __init__(self, server_def: MCPServerDef) -> None:
        self._def = server_def
        self._process: subprocess.Popen | None = None
        self._tools: list[dict[str, Any]] = []
        self._connected = False

    async def connect(self) -> bool:
        """启动 MCP Server 进程。"""
        if self._def.url:
            # HTTP 传输（暂不实现完整协议，只记录 URL）
            self._connected = True
            return True

        if not self._def.command:
            return False

        try:
            import os
            env = {**os.environ, **self._def.env}
            self._process = subprocess.Popen(
                [self._def.command, *self._def.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
            )
            # 发送 initialize 请求
            init_msg = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "script-workshop", "version": "0.3.0"},
                },
            }
            self._send(init_msg)
            resp = self._recv()
            if resp and "result" in resp:
                self._connected = True
                # 发送 initialized 通知
                self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                return True
        except Exception as e:  # noqa: BLE001
            log.warning("连接 MCP Server 失败：%s", e)
        return False

    async def list_tools(self) -> list[dict[str, Any]]:
        """获取 MCP Server 提供的工具列表。"""
        if not self._connected:
            return []
        try:
            self._send({
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
            })
            resp = self._recv()
            if resp and "result" in resp:
                self._tools = resp["result"].get("tools", [])
                return self._tools
        except Exception as e:  # noqa: BLE001
            log.warning("MCP tools/list 失败：%s", e)
        return []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        """调用 MCP Server 的工具。"""
        if not self._connected:
            raise RuntimeError("MCP Server 未连接")
        try:
            self._send({
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            })
            resp = self._recv()
            if resp and "result" in resp:
                content = resp["result"].get("content", [])
                # 提取文本内容
                texts = [c.get("text", "") for c in content if c.get("type") == "text"]
                return "\n".join(texts) if texts else str(content)
            elif resp and "error" in resp:
                raise RuntimeError(resp["error"].get("message", "Unknown error"))
        except Exception as e:  # noqa: BLE001
            log.warning("MCP tools/call %s 失败：%s", name, e)
            raise
        return ""

    async def disconnect(self) -> None:
        """断开 MCP Server 连接。"""
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=5)
            except Exception:
                self._process.kill()
            self._process = None
        self._connected = False

    def _send(self, msg: dict[str, Any]) -> None:
        """发送 JSON-RPC 消息。"""
        if not self._process or not self._process.stdin:
            return
        data = json.dumps(msg) + "\n"
        self._process.stdin.write(data)
        self._process.stdin.flush()

    def _recv(self) -> dict[str, Any] | None:
        """接收 JSON-RPC 响应。"""
        if not self._process or not self._process.stdout:
            return None
        line = self._process.stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line.strip())
        except json.JSONDecodeError:
            return None


def mcp_tools_to_langchain(
    mcp_tools: list[dict[str, Any]],
    connection: MCPConnection,
) -> list[BaseTool]:
    """将 MCP 工具定义转为 LangChain Tool 列表。"""

    lc_tools: list[BaseTool] = []

    for mcp_tool in mcp_tools:
        name = mcp_tool.get("name", "")
        description = mcp_tool.get("description", "")
        input_schema = mcp_tool.get("inputSchema", {})
        properties = input_schema.get("properties", {})
        required = set(input_schema.get("required", []))

        # 为每个 MCP 工具创建一个闭包调用
        def _make_caller(tool_name: str, conn: MCPConnection):
            def _call(**kwargs: Any) -> str:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        import concurrent.futures
                        with concurrent.futures.ThreadPoolExecutor() as pool:
                            future = pool.submit(asyncio.run, conn.call_tool(tool_name, kwargs))
                            return future.result(timeout=60)
                    return asyncio.run(conn.call_tool(tool_name, kwargs))
                except Exception as e:
                    return f"MCP 工具调用失败：{e}"
            return _call

        caller = _make_caller(name, connection)

        # 构造参数描述
        param_descs = []
        for pname, pdef in properties.items():
            req = "（必需）" if pname in required else "（可选）"
            param_descs.append(f"- {pname}: {pdef.get('description', pdef.get('type', ''))} {req}")

        full_desc = description
        if param_descs:
            full_desc += "\n参数：\n" + "\n".join(param_descs)

        # 使用 @tool 包装
        lc_tool = tool(name=name, description=full_desc)(caller)
        lc_tools.append(lc_tool)

    return lc_tools
