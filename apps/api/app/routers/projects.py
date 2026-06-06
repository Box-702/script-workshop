"""Project + run management endpoints."""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException
from sqlalchemy.orm import Session

from .. import db as dbm
from ..chunking import split_chapters
from ..config import get_settings
from ..ids import gen_id
from ..langdetect import detect_language
from ..pipeline import PipelineCallbacks, run_pipeline, to_yaml_text
from ..providers.base import LLMProvider
from ..providers.openai_provider import OpenAIProvider
from ..runlog import log_event
from ..schemas import (
    ChapterOut,
    GenerateAccepted,
    ProjectCreate,
    ProjectCreateResponse,
    ProjectDetail,
    ProjectOut,
    ProjectRunSummary,
    ProjectScriptImportRequest,
    ProjectScriptImportResponse,
    RunOut,
    ScriptVersionOut,
)
from ..services.model_keys import (
    decrypt_model_key,
    get_active_model_key,
    is_plausible_api_key,
)
from ..services.versions import create_version_from_yaml, latest_version, parse_version_yaml
from ..yaml_io import to_yaml
from .deps import CurrentUser, DbSession

router = APIRouter(prefix="/api", tags=["projects"])
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMRunOptions:
    provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = ""
    language: str = ""


def _version_out(version: dbm.ScriptVersion | None) -> ScriptVersionOut | None:
    if version is None:
        return None
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


def _run_summary(run: dbm.GenerationRun | None) -> ProjectRunSummary | None:
    if run is None:
        return None
    return ProjectRunSummary(
        id=run.id,
        status=run.status,
        current_step=run.current_step,
        progress=run.progress,
        created_at=run.created_at.isoformat(),
    )


def _latest_version(db: Session, project_id: str) -> dbm.ScriptVersion | None:
    return latest_version(db, project_id)


def _latest_run(db: Session, project_id: str) -> dbm.GenerationRun | None:
    return (
        db.query(dbm.GenerationRun)
        .filter_by(project_id=project_id)
        .order_by(dbm.GenerationRun.created_at.desc())
        .first()
    )


def get_project_for_user_or_404(
    db: Session, project_id: str, user_id: str
) -> dbm.Project:
    project = db.get(dbm.Project, project_id)
    if not project or project.owner_id != user_id:
        raise HTTPException(404, "project not found")
    return project


def _project_out(db: Session, project: dbm.Project) -> ProjectOut:
    return ProjectOut(
        id=project.id,
        owner_id=project.owner_id,
        title=project.title,
        adaptation_type=project.adaptation_type,
        language=project.language,
        status=project.status,
        current_version_id=project.current_version_id,
        created_at=project.created_at.isoformat(),
        updated_at=project.updated_at.isoformat(),
        chapter_count=len(project.chapters),
        version_count=len(project.versions),
        latest_version=_version_out(_latest_version(db, project.id)),
        latest_run=_run_summary(_latest_run(db, project.id)),
    )


def _project_detail(db: Session, project: dbm.Project) -> ProjectDetail:
    base = _project_out(db, project)
    chapters = [
        ChapterOut(
            id=chapter.id,
            title=chapter.title,
            word_count=len(chapter.content),
            order_index=chapter.order_index,
        )
        for chapter in sorted(project.chapters, key=lambda item: item.order_index)
    ]
    return ProjectDetail(**base.model_dump(), chapters=chapters)


