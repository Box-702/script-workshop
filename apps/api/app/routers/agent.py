"""AI Agent adaptation endpoints."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header

from .. import db as dbm
from ..config import get_settings
from ..schemas import (
    AgentAcceptRequest,
    AgentAdaptRequest,
    AgentRunOut,
    ScriptVersionDetail,
    ScriptVersionOut,
)
from ..services.agent import (
    accept_agent_run,
    create_agent_run,
    get_agent_run_or_404,
    reject_agent_run,
    retry_agent_run,
)
from ..services.versions import get_project_or_404
from .deps import DbSession
from .projects import LLMRunOptions, _fill_options_from_saved_key, _provider_from_options

router = APIRouter(prefix="/api", tags=["agent"])


def _version_out(version: dbm.ScriptVersion) -> ScriptVersionOut:
    return ScriptVersionOut(
        id=version.id,
        project_id=version.project_id,
        parent_version_id=version.parent_version_id,
        source_type=version.source_type,
        label=version.label,
        notes=version.notes,
        validation_status=version.validation_status,
        validation_errors=version.validation_errors,
        created_at=version.created_at.isoformat(),
    )


def _version_detail(version: dbm.ScriptVersion) -> ScriptVersionDetail:
    return ScriptVersionDetail(
        **_version_out(version).model_dump(),
        yaml_content=version.yaml_content,
    )


def _agent_run_out(run: dbm.AgentRun) -> AgentRunOut:
    return AgentRunOut(
        id=run.id,
        project_id=run.project_id,
        base_version_id=run.base_version_id,
        result_version_id=run.result_version_id,
        user_prompt=run.user_prompt,
        selected_context=run.selected_context,
        plan=run.plan,
        patch=run.patch,
        status=run.status,
        model=run.model,
        error_message=run.error_message,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


def _agent_provider_from_headers(
    db: DbSession,
    *,
    language: str,
    llm_provider: str | None,
    openai_api_key: str | None,
    openai_base_url: str | None,
    openai_model: str | None,
) -> tuple[object | None, str | None]:
    options = LLMRunOptions(
        provider=llm_provider or "openai",
        openai_api_key=openai_api_key or "",
        openai_base_url=openai_base_url or "",
        openai_model=openai_model or "",
        language=language,
    )
    options = _fill_options_from_saved_key(db, options)
    if options.openai_api_key.strip() or get_settings().openai_api_key.strip():
        try:
            return _provider_from_options(options), None
        except Exception as e:  # noqa: BLE001
            return None, str(e)
    return None, "未配置模型 key，已使用本地改编建议。"


@router.post("/projects/{project_id}/agent/adapt", response_model=AgentRunOut)
def adapt_project(
    project_id: str,
    payload: AgentAdaptRequest,
    db: DbSession,
    llm_provider: Annotated[str | None, Header(alias="X-LLM-Provider")] = None,
    openai_api_key: Annotated[str | None, Header(alias="X-OpenAI-API-Key")] = None,
    openai_base_url: Annotated[str | None, Header(alias="X-OpenAI-Base-URL")] = None,
    openai_model: Annotated[str | None, Header(alias="X-OpenAI-Model")] = None,
) -> AgentRunOut:
    project = get_project_or_404(db, project_id)
    provider, provider_error = _agent_provider_from_headers(
        db,
        language=project.language or "",
        llm_provider=llm_provider,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
        openai_model=openai_model,
    )
    return _agent_run_out(
        create_agent_run(db, project, payload, provider=provider, provider_error=provider_error)
    )


@router.get("/agent-runs/{run_id}", response_model=AgentRunOut)
def get_agent_run(run_id: str, db: DbSession) -> AgentRunOut:
    return _agent_run_out(get_agent_run_or_404(db, run_id))


@router.post("/agent-runs/{run_id}/accept", response_model=ScriptVersionDetail)
def accept_agent_run_endpoint(
    run_id: str, db: DbSession, payload: AgentAcceptRequest | None = None
) -> ScriptVersionDetail:
    version = accept_agent_run(
        db,
        get_agent_run_or_404(db, run_id),
        patch_indexes=payload.patch_indexes if payload else None,
    )
    return _version_detail(version)


@router.post("/agent-runs/{run_id}/reject", response_model=AgentRunOut)
def reject_agent_run_endpoint(run_id: str, db: DbSession) -> AgentRunOut:
    return _agent_run_out(reject_agent_run(db, get_agent_run_or_404(db, run_id)))


@router.post("/agent-runs/{run_id}/retry", response_model=AgentRunOut)
def retry_agent_run_endpoint(
    run_id: str,
    db: DbSession,
    llm_provider: Annotated[str | None, Header(alias="X-LLM-Provider")] = None,
    openai_api_key: Annotated[str | None, Header(alias="X-OpenAI-API-Key")] = None,
    openai_base_url: Annotated[str | None, Header(alias="X-OpenAI-Base-URL")] = None,
    openai_model: Annotated[str | None, Header(alias="X-OpenAI-Model")] = None,
) -> AgentRunOut:
    run = get_agent_run_or_404(db, run_id)
    project = get_project_or_404(db, run.project_id)
    provider, provider_error = _agent_provider_from_headers(
        db,
        language=project.language or "",
        llm_provider=llm_provider,
        openai_api_key=openai_api_key,
        openai_base_url=openai_base_url,
        openai_model=openai_model,
    )
    return _agent_run_out(
        retry_agent_run(db, run, provider=provider, provider_error=provider_error)
    )
