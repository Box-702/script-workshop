# =====================================================================
# agent_runs.py —— 改编智能体的运行与审阅
#
# 启动一次运行（跑到 interrupt 等待审阅）、查询运行、恢复运行
# （接受 / 编辑 / 重新生成 / 拒绝）。业务在 app/agent/runner.py。
# =====================================================================

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ..agent import runner as agent_svc
from . import common, deps
from .schemas import AcceptRequest, AgentRunRequest, ResumeRequest

router = APIRouter()


@router.post("/projects/{project_id}/agent/run")
def start_run(project_id: str, payload: AgentRunRequest) -> dict[str, Any]:
    p = common.get_project(project_id)
    base_version = None
    if payload.base_version_id:
        base_version = deps.store().get_version(payload.base_version_id)
        if not base_version:
            raise HTTPException(404, "基础版本不存在")
    if base_version is None:
        base_version = deps.store().latest_version(p)
    if base_version is None:
        raise HTTPException(400, "请先生成剧本版本")

    return agent_svc.start_agent_run(
        deps.store(), deps.llm(), deps.settings(),
        project=p,
        base_version=base_version,
        instruction=payload.instruction,
        scene_ids=payload.scene_ids,
    )


@router.get("/agent/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = agent_svc.get_run(deps.store(), run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    return run


@router.get("/projects/{project_id}/runs")
def list_runs(project_id: str) -> list[dict[str, Any]]:
    """列出某项目的 Agent 运行历史（供前端展示）。"""
    runs = deps.store().list_agent_runs(project_id)
    return [
        {
            "run_id": r.id,
            "status": r.status,
            "instruction": r.user_prompt,
            "steps": r.steps,
            "decision": r.decision,
            "created_at": r.created_at.isoformat(),
        }
        for r in runs
    ]


@router.post("/agent/runs/{run_id}/resume")
def resume_run(run_id: str, payload: ResumeRequest) -> dict[str, Any]:
    """在中断处提交人类决策：接受 / 编辑 / 重新生成 / 拒绝。"""
    return agent_svc.resume_agent_run(
        deps.store(), deps.llm(), deps.settings(),
        run_id=run_id,
        action=payload.action,
        patch_indexes=payload.patch_indexes,
        patch=payload.patch,
        feedback=payload.feedback,
    )


@router.post("/agent/runs/{run_id}/accept")
def accept_run(run_id: str, payload: AcceptRequest) -> dict[str, Any]:
    return agent_svc.resume_agent_run(
        deps.store(), deps.llm(), deps.settings(),
        run_id=run_id,
        action="accept",
        patch_indexes=payload.patch_indexes,
    )


@router.post("/agent/runs/{run_id}/reject")
def reject_run(run_id: str) -> dict[str, Any]:
    return agent_svc.resume_agent_run(
        deps.store(), deps.llm(), deps.settings(),
        run_id=run_id,
        action="reject",
        patch_indexes=None,
    )