def _provider_from_options(options: LLMRunOptions) -> LLMProvider:
    """Build the LLM provider. Only OpenAI is supported; missing key raises immediately."""
    provider = (options.provider or "openai").lower().strip()
    if provider != "openai":
        raise HTTPException(
            status_code=400,
            detail=(
                f"unsupported LLM provider: {provider!r}. "
                "Only 'openai' is supported."
            ),
        )
    api_key = options.openai_api_key or get_settings().openai_api_key
    if not (api_key or "").strip():
        raise HTTPException(
            status_code=400,
            detail=(
                "OpenAI API key is missing. Configure it on /settings or set "
                "OPENAI_API_KEY in the server environment."
            ),
        )
    if not is_plausible_api_key(api_key):
        raise HTTPException(
            status_code=400,
            detail=(
                "API key 看起来不是有效密钥。请在模型设置中粘贴完整 key，"
                "不要使用 ****1234 这类遮罩值、端口号或空值。"
            ),
        )
    return OpenAIProvider(
        get_settings(),
        api_key=api_key,
        base_url=options.openai_base_url or None,
        model=options.openai_model or None,
        language=options.language or None,
    )


def _fill_options_from_saved_key(
    db: Session, options: LLMRunOptions, *, user_id: str = "local_user"
) -> LLMRunOptions:
    if options.openai_api_key.strip():
        return options
    key = get_active_model_key(db, user_id=user_id, provider=options.provider)
    if key is None:
        return options
    decrypted = decrypt_model_key(key)
    return LLMRunOptions(
        provider=decrypted.provider,
        openai_api_key=decrypted.api_key,
        openai_base_url=options.openai_base_url or decrypted.base_url,
        openai_model=options.openai_model or decrypted.model,
        language=options.language,
    )


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: DbSession, current_user: CurrentUser) -> list[ProjectOut]:
    projects = (
        db.query(dbm.Project)
        .filter_by(owner_id=current_user.id)
        .order_by(dbm.Project.updated_at.desc())
        .all()
    )
    return [_project_out(db, project) for project in projects]


@router.post("/projects", response_model=ProjectCreateResponse)
def create_project(
    payload: ProjectCreate, db: DbSession, current_user: CurrentUser
) -> Any:
    try:
        chapters = split_chapters(payload.raw_text, min_chapters=3)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if len(chapters) < 3:
        raise HTTPException(
            status_code=400,
            detail=f"need at least 3 chapters, got {len(chapters)}",
        )

    project = dbm.Project(
        id=gen_id("proj"),
        owner_id=current_user.id,
        title=payload.title,
        adaptation_type=payload.adaptation_type,
        language=payload.language or detect_language(payload.raw_text),
        status="created",
    )
    db.add(project)
    for idx, ch in enumerate(chapters):
        db.add(
            dbm.Chapter(
                id=ch.chapter_id,
                project_id=project.id,
                title=ch.title,
                content=ch.content,
                order_index=idx,
            )
        )
    db.commit()
    return ProjectCreateResponse(
        project_id=project.id,
        chapter_count=len(chapters),
        chapters=[
            ChapterOut(
                id=ch.id,
                title=ch.title,
                word_count=len(ch.content),
                order_index=ch.order_index,
            )
            for ch in project.chapters
        ],
    )


@router.post("/projects/import-script", response_model=ProjectScriptImportResponse)
def import_script_project(
    payload: ProjectScriptImportRequest,
    db: DbSession,
    current_user: CurrentUser,
) -> ProjectScriptImportResponse:
    yaml_content = _import_payload_to_yaml(payload)
    data, errors = parse_version_yaml(yaml_content)
    script = data.get("script") if isinstance(data, dict) else {}
    if not isinstance(script, dict):
        raise HTTPException(400, "script source must contain a script object")

    project = dbm.Project(
        id=gen_id("proj"),
        owner_id=current_user.id,
        title=(payload.title or script.get("title") or "导入剧本").strip(),
        adaptation_type=_script_adaptation_type(script),
        language=str(script.get("language") or "zh-CN"),
        status="created",
    )
    db.add(project)
    for idx, chapter_id in enumerate(_script_chapter_ids(script)):
        db.add(
            dbm.Chapter(
                id=chapter_id,
                project_id=project.id,
                title=f"导入来源 {idx + 1}",
                content="该项目由剧本源码导入，未包含小说原文。",
                order_index=idx,
            )
        )
    db.commit()
    db.refresh(project)

    version = create_version_from_yaml(
        db,
        project,
        yaml_content,
        source_type="import",
        label=payload.label or "导入剧本源码",
        notes="用户从剧本源码导入项目。",
        edit_type="import",
    )
    return ProjectScriptImportResponse(
        project_id=project.id,
        version_id=version.id,
        validation_status=version.validation_status,
        validation_errors=errors,
    )


