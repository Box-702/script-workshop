"""Project + run management endpoints."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

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
    RunOut,
)
from .deps import DbSession

router = APIRouter(prefix="/api", tags=["projects"])
log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMRunOptions:
    provider: str = "openai"
    openai_api_key: str = ""
    openai_base_url: str = ""
    openai_model: str = ""
    language: str = ""


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
    return OpenAIProvider(
        get_settings(),
        api_key=api_key,
        base_url=options.openai_base_url or None,
        model=options.openai_model or None,
        language=options.language or None,
    )


@router.post("/projects", response_model=ProjectCreateResponse)
def create_project(payload: ProjectCreate, db: DbSession) -> Any:
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


@router.post("/projects/{project_id}/generate", response_model=GenerateAccepted)
def generate(
    project_id: str,
    background: BackgroundTasks,
    db: DbSession,
    llm_provider: Annotated[str | None, Header(alias="X-LLM-Provider")] = None,
    openai_api_key: Annotated[str | None, Header(alias="X-OpenAI-API-Key")] = None,
    openai_base_url: Annotated[str | None, Header(alias="X-OpenAI-Base-URL")] = None,
    openai_model: Annotated[str | None, Header(alias="X-OpenAI-Model")] = None,
) -> Any:
    project = db.get(dbm.Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if not project.chapters:
        raise HTTPException(400, "project has no chapters")

    options = LLMRunOptions(
        provider=llm_provider or "openai",
        openai_api_key=openai_api_key or "",
        openai_base_url=openai_base_url or "",
        openai_model=openai_model or "",
        language=project.language or "",
    )
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
def get_run(run_id: str, db: DbSession) -> Any:
    run = db.get(dbm.GenerationRun, run_id)
    if not run:
        raise HTTPException(404, "run not found")
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
                yaml_content=yaml_text,
                json_content=doc.model_dump(exclude_none=True),
                validation_status="valid" if not artifacts.get("validation_errors") else "invalid",
                validation_errors=artifacts.get("validation_errors"),
            )
            db.add(version)
            project.status = "ready"
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
            run.error_message = str(e)
            db.commit()
            log_event(
                run_id,
                "lifecycle",
                "run_failed",
                error=f"{type(e).__name__}: {e}",
            )
    finally:
        db.close()
