# =====================================================================
# graph.py —— LangGraph 状态图编排
#
# 这是整个项目的「智能体中枢」。它把节点与边组装成一个有状态的有向图，
# 并连上 checkpointer 以实现「中断 -> 用户审阅 -> 恢复」的人机协同。
#
# 图的拓扑：
#   START -> context -> plan -> (tools -> plan)*ReAct 循环
#             plan -> propose -> review(interrupt) -> apply -> finalize -> END
#                                        └────────> finalize -> END   (拒绝)
#
# 体现的 LangGraph 能力：
#   1. StateGraph + 条件边：根据模型是否调用工具 / 用户是否接受来路由；
#   2. ReAct 循环：模型绑定工具，ToolNode 执行，结果回流给模型；
#   3. 结构化输出：propose 节点用 with_structured_output 产出 Pydantic 提议；
#   4. 人机协同：review 节点用 interrupt 暂停，用户决定后 Command(resume=...) 恢复；
#   5. checkpointer：内存 / Postgres，支撑跨请求、跨重启恢复。
#
# 注意：checkpointer 必须是模块级单例。若每次请求新建 InMemorySaver，
# 中断后的线程状态会丢失，导致 review 无法恢复。因此统一由
# get_checkpointer() 提供；编译后的图按 base 版本缓存复用，恢复时用同一实例。
# =====================================================================

from __future__ import annotations

import logging
import re
from typing import Any

from langgraph.graph import END, START, StateGraph

from .config import Settings
from .domain import Script
from .llm import LLM
from .nodes import MAX_PROPOSE_ITERATIONS, build_nodes
from .state import AgentState
from .store import Project, Store
from .tools import Retriever, build_tools
from .vector import VectorStore

log = logging.getLogger(__name__)

# ReAct 工具循环的最大轮数，避免死循环。
MAX_TOOL_STEPS = 8

# 模块级 checkpointer 单例。
_CHECKPOINTER: Any = None

# 编译后的图缓存：同一 base 版本复用同一实例，保证 invoke / resume 用同一张图。
_GRAPH_CACHE: dict[str, Any] = {}


def _normalize_pg_dsn(dsn: str) -> str:
    """把 SQLAlchemy 风格的 `postgresql+psycopg://` 转成 psycopg 的 `postgresql://`。"""
    return re.sub(r"^postgresql\+psycopg", "postgresql", dsn)


def get_checkpointer(settings: Settings):
    """返回 checkpointer 单例：postgres（跨重启）或内存（本地/离线）。

    若配置了 postgres 但初始化失败（如数据库未就绪、缺驱动），
    会自动回退为内存 checkpointer，保证服务仍能启动。
    """
    global _CHECKPOINTER
    if _CHECKPOINTER is not None:
        return _CHECKPOINTER
    if settings.checkpointer == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
            import psycopg

            dsn = _normalize_pg_dsn(settings.effective_checkpoint_dsn)
            conn = psycopg.connect(dsn, autocommit=True)
            saver = PostgresSaver(conn)
            saver.setup()
            log.info("使用 Postgres checkpointer")
            _CHECKPOINTER = saver
            return saver
        except Exception as e:  # noqa: BLE001
            log.warning("Postgres checkpointer 初始化失败，回退为内存：%s", e)
    from langgraph.checkpoint.memory import InMemorySaver

    _CHECKPOINTER = InMemorySaver()
    return _CHECKPOINTER


def make_retriever(settings: Settings, vector: VectorStore, embedder: Any, project: Project) -> Retriever | None:
    """构造 RAG 检索器。

    不再以 enable_rag 作为「是否带工具」的门槛：向量后端本身就在 Milvus 不可达
    时退化为内存向量（见 build_vector_store），即便未显式开启 RAG，只要项目被
    索引进过知识库（create_project 时），就能按语义检索原文 / 知识。这样让
    「RAG 真正投入使用」而不仅是可选项。检索空结果时工具会安全返回空提示。
    """
    from .vector import retrieve

    def _retrieve(query: str, k: int) -> list[str]:
        try:
            return retrieve(vector, embedder, project_id=project.id, query=query, k=k)
        except Exception:  # noqa: BLE001
            return []

    return _retrieve


