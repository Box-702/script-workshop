# =====================================================================
# store.py —— 业务数据持久化（SQLAlchemy + Postgres，可回退 SQLite）
#
# 保存三类对象：
#   Project       剧本项目（标题、类型、语言、原始文本、指向当前版本）
#   ScriptVersion 剧本快照（内容为 JSON，支持父子版本链）
#   AgentRun      Agent 运行记录（计划、patch、状态、审阅决定）
#
# 这个「应用层存储」与 LangGraph 的 checkpointer 是两层不同的东西：
#   - 本文件：保存「业务数据」——项目 / 版本 / Agent 运行记录本身（默认 Postgres）；
#   - checkpointer：保存「图执行到哪一步」的状态，用于中断后恢复（见 graph.py）。
# 两者配合才能实现「页面刷新后审阅建议还在、接受后生成新版本」。
#
# 驱动选择：通过 DATABASE_URL 前缀自动判断。
#   - postgresql+psycopg://...  -> Postgres（生产 / Docker 默认）
#   - sqlite:///...             -> SQLite（本地开发 / 自动测试，无需外部服务）
# 这保证了在没起 Postgres 的机器上也能单测核心逻辑。
# =====================================================================

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import ForeignKey, create_engine, desc
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .domain import Script


def gen_id(prefix: str) -> str:
    """生成带前缀的短 id（如 ``run_xxx``）。"""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_sqlite_dir(database_url: str) -> None:
    """SQLite 文件库需要父目录存在，否则建表会失败。"""
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return
    path_text = database_url[len(prefix) :]
    if not path_text or path_text == ":memory:":
        return
    Path(path_text).parent.mkdir(parents=True, exist_ok=True)


class Base(DeclarativeBase):
    """ORM 基类。"""


class Project(Base):
    """剧本项目。"""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(primary_key=True)
    title: Mapped[str]
    adaptation_type: Mapped[str] = mapped_column(default="short_drama")
    language: Mapped[str] = mapped_column(default="zh-CN")
    raw_text: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="ready")
    current_version_id: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    versions: Mapped[list["ScriptVersion"]] = relationship(back_populates="project")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="project")


