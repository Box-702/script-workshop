"""Project + run management endpoints."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime  # noqa: F401  (kept for future timestamps)
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import db as dbm
from ..chunking import split_chapters
from ..pipeline import PipelineCallbacks, run_pipeline, to_yaml_text
from ..schemas import (
    ChapterOut,
    GenerateAccepted,
    ProjectCreate,
    ProjectCreateResponse,
    RunOut,
)

router = APIRouter(prefix="/api", tags=["projects"])
log = logging.getLogger(__name__)


def get_db():
    s = dbm.SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _gen_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


@router.post("/projects", response_model=ProjectCreateResponse)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Any:
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
        id=_gen_id("proj"),
        title=payload.title,
        adaptation_type=payload.adaptation_type,
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
    project_id: str, background: BackgroundTasks, db: Session = Depends(get_db)
) -> Any:
    project = db.get(dbm.Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    if not project.chapters:
        raise HTTPException(400, "project has no chapters")

    run = dbm.GenerationRun(
        id=_gen_id("run"),
        project_id=project.id,
        status="queued",
        current_step="queued",
        progress=0,
    )
    db.add(run)
    project.status = "generating"
    db.commit()
    background.add_task(_run_pipeline_task, run.id)
    return GenerateAccepted(run_id=run.id, status="queued")


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: str, db: Session = Depends(get_db)) -> Any:
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


@router.get("/projects/{project_id}/script.yaml")
def get_yaml(project_id: str, db: Session = Depends(get_db)) -> Any:
    project = db.get(dbm.Project, project_id)
    if not project:
        raise HTTPException(404, "project not found")
    latest = (
        db.query(dbm.ScriptVersion)
        .filter_by(project_id=project_id)
        .order_by(dbm.ScriptVersion.created_at.desc())
        .first()
    )
    if not latest:
        raise HTTPException(404, "no script version yet")
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(latest.yaml_content, media_type="text/yaml")


# ---------- background ----------


def _run_pipeline_task(run_id: str) -> None:
    """Background task: execute the 8-stage pipeline, persist outputs.

    Runs in a threadpool thread; uses sync OpenAI SDK. We persist progress
    at coarse step boundaries — fine-grained progress is delivered by the
    final state once the pipeline completes.
    """
    from ..db import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(dbm.GenerationRun, run_id)
        if not run:
            return
        run.status = "running"
        db.commit()

        project = db.get(dbm.Project, run.project_id)
        if not project:
            run.status = "failed"
            run.error_message = "project gone"
            db.commit()
            return

        chapters = sorted(project.chapters, key=lambda c: c.order_index)
        from ..chunking import ChapterSplit

        cb = PipelineCallbacks()

        def _persist_step() -> None:
            run.current_step = cb.current_step
            run.progress = cb.progress
            db.commit()

        try:
            doc, artifacts = run_pipeline(
                [ChapterSplit(c.id, c.title, c.content) for c in chapters],
                title=project.title,
                adaptation_type=project.adaptation_type,
                on_progress=cb,
            )
            _persist_step()  # final progress before assembly
            yaml_text = to_yaml_text(doc)
            version = dbm.ScriptVersion(
                id=_gen_id("ver"),
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
        except Exception as e:  # noqa: BLE001
            log.exception("pipeline failed for run %s", run_id)
            run.status = "failed"
            run.error_message = str(e)
            db.commit()
    finally:
        db.close()