def _import_payload_to_yaml(payload: ProjectScriptImportRequest) -> str:
    if payload.format == "yaml":
        return payload.content
    try:
        data = json.loads(payload.content)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"JSON parse error: {e}") from e
    if not isinstance(data, dict):
        raise HTTPException(400, "JSON root must be an object")
    if "script" not in data:
        data = {"script": data}
    return to_yaml(data)


def _script_adaptation_type(script: dict[str, Any]) -> str:
    adaptation = script.get("adaptation")
    if isinstance(adaptation, dict):
        value = str(adaptation.get("type") or "").strip()
        if value:
            return value
    return "other"


def _script_chapter_ids(script: dict[str, Any]) -> list[str]:
    source = script.get("source")
    if isinstance(source, dict):
        raw_ids = source.get("chapter_ids")
        if isinstance(raw_ids, list):
            ids = [str(item).strip() for item in raw_ids if str(item).strip()]
            if ids:
                return list(dict.fromkeys(ids))
    return ["chapter_001", "chapter_002", "chapter_003"]


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: str, db: DbSession, current_user: CurrentUser
) -> ProjectDetail:
    project = get_project_for_user_or_404(db, project_id, current_user.id)
    return _project_detail(db, project)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: str, db: DbSession, current_user: CurrentUser) -> None:
    project = get_project_for_user_or_404(db, project_id, current_user.id)
    db.delete(project)
    db.commit()


