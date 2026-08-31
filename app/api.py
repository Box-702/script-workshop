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

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import agent as agent_svc
from . import chat as chat_svc
from .config import Settings
from .deps import embedder, llm, settings, store, vector
from .domain import Script, normalize_adaptation_type
from .generation import generate_script
from .importer import parse_file
from .knowledge import index_project_knowledge
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


class ChatRequest(BaseModel):
    """对话式 Agent 的一轮输入。"""

    project_id: str | None = None   # 剧本项目；缺省为「新建剧本」的全局会话
    conversation_id: str | None = None  # 项目下的具体对话（线程）；缺省用项目默认对话
    message: str = Field(default="")  # 审阅动作（meta.intent=resume）时可为空
    meta: dict[str, Any] | None = None  # 结构化意图（如 {"intent": "resume", ...}）


class ConversationCreate(BaseModel):
    title: str = Field(default="新对话", min_length=1, max_length=120)


class ConversationRename(BaseModel):
    title: str = Field(min_length=1, max_length=120)


# ---------- 序列化辅助 ----------


def _script_to_dict(script: Script) -> dict[str, Any]:
    data = script.model_dump(exclude_none=True)
    data["validation"] = [i.model_dump() for i in validate_script(script)]
    return data


def _project_dict(project: Any) -> dict[str, Any]:
    latest = store().latest_version(project)
    runs = store().list_agent_runs(project.id)
    latest_run = runs[0] if runs else None
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
        "latest_run": {"status": latest_run.status, "updated_at": latest_run.updated_at.isoformat()}
        if latest_run
        else None,
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


@router.get("/projects/{project_id}/runs")
def list_runs(project_id: str) -> list[dict[str, Any]]:
    """列出某项目的 Agent 运行历史（供前端展示）。"""
    runs = store().list_agent_runs(project_id)
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


# ---------- 对话式 Agent ----------


