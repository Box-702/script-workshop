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
    notes: Mapped[str] = mapped_column(default="")  # 编剧圣经 / 设定备忘（自由文本）
    status: Mapped[str] = mapped_column(default="ready")
    current_version_id: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    versions: Mapped[list["ScriptVersion"]] = relationship(back_populates="project")
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="project")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="project")


class ScriptVersion(Base):
    """剧本快照。内容以 JSON 存储，可追溯版本链。"""

    __tablename__ = "script_versions"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    parent_version_id: Mapped[str | None] = mapped_column(default=None)
    source_type: Mapped[str] = mapped_column(default="generation")  # generation|agent_adaptation|import|manual_edit
    label: Mapped[str | None] = mapped_column(default=None)
    notes: Mapped[str | None] = mapped_column(default=None)
    milestone: Mapped[str | None] = mapped_column(default=None)  # draft|candidate|final
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


class Conversation(Base):
    """项目下的一个对话（会话线程）。

    一个项目 = 一个剧本文件夹，其下可以新建多个对话；每个对话独立保存
    消息历史，从而独立控制 Agent 的上下文（互不干扰）。
    """

    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(default="新对话")
    created_at: Mapped[datetime] = mapped_column(default=_now)
    updated_at: Mapped[datetime] = mapped_column(default=_now, onupdate=_now)

    project: Mapped[Project] = relationship(back_populates="conversations")


