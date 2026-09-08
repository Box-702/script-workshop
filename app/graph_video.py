# =====================================================================
# graph_video.py —— 导演组 LangGraph 子图
#
# 编排导演 → 美术指导 → 摄影指导的流水线：
#   START → director → art_director → dp → finalize → END
#
# 在 director 和 dp 节点后设有 HITL 中断点，
# 用户可以审批、修改或退回重做。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from typing_extensions import TypedDict

from .crew import run_art_director, run_director, run_dp
from .domain import SceneBreakdown, Script, StyleGuide
from .llm import LLM

log = logging.getLogger(__name__)


# ---- 状态 ----


class VideoPipelineState(TypedDict, total=False):
    """导演组流水线状态。"""

    script: Script
    scene_ids: list[str] | None

    # 中间产物
    breakdowns: list[dict[str, Any]]  # SceneBreakdown 序列化
    style_guide: dict[str, Any]  # StyleGuide 序列化
    shots: list[dict[str, Any]]  # Shot 序列化（含 video_prompt）

    # 流水线控制
    stage: str  # director / art_director / dp / finalize
    errors: list[str]
    summary: str

    # HITL 审批
    approval: str  # approved / edited / rejected


# ---- 节点 ----


def node_director(state: VideoPipelineState, llm: LLM) -> dict[str, Any]:
    """导演节点：场景拆解为镜头。"""
    script = state["script"]
    scene_ids = state.get("scene_ids")

    result = run_director(llm, script, scene_ids=scene_ids)

    if not result.success:
        return {
            "stage": "director",
            "errors": state.get("errors", []) + result.errors,
            "summary": result.summary,
        }

    breakdowns = [b.model_dump() for b in result.data]
    return {
        "breakdowns": breakdowns,
        "stage": "director",
        "summary": result.summary,
    }


def node_director_review(state: VideoPipelineState) -> dict[str, Any]:
    """导演审批节点（HITL）：用户审核镜头拆解方案。"""
    breakdowns = state.get("breakdowns", [])
    if not breakdowns:
        return {"approval": "approved"}

    # 中断等待用户审批
    decision = interrupt({
        "type": "director_review",
        "stage": "分镜方案审批",
        "breakdowns": breakdowns,
        "summary": state.get("summary", ""),
        "message": "导演已完成场景拆解，请审核镜头方案",
    })

    return {"approval": decision.get("action", "approved")}


def node_art_director(state: VideoPipelineState, llm: LLM) -> dict[str, Any]:
    """美术指导节点：生成视觉风格指南。"""
    script = state["script"]

    # 收集导演备注作为参考
    breakdowns = state.get("breakdowns", [])
    director_notes = ""
    if breakdowns:
        notes = [b.get("director_notes", "") for b in breakdowns if b.get("director_notes")]
        director_notes = "\n".join(notes[:3])

    result = run_art_director(llm, script, director_notes=director_notes)

    if not result.success:
        return {
            "stage": "art_director",
            "errors": state.get("errors", []) + result.errors,
        }

    return {
        "style_guide": result.data.model_dump(),
        "stage": "art_director",
        "summary": state.get("summary", "") + " | " + result.summary,
    }


def node_dp(state: VideoPipelineState, llm: LLM) -> dict[str, Any]:
    """摄影指导节点：为镜头生成视频 Prompt。"""
    script = state["script"]

    # 重建领域对象
    breakdowns = [SceneBreakdown.model_validate(b) for b in state.get("breakdowns", [])]
    style_guide = StyleGuide.model_validate(state.get("style_guide", {}))

    result = run_dp(llm, script, breakdowns=breakdowns, style_guide=style_guide)

    if not result.success:
        return {
            "stage": "dp",
            "errors": state.get("errors", []) + result.errors,
            "summary": result.summary,
        }

    shots = [s.model_dump() for s in result.data]
    return {
        "shots": shots,
        "stage": "dp",
        "summary": state.get("summary", "") + " | " + result.summary,
    }


def node_dp_review(state: VideoPipelineState) -> dict[str, Any]:
    """摄影指导审批节点（HITL）：用户审核视频 Prompt。"""
    shots = state.get("shots", [])
    if not shots:
        return {"approval": "approved"}

    decision = interrupt({
        "type": "dp_review",
        "stage": "视频 Prompt 审批",
        "shots": shots,
        "summary": state.get("summary", ""),
        "message": "摄影指导已为每个镜头生成视频 Prompt，请审核",
    })

    return {"approval": decision.get("action", "approved")}


def node_finalize(state: VideoPipelineState) -> dict[str, Any]:
    """最终节点：汇总结果。"""
    return {
        "stage": "finalize",
        "summary": state.get("summary", "") + " | 流水线完成",
    }


# ---- 条件路由 ----


def route_after_director_review(state: VideoPipelineState) -> str:
    """导演审批后路由。"""
    approval = state.get("approval", "approved")
    if approval == "rejected":
        return END
    return "art_director"


def route_after_dp_review(state: VideoPipelineState) -> str:
    """摄影指导审批后路由。"""
    approval = state.get("approval", "approved")
    if approval == "rejected":
        return END
    return "finalize"


# ---- 图构建 ----


def build_video_graph(llm: LLM) -> Any:
    """构建导演组 LangGraph 子图。

    流程：
    START → director → director_review(HITL) → art_director → dp → dp_review(HITL) → finalize → END
    """
    graph = StateGraph(VideoPipelineState)

    # 注册节点（用 lambda 闭包注入 llm）
    graph.add_node("director", lambda s: node_director(s, llm))
    graph.add_node("director_review", node_director_review)
    graph.add_node("art_director", lambda s: node_art_director(s, llm))
    graph.add_node("dp", lambda s: node_dp(s, llm))
    graph.add_node("dp_review", node_dp_review)
    graph.add_node("finalize", node_finalize)

    # 连接边
    graph.add_edge(START, "director")
    graph.add_edge("director", "director_review")
    graph.add_conditional_edges("director_review", route_after_director_review, {
        "art_director": "art_director",
        END: END,
    })
    graph.add_edge("art_director", "dp")
    graph.add_edge("dp", "dp_review")
    graph.add_conditional_edges("dp_review", route_after_dp_review, {
        "finalize": "finalize",
        END: END,
    })
    graph.add_edge("finalize", END)

    return graph.compile()


def build_video_graph_no_hitl(llm: LLM) -> Any:
    """构建无 HITL 中断的导演组子图（全自动模式）。

    流程：
    START → director → art_director → dp → finalize → END
    """
    graph = StateGraph(VideoPipelineState)

    graph.add_node("director", lambda s: node_director(s, llm))
    graph.add_node("art_director", lambda s: node_art_director(s, llm))
    graph.add_node("dp", lambda s: node_dp(s, llm))
    graph.add_node("finalize", node_finalize)

    graph.add_edge(START, "director")
    graph.add_edge("director", "art_director")
    graph.add_edge("art_director", "dp")
    graph.add_edge("dp", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
