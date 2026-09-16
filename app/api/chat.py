# =====================================================================
# chat.py —— 对话式 Agent 与会话管理
#
# 一轮对话（非流式 / SSE 流式）、历史消息，以及「一个项目下多个独立
# 对话 / 全局对话」的增删改查。编排逻辑在 app/chat/conductor.py。
# =====================================================================

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from ..chat import conductor as chat_svc
from . import common, deps
from .schemas import ChatRequest, ConversationCreate, ConversationRename

router = APIRouter()


def _conversation_dict(conv: Any) -> dict[str, Any]:
    return {
        "id": conv.id,
        "project_id": conv.project_id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


def _resolve_conversation(project_id: str | None, conversation_id: str | None) -> str | None:
    """解析会话线程：显式 conversation_id 优先；否则用项目的默认对话；都没有则全局。"""
    if conversation_id:
        conv = deps.store().get_conversation(conversation_id)
        if not conv:
            raise HTTPException(404, "对话不存在")
        # 归属校验：防止把 A 项目的消息写进 B 项目的对话线程，造成上下文串扰。
        if project_id and conv.project_id and conv.project_id != project_id:
            raise HTTPException(400, "对话不属于该项目")
        return conv.id
    if project_id:
        p = deps.store().get_project(project_id)
        if not p:
            raise HTTPException(404, "项目不存在")
        return deps.store().ensure_default_conversation(project_id).id
    return None


# ---------- 对话 ----------


@router.post("/chat")
def chat(payload: ChatRequest) -> dict[str, Any]:
    """对话式 Agent 的一轮非流式对话。"""
    conversation_id = _resolve_conversation(payload.project_id, payload.conversation_id)
    return chat_svc.chat_once(
        deps.store(), deps.llm(), deps.settings(),
        conversation_id=conversation_id,
        project_id=payload.project_id,
        message=payload.message,
        meta=payload.meta,
        runner=deps.subagent_runner(),
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """对话式 Agent 的 SSE 流式对话（工具轨迹 + 正文增量 + done）。"""
    conversation_id = _resolve_conversation(payload.project_id, payload.conversation_id)
    gen = chat_svc.chat_stream(
        deps.store(), deps.llm(), deps.settings(),
        conversation_id=conversation_id,
        project_id=payload.project_id,
        message=payload.message,
        meta=payload.meta,
        runner=deps.subagent_runner(),
    )

    # chat_stream 是同步生成器（内部含阻塞的 LLM / DB 调用），
    # 必须放到线程池里逐条推进，否则会把整个事件循环卡住，拖死所有并发请求。
    _STREAM_DONE = object()

    async def event_source():
        it = iter(gen)
        while True:
            event = await run_in_threadpool(next, it, _STREAM_DONE)
            if event is _STREAM_DONE:
                break
            yield common.sse_frame(event["event"], event["data"])

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/history")
def chat_history(
    project_id: str | None = None, conversation_id: str | None = None
) -> list[dict[str, Any]]:
    """读取某条会话线程的历史消息（优先 conversation_id，否则项目默认对话）。"""
    thread = _resolve_conversation(project_id, conversation_id)
    return chat_svc.load_history(deps.store(), thread)


# ---------- 对话（Conversation）管理：一个项目下多个独立对话 ----------


@router.get("/projects/{project_id}/conversations")
def list_conversations(project_id: str) -> list[dict[str, Any]]:
    """列出某项目下的全部对话（每个对话独立控制上下文）。"""
    common.get_project(project_id)
    st = deps.store()
    result = []
    for c in st.list_conversations(project_id):
        d = _conversation_dict(c)
        d["user_message_count"] = st.count_user_messages(c.id)
        result.append(d)
    return result


@router.post("/projects/{project_id}/conversations")
def create_conversation(project_id: str, payload: ConversationCreate) -> dict[str, Any]:
    """在项目下新建一个对话。"""
    common.get_project(project_id)
    conv = deps.store().create_conversation(project_id, title=payload.title)
    return _conversation_dict(conv)


@router.get("/conversations")
def list_global_conversations() -> list[dict[str, Any]]:
    """列出全局对话（不属于任何项目）。"""
    st = deps.store()
    result = []
    for c in st.list_global_conversations():
        d = _conversation_dict(c)
        d["user_message_count"] = st.count_user_messages(c.id)
        result.append(d)
    return result


@router.post("/conversations")
def create_global_conversation(payload: ConversationCreate) -> dict[str, Any]:
    """新建全局对话（不绑定项目）。"""
    conv = deps.store().create_conversation(project_id=None, title=payload.title)
    return _conversation_dict(conv)


@router.patch("/conversations/{conversation_id}")
def rename_conversation(conversation_id: str, payload: ConversationRename) -> dict[str, Any]:
    conv = deps.store().rename_conversation(conversation_id, payload.title)
    if not conv:
        raise HTTPException(404, "对话不存在")
    return _conversation_dict(conv)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str) -> dict[str, Any]:
    if not deps.store().delete_conversation(conversation_id):
        raise HTTPException(404, "对话不存在")
    return {"deleted": conversation_id}


@router.get("/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str) -> list[dict[str, Any]]:
    """读取某个对话的全部消息（按时间正序）。"""
    conv = deps.store().get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "对话不存在")
    return chat_svc.load_history(deps.store(), conv.id)
