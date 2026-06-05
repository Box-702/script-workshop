from __future__ import annotations

import logging
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import get_settings

log = logging.getLogger(__name__)
API_ROOT = Path(__file__).resolve().parent.parent


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64), default="local_user", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    adaptation_type: Mapped[str] = mapped_column(String(64), default="short_drama")
    language: Mapped[str] = mapped_column(String(16), default="zh-CN")
    status: Mapped[str] = mapped_column(String(32), default="created")
    current_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Chapter.order_index"
    )
    runs: Mapped[list[GenerationRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    versions: Mapped[list[ScriptVersion]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id"), primary_key=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    project: Mapped[Project] = relationship(back_populates="chapters")


class GenerationRun(Base):
    __tablename__ = "generation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")  # queued|running|done|failed
    current_step: Mapped[str] = mapped_column(String(64), default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifacts: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    project: Mapped[Project] = relationship(back_populates="runs")


class UserModelKey(Base):
    __tablename__ = "user_model_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), default="local_user", index=True)
    provider: Mapped[str] = mapped_column(String(64), default="openai")
    base_url: Mapped[str] = mapped_column(String(512), default="")
    default_model: Mapped[str] = mapped_column(String(128), default="")
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    key_last4: Mapped[str] = mapped_column(String(8), default="")
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class ScriptVersion(Base):
    __tablename__ = "script_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    yaml_content: Mapped[str] = mapped_column(Text, nullable=False)
    json_content: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), default="valid")
    validation_errors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    project: Mapped[Project] = relationship(back_populates="versions")


def resolve_database_url(url: str) -> str:
    """Resolve app-relative SQLite URLs against ``apps/api``.

    The dev server is commonly launched from the repository root while
    Alembic is configured from ``apps/api``. Anchoring relative SQLite paths
    here keeps the runtime engine and migrations pointed at the same file.
    Network database URLs are returned unchanged.
    """
    if not url.startswith("sqlite:///"):
        return url

    raw_path = url.replace("sqlite:///", "", 1)
    if raw_path == ":memory:":
        return url
    if raw_path.startswith(("/", "\\")) or (
        len(raw_path) >= 3 and raw_path[1:3] in (":/", ":\\")
    ):
        return url

    abs_path = (API_ROOT / raw_path).resolve()
    return f"sqlite:///{abs_path.as_posix()}"


def make_engine():
    settings = get_settings()
    url = resolve_database_url(settings.database_url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Apply all pending Alembic migrations to the configured database.

    Alembic owns the schema. ``Base.metadata.create_all`` is intentionally
    not called here — it would silently mask missing columns and drift
    between the SQLAlchemy model and the actual SQLite file. For a brand
    new project (no versions table yet), the initial baseline migration
    under ``alembic/versions`` brings the database up to the current model
    schema.

    The function is idempotent w.r.t. the in-process state and safe to call
    repeatedly. ``alembic upgrade head`` is itself a no-op once the schema
    version recorded in ``alembic_version`` matches the latest revision.
    """
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    settings = get_settings()
    database_url = resolve_database_url(settings.database_url)
    # Ensure the sqlite file's parent directory exists so Alembic can open it.
    if database_url.startswith("sqlite:///") and database_url != "sqlite:///:memory:":
        path = database_url.replace("sqlite:///", "", 1)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)

    # Resolve the alembic config relative to this file. ``alembic.ini`` lives
    # at ``apps/api/alembic.ini``; the ``script_location`` in the ini file
    # points at ``alembic/`` next to it.
    api_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(api_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_root / "alembic"))
    # Make Alembic honour the runtime DATABASE_URL instead of the one baked
    # into alembic.ini (which exists for the alembic CLI but should not be
    # the source of truth for the running app).
    cfg.set_main_option("sqlalchemy.url", database_url)

    try:
        command.upgrade(cfg, "head")
    except Exception:
        # Re-raise after logging so the FastAPI startup handler can decide
        # whether to crash the process. We do not try to "self-heal" here
        # because that tends to mask real schema drift.
        log.exception("alembic upgrade head failed")
        raise