@router.post("/projects/{project_id}/generate", response_model=GenerateAccepted)
def generate(
    project_id: str,
    background: BackgroundTasks,
    db: DbSession,
    current_user: CurrentUser,
    llm_provider: Annotated[str | None, Header(alias="X-LLM-Provider")] = None,
    openai_api_key: Annotated[str | None, Header(alias="X-OpenAI-API-Key")] = None,
    openai_base_url: Annotated[str | None, Header(alias="X-OpenAI-Base-URL")] = None,
    openai_model: Annotated[str | None, Header(alias="X-OpenAI-Model")] = None,
) -> Any:
    project = get_project_for_user_or_404(db, project_id, current_user.id)
    if not project.chapters:
        raise HTTPException(400, "project has no chapters")

    options = LLMRunOptions(
        provider=llm_provider or "openai",
        openai_api_key=openai_api_key or "",
        openai_base_url=openai_base_url or "",
        openai_model=openai_model or "",
        language=project.language or "",
    )
    options = _fill_options_from_saved_key(db, options, user_id=current_user.id)
    # Fail fast with a clean HTTP error so the UI can show it. Background task
    # will only run after we've already proved the provider can be built.
    _provider_from_options(options)

    # Idempotency: if the project already has an in-flight run, return that
    # run_id instead of creating a duplicate. Cancellable later via a future
    # DELETE endpoint.
    existing = (
        db.query(dbm.GenerationRun)
        .filter(
            dbm.GenerationRun.project_id == project.id,
            dbm.GenerationRun.status.in_(("queued", "running")),
        )
        .order_by(dbm.GenerationRun.created_at.desc())
        .first()
    )
    if existing is not None:
        return GenerateAccepted(run_id=existing.id, status=existing.status)  # type: ignore[arg-type]

    run = dbm.GenerationRun(
        id=gen_id("run"),
        project_id=project.id,
        status="queued",
        current_step="queued",
        progress=0,
    )
    db.add(run)
    project.status = "generating"
    db.commit()
    background.add_task(_run_pipeline_task, run.id, options)
    return GenerateAccepted(run_id=run.id, status="queued")


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: DbSession, current_user: CurrentUser) -> Any:
    run = db.get(dbm.GenerationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
    get_project_for_user_or_404(db, run.project_id, current_user.id)
    return RunOut(
        id=run.id,
        project_id=run.project_id,
        status=run.status,
        current_step=run.current_step,
        progress=run.progress,
        error_message=run.error_message,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


# ---------- background ----------


def _run_pipeline_task(run_id: str, llm_options: LLMRunOptions) -> None:
    """Background task: execute the 8-stage pipeline, persist outputs."""
    from ..db import SessionLocal

    log_event(run_id, "lifecycle", "background_task_started")
    db = SessionLocal()
    try:
        run = db.get(dbm.GenerationRun, run_id)
        if not run:
            return
        run.status = "running"
        db.commit()
        log_event(run_id, "lifecycle", "run_marked_running", project_id=run.project_id)

        project = db.get(dbm.Project, run.project_id)
        if not project:
            run.status = "failed"
            run.error_message = "project gone"
            db.commit()
            return

        chapters = sorted(project.chapters, key=lambda c: c.order_index)
        from ..chunking import ChapterSplit

        class PersistingCallbacks(PipelineCallbacks):
            def update(self, step: str, progress: int) -> None:
                super().update(step, progress)
                run.current_step = step
                run.progress = progress
                db.commit()

        cb = PersistingCallbacks()

        try:
            doc, artifacts = run_pipeline(
                [ChapterSplit(c.id, c.title, c.content) for c in chapters],
                title=project.title,
                adaptation_type=project.adaptation_type,
                on_progress=cb,
                provider=_provider_from_options(llm_options),
                language=project.language or "zh-CN",
                run_id=run.id,
            )
            yaml_text = to_yaml_text(doc)
            version = dbm.ScriptVersion(
                id=gen_id("ver"),
                project_id=project.id,
                parent_version_id=project.current_version_id,
                source_type="generation",
                label="AI generated draft",
                notes=None,
                yaml_content=yaml_text,
                json_content=doc.model_dump(exclude_none=True),
                validation_status="valid" if not artifacts.get("validation_errors") else "invalid",
                validation_errors=artifacts.get("validation_errors"),
            )
            db.add(version)
            project.status = "ready"
            project.current_version_id = version.id
            run.status = "done"
            run.current_step = "done"
            run.progress = 100
            run.artifacts = artifacts
            db.commit()
            log_event(
                run_id,
                "lifecycle",
                "run_done",
                scene_count=len(doc.script.scenes),
                char_count=len(doc.script.characters),
                validation_errors=len(artifacts.get("validation_errors", [])),
            )
        except Exception as e:  # noqa: BLE001
            log.exception("pipeline failed for run %s", run_id)
            run.status = "failed"
            run.error_message = _friendly_generation_error(e)
            project.status = "failed"
            db.commit()
            log_event(
                run_id,
                "lifecycle",
                "run_failed",
                error=f"{type(e).__name__}: {e}",
            )
    finally:
        db.close()


def _friendly_generation_error(error: Exception) -> str:
    raw = str(error)
    lowered = raw.lower()
    status_code = getattr(error, "status_code", None)
    if status_code == 401 or "authentication" in lowered or "invalid api key" in lowered:
        return (
            "模型认证失败：API key 无效、已过期或没有访问权限。"
            "请到“模型设置”更新完整 key，并确认 base URL 与模型名称匹配。"
        )
    if status_code == 429 or "rate limit" in lowered or "quota" in lowered:
        return "模型额度或速率受限：请稍后重试，或更换有额度的 API key。"
    if "connection" in lowered or "timeout" in lowered:
        return "模型服务连接失败：请检查网络、base URL 和服务商状态。"
    if raw:
        return raw
    return f"生成失败：{type(error).__name__}"