def _sse_frame(event: str, data: dict[str, Any]) -> str:
    """把事件封装成 SSE 文本帧。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _resolve_conversation(project_id: str | None, conversation_id: str | None) -> str | None:
    """解析会话线程：显式 conversation_id 优先；否则用项目的默认对话；都没有则全局。"""
    if conversation_id:
        conv = store().get_conversation(conversation_id)
        if not conv:
            raise HTTPException(404, "对话不存在")
        return conv.id
    if project_id:
        p = store().get_project(project_id)
        if not p:
            raise HTTPException(404, "项目不存在")
        return store().ensure_default_conversation(project_id).id
    return None


@router.post("/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    """对话式 Agent 的一轮非流式对话。"""
    conversation_id = _resolve_conversation(payload.project_id, payload.conversation_id)
    return chat_svc.chat_once(
        store(), llm(), settings(), vector(), embedder(),
        conversation_id=conversation_id,
        project_id=payload.project_id,
        message=payload.message,
        meta=payload.meta,
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """对话式 Agent 的 SSE 流式对话（工具轨迹 + 正文增量 + done）。"""
    conversation_id = _resolve_conversation(payload.project_id, payload.conversation_id)
    gen = chat_svc.chat_stream(
        store(), llm(), settings(), vector(), embedder(),
        conversation_id=conversation_id,
        project_id=payload.project_id,
        message=payload.message,
        meta=payload.meta,
    )

    async def event_source():
        for event in gen:
            yield _sse_frame(event["event"], event["data"])

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/history")
def chat_history(project_id: str | None = None, conversation_id: str | None = None) -> list[dict[str, Any]]:
    """读取某条会话线程的历史消息（优先 conversation_id，否则项目默认对话）。"""
    thread = _resolve_conversation(project_id, conversation_id)
    return chat_svc.load_history(store(), thread)


# ---------- 对话（Conversation）管理：一个项目下多个独立对话 ----------


def _conversation_dict(conv: Any) -> dict[str, Any]:
    return {
        "id": conv.id,
        "project_id": conv.project_id,
        "title": conv.title,
        "message_count": len(store().list_chat_messages(conv.id)),
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@router.get("/projects/{project_id}/conversations")
def list_conversations(project_id: str) -> list[dict[str, Any]]:
    """列出某项目下的全部对话（每个对话独立控制上下文）。"""
    p = store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return [_conversation_dict(c) for c in store().list_conversations(project_id)]


@router.post("/projects/{project_id}/conversations")
def create_conversation(project_id: str, payload: ConversationCreate) -> dict[str, Any]:
    """在项目下新建一个对话。"""
    p = store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    conv = store().create_conversation(project_id, title=payload.title)
    return _conversation_dict(conv)


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationRename) -> dict[str, Any]:
    conv = store().rename_conversation(conversation_id, payload.title)
    if not conv:
        raise HTTPException(404, "对话不存在")
    return _conversation_dict(conv)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, Any]:
    if not store().delete_conversation(conversation_id):
        raise HTTPException(404, "对话不存在")
    return {"deleted": conversation_id}


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    """读取某个对话的全部消息（按时间正序）。"""
    conv = store().get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "对话不存在")
    return chat_svc.load_history(store(), conv.id)


# ---------- 文件导入：新建剧本 = 上传 .txt / .md / .docx ----------


@router.post("/projects/import")
async def import_project(
    file: UploadFile | None = File(default=None),
    raw_text: str | None = Form(default=None),
    title: str | None = Form(default=None),
    adaptation_type: str = Form(default="short_drama"),
    language: str = Form(default="zh-CN"),
) -> dict[str, Any]:
    """新建剧本：上传原著文件（.txt/.md/.docx）或直接粘贴原文，自动建知识库。"""
    text = ""
    source_file = ""
    if file is not None and file.filename:
        data = await file.read()
        if not data:
            raise HTTPException(400, "文件为空")
        try:
            text = parse_file(file.filename, data)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        source_file = file.filename
    elif raw_text and raw_text.strip():
        text = raw_text
    else:
        raise HTTPException(400, "请上传文件（.txt/.md/.docx）或粘贴原文")
    if len(text.strip()) < 20:
        raise HTTPException(400, "导入的文本内容太短（至少 20 字）")
    name = (title or "").strip() or Path(source_file or "未命名").stem
    p = store().create_project(
        title=name[:120],
        adaptation_type=normalize_adaptation_type(adaptation_type),
        language=language,
        raw_text=text,
    )
    counts = index_project_knowledge(
        vector(), embedder(), project_id=p.id, raw_text=text, title=p.title, llm=llm(), language=language
    )
    conv = store().ensure_default_conversation(p.id)
    return {
        "id": p.id,
        "title": p.title,
        "adaptation_type": p.adaptation_type,
        "conversation_id": conv.id,
        "raw_len": len(text),
        "indexed": counts,
        "source_file": source_file,
    }


# ---------- 版本文本查看（Codex 式「打开文件看内容」）----------


def _script_to_screenplay(script: Script) -> str:
    """把结构化剧本渲染成可读的剧本文本（供文本查看模式展示）。"""
    locs = {l.id: l.name for l in script.locations}
    chars = {c.id: c.name for c in script.characters}
    lines = [
        f"《{script.title}》",
        f"类型：{script.adaptation.type if script.adaptation else '其他'} · 语言：{script.language}",
        f"梗概：{script.logline}",
    ]
    if script.themes:
        lines.append("主题：" + "、".join(script.themes))
    lines.append("")
    for i, sc in enumerate(script.scenes, 1):
        loc = locs.get(sc.location_id, sc.location_id)
        lines.append(f"—— 第 {i} 场 · {sc.title}（{loc}）" + (f" · {sc.time}" if sc.time else ""))
        lines.append(f"目的：{sc.purpose}")
        lines.append(f"冲突：{sc.conflict}")
        lines.append("")
        for b in sc.beats:
            if b.type == "dialogue":
                speaker = chars.get(b.speaker, b.speaker or "")
                emotion = f"（{b.emotion}）" if b.emotion else ""
                lines.append(f"{speaker}{emotion}：{b.line}")
            elif b.type == "cue":
                lines.append(f"〔提示〕{b.text}")
            else:
                lines.append(f"【动作】{b.text}")
        lines.append("")
    return "\n".join(lines).rstrip()


@router.get("/versions/{version_id}/text")
def version_text(version_id: str) -> dict[str, Any]:
    """返回某版本的可读剧本文本（文本查看模式）。"""
    v = store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    return {
        "version_id": version_id,
        "title": v.script.title,
        "text": _script_to_screenplay(v.script),
    }


@router.get("/projects/{project_id}/knowledge")
def list_project_knowledge(project_id: str) -> dict[str, Any]:
    """列出某项目知识库里已索引的文档（原文分块 + 改编知识），用于调试与展示。"""
    p = store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    try:
        rows = vector().list_project(project_id)
    except Exception:  # noqa: BLE001
        rows = []
    docs = [
        {
            "kind": r.get("kind", "source"),
            "source": r.get("source", ""),
            "text": r.get("text", ""),
        }
        for r in rows
    ]
    return {
        "project_id": project_id,
        "total": len(docs),
        "docs": docs,
    }


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/status")
def status() -> dict[str, Any]:
    """返回当前运行配置摘要（供前端展示「模型 / RAG / 存储」状态）。"""
    cfg = settings()
    llm_ = llm()
    emb = embedder()
    vec = vector()
    return {
        "model": {
            "available": llm_.available,
            "provider": getattr(llm_, "provider_label", "local-fallback"),
            "name": cfg.openai_model if cfg.openai_api_key else (cfg.deepseek_model if cfg.deepseek_api_key else "-"),
        },
        "rag": {
            "enabled": cfg.enable_rag,
            "vector_backend": type(vec).__name__,
            "embedder": type(emb).__name__,
            "dim": getattr(emb, "dim", None),
        },
        "storage": {
            "database": cfg.database_url.split("://")[0],
            "checkpointer": cfg.checkpointer,
        },
        "langsmith": bool(cfg.langsmith_tracing and cfg.langsmith_api_key),
    }
