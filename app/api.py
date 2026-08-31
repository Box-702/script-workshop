# =====================================================================
# api.py —— REST API 路由
#
# 对外提供：项目创建/生成、版本查询、以及核心的「Agent 运行 ->
# 审阅 -> 接受/拒绝」接口。前端 Web 也走这些接口。
#
# 关注点分离：
#   - 路由只做参数校验与响应序列化；
#   - 真正的业务（生成、patch、版本、恢复）委托给
#     generation / agent / store 等模块。
# =====================================================================

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import agent as agent_svc
from .config import Settings
from .deps import embedder, llm, settings, store, vector
from .domain import Script
from .generation import generate_script
from .patch import validate_script
from .vector import index_project

router = APIRouter(prefix="/api")


# ---------- 请求模型 ----------


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    raw_text: str = Field(min_length=1)
    adaptation_type: str = "short_drama"
    language: str = "zh-CN"


class GenerateRequest(BaseModel):
    adaptation_type: str | None = None
    language: str | None = None


class AgentRunRequest(BaseModel):
    instruction: str = Field(min_length=1)
    base_version_id: str | None = None
    scene_ids: list[str] = Field(default_factory=list)


class AcceptRequest(BaseModel):
    patch_indexes: list[int] | None = None


class ResumeRequest(BaseModel):
    """人类在中断处的结构化决策。action 见 state.HumanDecision。"""

    action: str = "accept"  # accept | edit | regenerate | reject
    patch_indexes: list[int] | None = None
    patch: list[dict] | None = None  # edit 时人工修订的操作清单
    feedback: str | None = None      # regenerate 时给模型的反馈


# ---------- 序列化辅助 ----------


def _script_to_dict(script: Script) -> dict[str, Any]:
    data = script.model_dump(exclude_none=True)
    data["validation"] = [i.model_dump() for i in validate_script(script)]
    return data


def _project_dict(project: Any) -> dict[str, Any]:
    latest = store().latest_version(project)
    runs = store().list_agent_runs(project.id)
    return {
        "id": project.id,
        "title": project.title,
        "adaptation_type": project.adaptation_type,
        "language": project.language,
        "status": project.status,
        "current_version_id": project.current_version_id,
        "created_at": project.created_at.isoformat(),
        "version_count": len(store().list_versions(project.id)),
        "run_count": len(runs),
        "latest_run": runs[0] and {"status": runs[0].status, "updated_at": runs[0].updated_at.isoformat()},
    }


def _version_dict(version: Any, *, with_content: bool = False) -> dict[str, Any]:
    data = {
        "id": version.id,
        "project_id": version.project_id,
        "parent_version_id": version.parent_version_id,
        "source_type": version.source_type,
        "label": version.label,
        "notes": version.notes,
        "created_at": version.created_at.isoformat(),
    }
    if with_content:
        data["script"] = _script_to_dict(version.script)
        data["validation"] = [i.model_dump() for i in validate_script(version.script)]
    return data


# ---------- 项目 ----------


@router.post("/projects")
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    cfg: Settings = settings()
    p = store().create_project(
        title=payload.title,
        adaptation_type=payload.adaptation_type,
        language=payload.language,
        raw_text=payload.raw_text,
    )
    # 可选 RAG：把原始文本分块写入向量库（Milvus 或内存）。
    if cfg.enable_rag:
        try:
            indexed = index_project(
                vector(), embedder(), project_id=p.id, raw_text=p.raw_text, title=p.title
            )
        except Exception:  # noqa: BLE001
            indexed = 0
    else:
        indexed = 0
    return {"id": p.id, "indexed_chunks": indexed}


@router.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    return [_project_dict(p) for p in store().list_projects()]


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    p = store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return _project_dict(p)


@router.post("/projects/{project_id}/generate")
def generate(project_id: str, payload: GenerateRequest) -> dict[str, Any]:
    p = store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    adaptation_type = payload.adaptation_type or p.adaptation_type
    language = payload.language or p.language
    script, artifacts = generate_script(
        llm(), settings(), title=p.title, raw_text=p.raw_text, adaptation_type=adaptation_type, language=language
    )
    version = store().create_version(
        p,
        script,
        source_type="generation",
        label="初始生成",
        notes=f"生成模式：{artifacts.get('mode', 'n/a')}",
        parent_version_id=p.current_version_id,
        set_current=True,
    )
    return {"version_id": version.id, "mode": artifacts.get("mode"), "validation": [i.model_dump() for i in validate_script(script)]}


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str) -> list[dict[str, Any]]:
    p = store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return [_version_dict(v) for v in store().list_versions(project_id)]


@router.get("/versions/{version_id}")
def get_version(version_id: str) -> dict[str, Any]:
    v = store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    return _version_dict(v, with_content=True)


# ---------- Agent 运行 ----------


@router.post("/projects/{project_id}/agent/run")
def start_run(project_id: str, payload: AgentRunRequest) -> dict[str, Any]:
    p = store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    base_version = None
    if payload.base_version_id:
        base_version = store().get_version(payload.base_version_id)
        if not base_version:
            raise HTTPException(404, "基础版本不存在")
    if base_version is None:
        base_version = store().latest_version(p)
    if base_version is None:
        raise HTTPException(400, "请先生成剧本版本")

    result = agent_svc.start_agent_run(
        store(), llm(), settings(),
        project=p,
        base_version=base_version,
        instruction=payload.instruction,
        scene_ids=payload.scene_ids,
        vector=vector(),
        embedder=embedder(),
    )
    return result


@router.get("/agent/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    run = agent_svc.get_run(store(), run_id)
    if not run:
        raise HTTPException(404, "运行记录不存在")
    return run


@router.post("/agent/runs/{run_id}/resume")
def resume_run(run_id: str, payload: ResumeRequest) -> dict[str, Any]:
    """在中断处提交人类决策：接受 / 编辑 / 重新生成 / 拒绝。"""
    return agent_svc.resume_agent_run(
        store(), llm(), settings(),
        run_id=run_id,
        action=payload.action,
        patch_indexes=payload.patch_indexes,
        patch=payload.patch,
        feedback=payload.feedback,
        vector=vector(),
        embedder=embedder(),
    )


@router.post("/agent/runs/{run_id}/accept")
def accept_run(run_id: str, payload: AcceptRequest) -> dict[str, Any]:
    return agent_svc.resume_agent_run(
        store(), llm(), settings(),
        run_id=run_id,
        action="accept",
        patch_indexes=payload.patch_indexes,
        vector=vector(),
        embedder=embedder(),
    )


@router.post("/agent/runs/{run_id}/reject")
def reject_run(run_id: str) -> dict[str, Any]:
    return agent_svc.resume_agent_run(
        store(), llm(), settings(),
        run_id=run_id,
        action="reject",
        patch_indexes=None,
        vector=vector(),
        embedder=embedder(),
    )


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
