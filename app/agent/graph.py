# =====================================================================
# graph.py —— LangGraph 状态图编排（无 RAG 版）
#
# 图的拓扑：
#   START -> context -> plan -> (tools -> plan)*ReAct 循环
#             plan -> propose -> guard(自纠错) -> review(interrupt)
#                    -> apply -> finalize -> END
#
# 与旧版的区别：去掉了 vector/embedder 参数，知识直接从内存/DB 读取。
# =====================================================================

from __future__ import annotations

import logging
import re
from collections import OrderedDict
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..config import Settings
from ..domain import Script
from ..llm import LLM
from .nodes import MAX_PROPOSE_ITERATIONS, build_nodes
from .state import AgentState
from ..store import Project, Store
from .tools import build_tools

log = logging.getLogger(__name__)

# ReAct 工具循环的最大轮数，避免死循环。
MAX_TOOL_STEPS = 8

# 模块级 checkpointer 单例。
_CHECKPOINTER: Any = None

# 编译后的图缓存。
_GRAPH_CACHE: OrderedDict[str, Any] = OrderedDict()
_GRAPH_CACHE_MAX = 16


def _normalize_pg_dsn(dsn: str) -> str:
    """把 SQLAlchemy 风格的 `postgresql+psycopg://` 转成 psycopg 的 `postgresql://`。"""
    return re.sub(r"^postgresql\+psycopg", "postgresql", dsn)


def get_checkpointer(settings: Settings):
    """返回 checkpointer 单例：postgres（跨重启）或内存（本地/离线）。"""
    global _CHECKPOINTER
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER
    if settings.checkpointer == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver

            dsn = _normalize_pg_dsn(settings.effective_checkpoint_dsn)
            saver: Any
            try:
                from psycopg_pool import ConnectionPool

                pool = ConnectionPool(dsn, kwargs={"autocommit": True}, open=True)
                saver = PostgresSaver(pool)
                log.info("使用 Postgres checkpointer（连接池）")
            except ImportError:
                import psycopg

                conn = psycopg.connect(dsn, autocommit=True)
                saver = PostgresSaver(conn)
                log.info("使用 Postgres checkpointer（单连接，未安装 psycopg-pool）")
            saver.setup()
            _CHECKPOINTER = saver
            return saver
        except Exception as e:  # noqa: BLE001
            log.warning("Postgres checkpointer 初始化失败，回退为内存：%s", e)
    from langgraph.checkpoint.memory import InMemorySaver

    _CHECKPOINTER = InMemorySaver()
    return _CHECKPOINTER


def _route_after_plan(state: AgentState) -> str:
    """plan 节点之后路由：有工具调用则进 tools，否则进入 propose。"""
    if not state.get("model_available", False):
        return "propose"
    if state.get("steps", 0) >= MAX_TOOL_STEPS:
        return "propose"
    from langgraph.prebuilt import tools_condition

    return tools_condition(state) or "propose"


def _route_after_review(state: AgentState) -> str:
    """review 节点之后路由。"""
    decision = state.get("decision") or {}
    action = decision.get("action", "reject")
    if action in ("accept", "edit"):
        return "apply"
    if action == "regenerate":
        return "propose"
    return "finalize"


def _route_after_guard(state: AgentState) -> str:
    """guard（自纠错）之后路由。"""
    critique = state.get("critique") or []
    iterations = state.get("iterations", 0)
    if critique and iterations < MAX_PROPOSE_ITERATIONS:
        return "propose"
    return "review"


def _get_compiled(base_version_id: str, builder: Any) -> Any:
    """按 base 版本取已编译图；缺失则构建并缓存。"""
    graph = _GRAPH_CACHE.get(base_version_id)
    if graph is not None:
        _GRAPH_CACHE.move_to_end(base_version_id)
        return graph
    graph = builder.compile()
    _GRAPH_CACHE[base_version_id] = graph
    while len(_GRAPH_CACHE) > _GRAPH_CACHE_MAX:
        _GRAPH_CACHE.popitem(last=False)
    return graph


class _GraphBuilder:
    """把本次运行的依赖打包，用于构建并可复用编译同一张图。"""

    def __init__(
        self,
        *,
        store: Store,
        llm: LLM,
        settings: Settings,
        project: Project,
        base_script: Script,
        raw_text: str,
        base_version_id: str,
    ) -> None:
        self.store = store
        self.llm = llm
        self.settings = settings
        self.project = project
        self.base_script = base_script
        self.raw_text = raw_text
        self.base_version_id = base_version_id

    def compile(self) -> Any:
        """构建并编译 Agent 图。"""
        tools = build_tools(self.base_script, self.project, self.store, self.raw_text)
        nodes = build_nodes(
            self.store,
            self.llm,
            self.base_script,
            self.project,
            self.raw_text,
            settings=self.settings,
            tools=tools,
        )

        graph = StateGraph(AgentState)
        graph.add_node("context", nodes["context"])
        graph.add_node("plan", nodes["plan"])
        graph.add_node("propose", nodes["propose"])
        graph.add_node("guard", nodes["guard"])
        graph.add_node("review", nodes["review"])
        graph.add_node("apply", nodes["apply"])
        graph.add_node("finalize", nodes["finalize"])

        from langgraph.prebuilt import ToolNode

        base_tool_node = ToolNode(tools)

        def tools_step(state: AgentState) -> dict[str, Any]:
            """执行工具并累计轮数。"""
            out = base_tool_node.invoke(state)
            update = dict(out) if isinstance(out, dict) else {}
            update["steps"] = int(state.get("steps", 0)) + 1
            return update

        graph.add_node("tools", tools_step)

        graph.add_edge(START, "context")
        graph.add_edge("context", "plan")
        graph.add_conditional_edges(
            "plan",
            _route_after_plan,
            {"tools": "tools", "propose": "propose", "__end__": "propose"},
        )
        graph.add_edge("tools", "plan")
        graph.add_edge("propose", "guard")
        graph.add_conditional_edges(
            "guard",
            _route_after_guard,
            {"propose": "propose", "review": "review"},
        )
        graph.add_conditional_edges(
            "review",
            _route_after_review,
            {"apply": "apply", "propose": "propose", "finalize": "finalize"},
        )
        graph.add_edge("apply", "finalize")
        graph.add_edge("finalize", END)

        return graph.compile(checkpointer=get_checkpointer(self.settings))


def build_run_graph(
    store: Store,
    llm: LLM,
    settings: Settings,
    *,
    project: Project,
    base_script: Script,
    raw_text: str,
    base_version_id: str,
) -> Any:
    """为一个具体的 base 版本构建（并缓存）Agent 图。"""
    builder = _GraphBuilder(
        store=store,
        llm=llm,
        settings=settings,
        project=project,
        base_script=base_script,
        raw_text=raw_text,
        base_version_id=base_version_id,
    )
    return _get_compiled(base_version_id, builder)


def thread_config(run_id: str) -> dict[str, Any]:
    """为一次运行构造统一的 thread 配置。"""
    return {"configurable": {"thread_id": run_id}}