def make_knowledge_retriever(vector: VectorStore, embedder: Any, project: Project) -> Retriever | None:
    """构造「改编知识」检索器（同类剧本走向 / 写作手法 / 作者风格）。

    知识库与向量后端解耦：无论是否开启 Milvus（内存后端也可用），
    只要项目被索引进过知识库，改编工作流就能检索到相关知识。
    """
    from .knowledge import retrieve_knowledge

    def _retrieve(query: str, k: int, kinds: list[str] | None = None) -> list[dict]:
        try:
            return retrieve_knowledge(
                vector, embedder, project_id=project.id, query=query, k=k, kinds=kinds
            )
        except Exception:  # noqa: BLE001
            return []

    return _retrieve


def _route_after_plan(state: AgentState) -> str:
    """plan 节点之后路由：有工具调用则进 tools，否则进入 propose。"""
    if not state.get("model_available", False):
        return "propose"
    if state.get("steps", 0) >= MAX_TOOL_STEPS:
        return "propose"
    from langgraph.prebuilt import tools_condition

    return tools_condition(state) or "propose"


def _route_after_review(state: AgentState) -> str:
    """review 节点之后路由：
    - accept / edit  -> apply（落版，edit 采用人工修订的 patch）；
    - regenerate     -> propose（把反馈并入指令，重新提议）；
    - reject         -> finalize（拒绝）。
    """
    decision = state.get("decision") or {}
    action = decision.get("action", "reject")
    if action in ("accept", "edit"):
        return "apply"
    if action == "regenerate":
        return "propose"
    return "finalize"


def _route_after_guard(state: AgentState) -> str:
    """guard（自纠错）之后路由：还有问题且未超限则回到 propose 重做，否则进入 review。"""
    critique = state.get("critique") or []
    iterations = state.get("iterations", 0)
    if critique and iterations < MAX_PROPOSE_ITERATIONS:
        return "propose"
    return "review"


def _get_compiled(base_version_id: str, builder: Any) -> Any:
    """按 base 版本取已编译图；缺失则构建并缓存。"""
    if base_version_id not in _GRAPH_CACHE:
        _GRAPH_CACHE[base_version_id] = builder.compile()
    return _GRAPH_CACHE[base_version_id]


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
        vector: VectorStore,
        embedder: Any,
        base_version_id: str,
    ) -> None:
        self.store = store
        self.llm = llm
        self.settings = settings
        self.project = project
        self.base_script = base_script
        self.raw_text = raw_text
        self.vector = vector
        self.embedder = embedder
        self.base_version_id = base_version_id

    def compile(self) -> Any:
        """构建并编译 Agent 图。"""
        retriever = make_retriever(self.settings, self.vector, self.embedder, self.project)
        knowledge_retriever = make_knowledge_retriever(self.vector, self.embedder, self.project)
        tools = build_tools(self.base_script, self.project, self.store, self.raw_text, retriever=retriever)
        nodes = build_nodes(
            self.store,
            self.llm,
            self.base_script,
            self.project,
            self.raw_text,
            settings=self.settings,
            tools=tools,
            retriever=retriever,
            knowledge_retriever=knowledge_retriever,
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

        graph.add_node("tools", ToolNode(tools))

        graph.add_edge(START, "context")
        graph.add_edge("context", "plan")
        graph.add_conditional_edges(
            "plan",
            _route_after_plan,
            {"tools": "tools", "propose": "propose", "__end__": "propose"},
        )
        graph.add_edge("tools", "plan")  # 工具结果回流给模型，形成 ReAct 循环
        graph.add_edge("propose", "guard")
        # guard：自纠错 —— 有问题则回 propose 重做，否则交给人类审阅。
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
    vector: VectorStore,
    embedder: Any,
    base_version_id: str,
) -> Any:
    """为一个具体的 base 版本构建（并缓存）Agent 图。

    工具与节点需要通过闭包捕获本次运行的目标剧本，因此按 base 版本构建；
    同一 base 版本的多次运行复用同一张编译图，从而让 invoke / resume 命中
    同一个 checkpointer 线程状态。
    """
    builder = _GraphBuilder(
        store=store,
        llm=llm,
        settings=settings,
        project=project,
        base_script=base_script,
        raw_text=raw_text,
        vector=vector,
        embedder=embedder,
        base_version_id=base_version_id,
    )
    return _get_compiled(base_version_id, builder)


def thread_config(run_id: str) -> dict[str, Any]:
    """为一次运行构造统一的 thread 配置，用于把中断/恢复绑定到同一线程。"""
    return {"configurable": {"thread_id": run_id}}