class ChatMessage(Base):
    """对话式 Agent 的消息记录。

    ``thread_id`` 是这条消息所属会话的 id（等于 Conversation.id），
    一个项目下的多个对话彼此隔离；还没有项目的全局对话用 ``global``。
    ``payload`` / ``events`` 保存该条助手消息附带的结构化数据
    （审阅卡片、工具轨迹等），供前端渲染。
    """

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(primary_key=True)
    thread_id: Mapped[str] = mapped_column(index=True)
    role: Mapped[str] = mapped_column(default="user")  # user | assistant
    content: Mapped[str] = mapped_column(default="")
    payload_json: Mapped[str] = mapped_column(default="[]")
    events_json: Mapped[str] = mapped_column(default="[]")
    created_at: Mapped[datetime] = mapped_column(default=_now)

    @property
    def payload(self) -> list[dict[str, Any]]:
        return json.loads(self.payload_json or "[]")

    @property
    def events(self) -> list[dict[str, Any]]:
        return json.loads(self.events_json or "[]")


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
        if is_sqlite:
            # 多线程共享 engine 时（FastAPI 线程池），SQLite 需要 WAL + busy_timeout，
            # 否则并发写极易报 "database is locked"。
            from sqlalchemy import event

            @event.listens_for(self.engine, "connect")
            def _sqlite_pragma(dbapi_conn: Any, _record: Any) -> None:
                cursor = dbapi_conn.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=30000")
                cursor.close()

        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        self._ensure_columns()

    def _ensure_columns(self) -> None:
        """轻量迁移：给已存在的表补缺失列（如 milestone / notes）。

        新库由 create_all 直接建出含新列的表；老库（如已有 dev.db）不会自动加列，
        这里用 ALTER TABLE 补齐，避免启动后查询这些列报错。
        """
        try:
            from sqlalchemy import inspect, text

            insp = inspect(self.engine)
            tables = set(insp.get_table_names())
            cols_proj = {c["name"] for c in insp.get_columns("projects")} if "projects" in tables else set()
            if "notes" not in cols_proj:
                with self.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE projects ADD COLUMN notes VARCHAR"))
            cols_ver = {c["name"] for c in insp.get_columns("script_versions")} if "script_versions" in tables else set()
            if "milestone" not in cols_ver:
                with self.engine.begin() as conn:
                    conn.execute(text("ALTER TABLE script_versions ADD COLUMN milestone VARCHAR"))
        except Exception:  # noqa: BLE001
            # 表不存在或已是最新：迁移失败不阻塞启动。
            pass

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

    def delete_project(self, project_id: str) -> None:
        """删除项目及其所有关联数据（对话、消息、版本、运行记录）。"""
        with self.session() as s:
            # 删除对话消息（ChatMessage.thread_id 存的是 Conversation.id）
            convs = s.query(Conversation).filter_by(project_id=project_id).all()
            for c in convs:
                s.query(ChatMessage).filter_by(thread_id=c.id).delete()
            # 删除对话
            s.query(Conversation).filter_by(project_id=project_id).delete()
            # 删除版本
            s.query(ScriptVersion).filter_by(project_id=project_id).delete()
            # 删除运行记录
            s.query(AgentRun).filter_by(project_id=project_id).delete()
            # 删除项目
            s.query(Project).filter_by(id=project_id).delete()
            s.commit()

    def list_projects(self) -> list[Project]:
        with self.session() as s:
            return s.query(Project).order_by(desc(Project.created_at)).all()

    def get_project_notes(self, project_id: str) -> str:
        p = self.get_project(project_id)
        return p.notes if p else ""

    def set_project_notes(self, project_id: str, notes: str) -> Project | None:
        """保存项目的编剧圣经 / 设定备忘（自由文本）。"""
        with self.session() as s:
            p = s.get(Project, project_id)
            if not p:
                return None
            p.notes = notes
            p.updated_at = _now()
            s.commit()
            s.refresh(p)
            return p

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
        milestone: str | None = None,
    ) -> ScriptVersion:
        with self.session() as s:
            v = ScriptVersion(
                id=gen_id("ver"),
                project_id=project.id,
                parent_version_id=parent_version_id,
                source_type=source_type,
                label=label,
                notes=notes,
                milestone=milestone,
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

    def set_version_milestone(self, version_id: str, milestone: str | None) -> ScriptVersion | None:
        """给某版本打里程碑标记（draft/candidate/final）。传 None 清除。"""
        with self.session() as s:
            v = s.get(ScriptVersion, version_id)
            if not v:
                return None
            v.milestone = milestone
            s.commit()
            s.refresh(v)
            return v

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

    # ---- ChatMessage（对话式 Agent）----

    def save_chat_message(
        self,
        *,
        thread_id: str,
        role: str,
        content: str,
        payload: list[dict[str, Any]] | None = None,
        events: list[dict[str, Any]] | None = None,
    ) -> ChatMessage:
        with self.session() as s:
            m = ChatMessage(
                id=gen_id("msg"),
                thread_id=thread_id,
                role=role,
                content=content,
                payload_json=json.dumps(payload or [], ensure_ascii=False),
                events_json=json.dumps(events or [], ensure_ascii=False),
            )
            s.add(m)
            s.commit()
            s.refresh(m)
            return m

    def list_chat_messages(self, thread_id: str, limit: int = 200) -> list[ChatMessage]:
        with self.session() as s:
            # 取「最新 limit 条」再按时间正序返回：长对话要保留的是最近上下文，
            # 而不是开头几条。
            rows = (
                s.query(ChatMessage)
                .filter_by(thread_id=thread_id)
                .order_by(ChatMessage.created_at.desc())
                .limit(limit)
                .all()
            )
            return list(reversed(rows))

    # ---- Conversation（项目下的对话线程）----

    def create_conversation(self, project_id: str, title: str = "新对话") -> Conversation:
        with self.session() as s:
            c = Conversation(id=gen_id("conv"), project_id=project_id, title=title)
            s.add(c)
            s.commit()
            s.refresh(c)
            return c

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        with self.session() as s:
            return s.get(Conversation, conversation_id)

    def list_conversations(self, project_id: str) -> list[Conversation]:
        with self.session() as s:
            return (
                s.query(Conversation)
                .filter_by(project_id=project_id)
                .order_by(Conversation.updated_at.desc())
                .all()
            )

    def rename_conversation(self, conversation_id: str, title: str) -> Conversation | None:
        with self.session() as s:
            c = s.get(Conversation, conversation_id)
            if not c:
                return None
            c.title = title
            c.updated_at = _now()
            s.commit()
            s.refresh(c)
            return c

    def delete_conversation(self, conversation_id: str) -> bool:
        with self.session() as s:
            c = s.get(Conversation, conversation_id)
            if not c:
                return False
            s.query(ChatMessage).filter_by(thread_id=conversation_id).delete()
            s.delete(c)
            s.commit()
            return True

    def ensure_default_conversation(self, project_id: str) -> Conversation:
        """项目没有对话时自动建一个「默认对话」，保证任何项目都能直接开聊。"""
        convs = self.list_conversations(project_id)
        if convs:
            return convs[0]
        return self.create_conversation(project_id, title="默认对话")