class ScriptVersion(Base):
    """剧本快照。内容以 JSON 存储，可追溯版本链。"""

    __tablename__ = "script_versions"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_version_id: Mapped[str | None] = mapped_column(default=None)
    source_type: Mapped[str] = mapped_column(default="generation")  # generation|agent_adaptation|import
    label: Mapped[str | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(default=None)
    content_json: Mapped[str] = mapped_column(default="{}")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    project: Mapped[Project] = relationship(back_populates="versions")

    @property
    def content(self) -> dict[str, Any]:
        """解析后的剧本字典。"""
        return json.loads(self.content_json or "{}")

    @property
    def script(self) -> Script:
        """通过领域模型访问剧本。"""
        return Script.model_validate(self.content)


class AgentRun(Base):
    """一次 Agent 改编运行记录。"""

    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    base_version_id: Mapped[str]
    result_version_id: Mapped[str | None] = mapped_column(default=None)
    user_prompt: Mapped[str] = mapped_column(default="")
    scene_ids_json: Mapped[str] = mapped_column(default="[]")
    plan_json: Mapped[str] = mapped_column(default="[]")
    patch_json: Mapped[str] = mapped_column(default="[]")
    steps_json: Mapped[str] = mapped_column(default="[]")
    status: Mapped[str] = mapped_column(default="pending")  # pending|reviewing|accepted|rejected|applied
    decision_json: Mapped[str] = mapped_column(default="null")
    model: Mapped[str | None] = mapped_column(default=None)
    error_message: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    project: Mapped[Project] = relationship(back_populates="agent_runs")

    # ---- 便捷存取序列化字段 ----
    @property
    def scene_ids(self) -> list[str]:
        return json.loads(self.scene_ids_json or "[]")

    @property
    def plan(self) -> list[str]:
        return json.loads(self.plan_json or "[]")

    @property
    def patch(self) -> list[dict[str, Any]]:
        return json.loads(self.patch_json or "[]")

    @property
    def steps(self) -> list[str]:
        return json.loads(self.steps_json or "[]")

    @property
    def decision(self) -> dict[str, Any] | None:
        return json.loads(self.decision_json) if self.decision_json else None


# ---------- 会话 / 初始化 ----------


class Store:
    """封装 SQLAlchemy 会话的访问对象。"""

    def __init__(self, database_url: str) -> None:
        # 判断驱动：SQLite 需要单线程检查关闭，且父目录要存在；
        # Postgres（psycopg）则需要连接超时等参数。
        is_sqlite = database_url.startswith("sqlite")
        connect_args: dict[str, Any] = {"check_same_thread": False} if is_sqlite else {}
        if is_sqlite:
            _ensure_sqlite_dir(database_url)
        # pool_pre_ping：连接前探活，避免数据库重启后拿到失效连接。
        self.engine = create_engine(
            database_url,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)

    def session(self):
        return self.session_factory()

    # ---- Project ----
    def create_project(self, *, title: str, adaptation_type: str, language: str, raw_text: str) -> Project:
        with self.session() as s:
            p = Project(
                id=gen_id("proj"),
                title=title,
                adaptation_type=adaptation_type,
                language=language,
                raw_text=raw_text,
            )
            s.add(p)
            s.commit()
            s.refresh(p)
            return p

    def get_project(self, project_id: str) -> Project | None:
        with self.session() as s:
            return s.get(Project, project_id)

    def list_projects(self) -> list[Project]:
        with self.session() as s:
            return s.query(Project).order_by(desc(Project.created_at)).all()

    # ---- ScriptVersion ----
    def create_version(
        self,
        project: Project,
        script: Script,
        *,
        source_type: str,
        label: str | None = None,
        notes: str | None = None,
        parent_version_id: str | None = None,
        set_current: bool = True,
    ) -> ScriptVersion:
        with self.session() as s:
            v = ScriptVersion(
                id=gen_id("ver"),
                project_id=project.id,
                parent_version_id=parent_version_id,
                source_type=source_type,
                label=label,
                notes=notes,
                content_json=script.model_dump_json(exclude_none=True),
            )
            s.add(v)
            if set_current:
                db_project = s.query(Project).filter_by(id=project.id).first()
                if db_project:
                    db_project.current_version_id = v.id
                    db_project.updated_at = _now()
            s.commit()
            s.refresh(v)
            return v

    def get_version(self, version_id: str) -> ScriptVersion | None:
        with self.session() as s:
            return s.get(ScriptVersion, version_id)

    def list_versions(self, project_id: str) -> list[ScriptVersion]:
        with self.session() as s:
            return (
                s.query(ScriptVersion)
                .filter_by(project_id=project_id)
                .order_by(desc(ScriptVersion.created_at))
                .all()
            )

    def latest_version(self, project: Project) -> ScriptVersion | None:
        """取项目当前版本；没有则取最近一条版本。"""
        with self.session() as s:
            if project.current_version_id:
                v = s.get(ScriptVersion, project.current_version_id)
                if v:
                    return v
            return (
                s.query(ScriptVersion)
                .filter_by(project_id=project.id)
                .order_by(desc(ScriptVersion.created_at))
                .first()
            )

    # ---- AgentRun ----
    def create_agent_run(
        self,
        *,
        run_id: str | None = None,
        project_id: str,
        base_version_id: str,
        user_prompt: str,
        scene_ids: list[str],
        plan: list[str] | None = None,
        patch: list[dict[str, Any]] | None = None,
        steps: list[str] | None = None,
        status: str = "pending",
        decision: dict[str, Any] | None = None,
        model: str | None = None,
        error_message: str | None = None,
    ) -> AgentRun:
        with self.session() as s:
            r = AgentRun(
                id=run_id or gen_id("run"),
                project_id=project_id,
                base_version_id=base_version_id,
                user_prompt=user_prompt,
                scene_ids_json=json.dumps(scene_ids),
                plan_json=json.dumps(plan or []),
                patch_json=json.dumps(patch or []),
                steps_json=json.dumps(steps or []),
                status=status,
                decision_json=json.dumps(decision) if decision is not None else "null",
                model=model,
                error_message=error_message,
            )
            s.add(r)
            s.commit()
            s.refresh(r)
            return r

    def get_agent_run(self, run_id: str) -> AgentRun | None:
        with self.session() as s:
            return s.get(AgentRun, run_id)

    def update_agent_run(self, run_id: str, **fields: Any) -> AgentRun | None:
        with self.session() as s:
            r = s.get(AgentRun, run_id)
            if not r:
                return None
            for key, value in fields.items():
                if not hasattr(r, key):
                    continue
                if key in {"scene_ids", "plan", "patch", "steps"}:
                    setattr(r, f"{key}_json", json.dumps(value))
                elif key == "decision":
                    setattr(r, "decision_json", json.dumps(value) if value is not None else "null")
                else:
                    setattr(r, key, value)
            s.commit()
            s.refresh(r)
            return r

    def list_agent_runs(self, project_id: str) -> list[AgentRun]:
        with self.session() as s:
            return (
                s.query(AgentRun)
                .filter_by(project_id=project_id)
                .order_by(desc(AgentRun.created_at))
                .all()
            )
