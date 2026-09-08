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
import re
from datetime import datetime, UTC
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from . import agent as agent_svc
from . import chat as chat_svc
from .deps import llm, settings, store, subagent_runner
from .domain import Script, normalize_adaptation_type
from .export import EXPORT_FORMATS, export_script, script_to_screenplay
from .generation import generate_script
from .importer import parse_file
from .knowledge import detect_genres, extract_author_style
from .patch import validate_script
from .workspace import SUBDIRS, configure_root, current_workspace, pick_directory


def _now() -> datetime:
    return datetime.now(UTC)

router = APIRouter(prefix="/api")


# ---------- 公共辅助 ----------


def _get_project(project_id: str):
    """获取项目, 不存在则 404。"""
    p = store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


def _content_disposition(filename: str, *, inline: bool = False) -> dict[str, str]:
    """构造 RFC 5987 Content-Disposition 头 (中文文件名兼容)。"""
    ascii_name = re.sub(r"[^\x20-\x7e]", "_", filename) or filename
    encoded = quote(filename)
    disp = "inline" if inline else "attachment"
    return {"Content-Disposition": f'{disp}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'}


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
        "milestone": getattr(version, "milestone", None),
        "created_at": version.created_at.isoformat(),
    }
    if with_content:
        script_dict = _script_to_dict(version.script)
        data["script"] = script_dict
        data["validation"] = script_dict.get("validation", [])
    return data


# ---------- 工作目录写入（失败不阻断主流程）----------


def _workspace() -> Any:
    """取当前工作目录实例（未配置/仅应用内时，写文件会静默跳过）。"""
    return current_workspace(settings().effective_workspace_root, settings().workspace_persist)


def _proj_title(raw_title: str) -> str:
    """把任意标题清洗成适合做文件名的安全文本。"""
    text = str(raw_title or "").strip() or "未命名剧本"
    text = re.sub(r'[<>:"\\|?*]', "_", text)
    return text[:80] or "未命名剧本"


def _persist_original(project: Any) -> None:
    """把项目原著写入工作目录的「01_原稿」。"""
    ws = _workspace()
    if not ws.configured:
        return
    try:
        ws.save_original(project.title, _proj_title(project.title) + ".txt", project.raw_text)
    except Exception:  # noqa: BLE001
        pass  # 落盘失败不影响主流程


def _persist_version(project: Any, version: Any, *, label: str | None = None) -> None:
    """把一份剧本版本写入工作目录的「02_版本」。"""
    ws = _workspace()
    if not ws.configured:
        return
    try:
        text = script_to_screenplay(version.script)
        name = f"{_proj_title(project.title)}_v{(version.label or label or '').strip() or 'version'}"
        ws.save_version(project.title, name, text)
    except Exception:  # noqa: BLE001
        pass


# ---------- 项目 ----------


@router.post("/projects")
def create_project(payload: ProjectCreate) -> dict[str, Any]:
    p = store().create_project(
        title=payload.title,
        adaptation_type=payload.adaptation_type,
        language=payload.language,
        raw_text=payload.raw_text,
    )
    _persist_original(p)
    # 提取作者风格存入项目 notes
    try:
        style = extract_author_style(payload.raw_text, llm=llm(), language=payload.language)
        store().set_project_notes(p.id, f"作者风格：{style.get('summary', '')}")
    except Exception:
        pass
    genres = detect_genres(payload.raw_text, top=2)
    return {"id": p.id, "genres": genres}


@router.get("/projects")
def list_projects() -> list[dict[str, Any]]:
    return store().list_project_summaries()


@router.get("/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    p = _get_project(project_id)
    return _project_dict(p)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str) -> dict[str, Any]:
    """删除项目及其所有对话、消息、版本，并清理磁盘上的工作目录文件夹。"""
    p = _get_project(project_id)
    title = p.title
    # 磁盘目录以 title 为键：若有同名项目共存，删掉其中一个不能 rmtree 共享目录。
    has_same_title = any(
        other.title == title and other.id != project_id for other in store().list_projects()
    )
    store().delete_project(project_id)
    ws = _workspace()
    if ws.configured and not has_same_title:
        try:
            ws.remove_project(title)
        except Exception:  # noqa: BLE001
            pass
    return {"ok": True, "deleted": project_id}


@router.post("/projects/{project_id}/generate")
def generate(project_id: str, payload: GenerateRequest) -> dict[str, Any]:
    p = _get_project(project_id)
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
    _persist_version(p, version)
    warnings = []
    if artifacts.get("mode") == "local-fallback":
        warnings.append("未配置可用模型，本次生成的是本地演示剧本；配置 OPENAI/DEEPSEEK key 可生成真实剧本。")
    return {
        "version_id": version.id,
        "mode": artifacts.get("mode"),
        "validation": [i.model_dump() for i in validate_script(script)],
        "warnings": warnings,
    }


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str) -> list[dict[str, Any]]:
    _get_project(project_id)
    return [_version_dict(v) for v in store().list_versions(project_id)]


@router.get("/versions/{version_id}")
def get_version(version_id: str) -> dict[str, Any]:
    v = store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    return _version_dict(v, with_content=True)


class MilestoneSet(BaseModel):
    milestone: str | None = None  # draft | candidate | final | None(清除)


@router.post("/versions/{version_id}/milestone")
def set_milestone(version_id: str, payload: MilestoneSet) -> dict[str, Any]:
    """给版本打里程碑标记（草稿/候选/终稿）。用于「定稿」管理。"""
    allowed = {None, "draft", "candidate", "final"}
    if payload.milestone not in allowed:
        raise HTTPException(400, "milestone 需为 draft/candidate/final 或 null")
    v = store().set_version_milestone(version_id, payload.milestone)
    if not v:
        raise HTTPException(404, "版本不存在")
    return {"ok": True, "version_id": version_id, "milestone": v.milestone}


class ApplyEdit(BaseModel):
    """built-in 剧本编辑器的改动：一组字段级操作（set/add/remove，见 patch.PatchOp）。"""
    ops: list[dict] = Field(default_factory=list)


@router.post("/versions/{version_id}/apply")
def apply_edit(version_id: str, payload: ApplyEdit) -> dict[str, Any]:
    """把编辑器产生的字段级改动应用到一个版本上，生成新版本（source_type=manual_edit）。"""
    from .patch import PatchOp, apply_patch, validate_script

    v = store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    project = store().get_project(v.project_id)
    if not project:
        raise HTTPException(404, "项目不存在")
    try:
        ops = [PatchOp.model_validate(op) for op in payload.ops]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"改动格式错误：{e}") from e
    if not ops:
        raise HTTPException(400, "没有可应用的改动")
    try:
        new_script = apply_patch(v.script, ops)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"应用改动失败：{e}") from e
    issues = validate_script(new_script)
    errors = [i for i in issues if i.severity == "error"]
    if errors:
        raise HTTPException(400, f"改动校验失败：{errors[0].message}")
    nv = store().create_version(
        project,
        new_script,
        source_type="manual_edit",
        label="手动编辑",
        notes=f"基于 {version_id} 手动编辑（{len(ops)} 项改动）",
        parent_version_id=version_id,
        set_current=True,
        milestone="draft",
    )
    _persist_version(project, nv)
    return {"version_id": nv.id, "validation": [i.model_dump() for i in issues]}


# ---------- Agent 运行 ----------


@router.post("/projects/{project_id}/agent/run")
def start_run(project_id: str, payload: AgentRunRequest) -> dict[str, Any]:
    p = _get_project(project_id)
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
    )


@router.post("/agent/runs/{run_id}/accept")
def accept_run(run_id: str, payload: AcceptRequest) -> dict[str, Any]:
    return agent_svc.resume_agent_run(
        store(), llm(), settings(),
        run_id=run_id,
        action="accept",
        patch_indexes=payload.patch_indexes,
    )


@router.post("/agent/runs/{run_id}/reject")
def reject_run(run_id: str) -> dict[str, Any]:
    return agent_svc.resume_agent_run(
        store(), llm(), settings(),
        run_id=run_id,
        action="reject",
        patch_indexes=None,
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
        # 归属校验：防止把 A 项目的消息写进 B 项目的对话线程，造成上下文串扰。
        if project_id and conv.project_id and conv.project_id != project_id:
            raise HTTPException(400, "对话不属于该项目")
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
        store(), llm(), settings(),
        conversation_id=conversation_id,
        project_id=payload.project_id,
        message=payload.message,
        meta=payload.meta,
        runner=subagent_runner(),
    )


@router.post("/chat/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    """对话式 Agent 的 SSE 流式对话（工具轨迹 + 正文增量 + done）。"""
    conversation_id = _resolve_conversation(payload.project_id, payload.conversation_id)
    gen = chat_svc.chat_stream(
        store(), llm(), settings(),
        conversation_id=conversation_id,
        project_id=payload.project_id,
        message=payload.message,
        meta=payload.meta,
        runner=subagent_runner(),
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
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat(),
    }


@router.get("/projects/{project_id}/conversations")
def list_conversations(project_id: str) -> list[dict[str, Any]]:
    """列出某项目下的全部对话（每个对话独立控制上下文）。"""
    _get_project(project_id)
    st = store()
    convs = st.list_conversations(project_id)
    result = []
    for c in convs:
        d = _conversation_dict(c)
        d["user_message_count"] = st.count_user_messages(c.id)
        result.append(d)
    return result


@router.post("/projects/{project_id}/conversations")
def create_conversation(project_id: str, payload: ConversationCreate) -> dict[str, Any]:
    """在项目下新建一个对话。"""
    _get_project(project_id)
    conv = store().create_conversation(project_id, title=payload.title)
    return _conversation_dict(conv)


@router.get("/conversations")
def list_global_conversations() -> list[dict[str, Any]]:
    """列出全局对话（不属于任何项目）。"""
    st = store()
    convs = st.list_global_conversations()
    result = []
    for c in convs:
        d = _conversation_dict(c)
        d["user_message_count"] = st.count_user_messages(c.id)
        result.append(d)
    return result


@router.post("/conversations")
def create_global_conversation(payload: ConversationCreate) -> dict[str, Any]:
    """新建全局对话（不绑定项目）。"""
    conv = store().create_conversation(project_id=None, title=payload.title)
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
    file: UploadFile | None = File(default=None),  # noqa: B008
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
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(400, "文件太大（上限 10MB）")
        try:
            # 解析（zip/XML）是 CPU 阻塞操作，放线程池避免卡住事件循环。
            text = await run_in_threadpool(parse_file, file.filename, data)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        except Exception as e:  # noqa: BLE001  损坏 docx / 非法 XML 等
            raise HTTPException(400, f"文件解析失败：{e}") from e
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
    _persist_original(p)
    # 提取作者风格存入项目 notes
    try:
        style = await run_in_threadpool(
            extract_author_style, text, llm=llm(), language=language,
        )
        store().set_project_notes(p.id, f"作者风格：{style.get('summary', '')}")
    except Exception:
        pass
    conv = store().ensure_default_conversation(p.id)
    genres = detect_genres(text, top=2)
    return {
        "id": p.id,
        "title": p.title,
        "adaptation_type": p.adaptation_type,
        "conversation_id": conv.id,
        "raw_len": len(text),
        "genres": genres,
        "source_file": source_file,
        "warnings": [],
    }


# ---------- 版本文本查看（Codex 式「打开文件看内容」）----------


@router.get("/versions/{version_id}/text")
def version_text(version_id: str) -> dict[str, Any]:
    """返回某版本的可读剧本文本（文本查看模式）。"""
    v = store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    return {
        "version_id": version_id,
        "title": v.script.title,
        "text": script_to_screenplay(v.script),
    }


@router.get("/versions/{version_id}/export")
def export_version(version_id: str, fmt: str = "txt") -> Response:
    """导出某版本文本为 .txt / .md / .docx 文件，并同步写入工作目录的「03_导出」。"""
    v = store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    fmt = (fmt or "txt").lower()
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(400, f"不支持的导出格式：{fmt}，可选：{'/'.join(EXPORT_FORMATS)}")
    try:
        data, ext = export_script(v.script, fmt)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    base = f"{_proj_title(v.script.title)}_v{version_id}"
    filename = f"{base}{ext}"
    headers = _content_disposition(filename)
    media_type = EXPORT_FORMATS[fmt]["mime"]

    # 同步写入工作目录（03_导出）——失败不影响下载本身。
    ws = _workspace()
    if ws.configured:
        try:
            ws.save_export(v.script.title, base, data, ext)
        except Exception:  # noqa: BLE001
            pass

    return Response(content=data, media_type=media_type, headers=headers)


# ---------- 工作目录（真实关联磁盘文件夹）----------


class WorkspaceSet(BaseModel):
    root: str = Field(default="", min_length=0)
    persist: bool = Field(default=True)  # False = 仅应用内、不落盘文件


@router.get("/workspace")
def get_workspace() -> dict[str, Any]:
    """返回当前工作目录配置（含根路径、落盘模式与目录结构说明）。"""
    ws = _workspace()
    info = ws.info(settings().effective_workspace_root)
    # 已配置时附带一份结构说明文字。
    info["structure"] = (
        "\n".join(f"{code}/  <-  {label}" for code, label in SUBDIRS)
        if ws.configured
        else None
    )
    return info


@router.get("/workspace/select")
def select_workspace_directory() -> dict[str, Any]:
    """弹出系统原生文件夹选择对话框（Windows），选择即设为工作目录。

    注意：这是**阻塞式**调用——服务端会弹出一个原生「选择文件夹」窗口，等用户
    选完返回。取消时返回 cancelled=True，不改变工作目录。
    """
    ws = _workspace()
    initial = str(ws.root) if ws.root else None
    try:
        path = pick_directory(initial)
    except RuntimeError as e:
        raise HTTPException(400, str(e)) from e
    if not path:
        return {"cancelled": True, "path": None}
    # 选择文件夹即切到「落盘」模式。
    ws = configure_root(path, persist=True)
    return {"cancelled": False, "path": path, **ws.info(settings().effective_workspace_root)}


@router.post("/workspace")
def set_workspace(payload: WorkspaceSet) -> dict[str, Any]:
    """设置 / 更新工作目录。persist=False 表示「仅应用内」模式（不写磁盘，数据库照常存）。"""
    root = (payload.root or "").strip()
    try:
        ws = configure_root(root, payload.persist)
        if ws.persist:
            ws.ensure_root()
            ws.write_readme()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"无法创建工作目录：{e}") from e
    return {"ok": True, **ws.info(settings().effective_workspace_root)}


@router.post("/projects/{project_id}/structure")
def project_structure(project_id: str) -> dict[str, Any]:
    """把某项目的原稿与最新版本落盘到工作目录，返回目录树文本。"""
    p = _get_project(project_id)
    ws = _workspace()
    if not ws.persist:
        raise HTTPException(400, "当前为「仅应用内」模式，不写入磁盘；可切换到落盘模式后重试")
    if not ws.root:
        raise HTTPException(400, "工作目录未配置，请先设置工作目录")
    _persist_original(p)
    latest = store().latest_version(p)
    if latest:
        _persist_version(p, latest)
    return {"project_id": project_id, "structure": ws.tree_text(p.title), "root": ws.info()["root"]}


@router.get("/projects/{project_id}/knowledge")
def list_project_knowledge(project_id: str) -> dict[str, Any]:
    """列出项目的知识（题材知识 + 用户记忆），用于调试与展示。"""
    p = _get_project(project_id)
    # 题材知识
    genres = detect_genres(p.raw_text, top=2)
    from .knowledge import get_all_genre_knowledge
    genre_knowledge = get_all_genre_knowledge(genres)
    docs = []
    for kind, items in genre_knowledge.items():
        for item in items:
            docs.append({"kind": kind, "source": f"genre:{'、'.join(genres)}", "text": item})
    # 用户记忆
    from .memory import recall_memories
    memories = recall_memories(store(), project_id=project_id, limit=20)
    for m in memories:
        docs.append({"kind": m["kind"], "source": m["source"], "text": m["content"]})
    return {
        "project_id": project_id,
        "total": len(docs),
        "docs": docs,
    }


# ---------- 本地剧本文件（查看 / 下载）----------


def _file_mime(ext: str) -> str:
    ext = (ext or "").lower()
    if ext in {".txt", ".md", ".markdown"}:
        return "text/plain; charset=utf-8"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if ext == ".pdf":
        return "application/pdf"
    return "application/octet-stream"


@router.get("/projects/{project_id}/files")
def list_project_files(project_id: str) -> dict[str, Any]:
    """列出某项目在磁盘上的剧本文件（按 01_原稿/02_版本/03_导出/04_知识库 分组）。"""
    p = _get_project(project_id)
    ws = _workspace()
    if not ws.persist:
        return {"project_id": project_id, "persist": False, "configured": False, "root": None, "folders": []}
    data = ws.list_project_files(p.title)
    return {
        "project_id": project_id,
        "persist": True,
        "configured": True,
        "root": (data or {}).get("root"),
        "folders": (data or {}).get("folders", []),
    }


@router.get("/projects/{project_id}/files/{relpath:path}")
def get_project_file(project_id: str, relpath: str) -> FileResponse:
    """读取/预览某项目下的一个剧本文件（文本内联预览，其它附件下载）。"""
    p = _get_project(project_id)
    ws = _workspace()
    if not ws.persist:
        raise HTTPException(400, "当前为「仅应用内」模式，未落盘文件")
    path = ws.resolve_file(p.title, relpath)
    if not path:
        raise HTTPException(404, "文件不存在")
    ext = path.suffix.lower()
    inline = ext in {".txt", ".md", ".markdown"}
    headers = _content_disposition(path.name, inline=inline)
    return FileResponse(path, media_type=_file_mime(ext), headers=headers)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# ---------- 子代理任务 ----------


@router.get("/tasks")
def list_tasks(active_only: bool = False) -> list[dict[str, Any]]:
    """列出子代理任务（默认全部，active_only=true 只返回运行中的）。"""
    return [t.to_dict() for t in subagent_runner().list_tasks(active_only=active_only)]


@router.get("/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, Any]:
    """查询单个子代理任务详情。"""
    task = subagent_runner().get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task.to_dict()


# ---------- 编剧圣经 / 设定备忘 ----------


class NotesSet(BaseModel):
    notes: str = Field(default="")


@router.get("/projects/{project_id}/notes")
def get_notes(project_id: str) -> dict[str, Any]:
    _get_project(project_id)
    return {"project_id": project_id, "notes": store().get_project_notes(project_id)}


@router.put("/projects/{project_id}/notes")
def set_notes(project_id: str, payload: NotesSet) -> dict[str, Any]:
    p = _get_project(project_id)
    store().set_project_notes(project_id, payload.notes)
    # 同步到工作目录的「04_知识库」——失败不影响主流程。
    ws = _workspace()
    if ws.configured:
        try:
            ws.save_note(p.title, "编剧圣经_设定.md", payload.notes)
        except Exception:  # noqa: BLE001
            pass
    return {"project_id": project_id, "ok": True}


@router.get("/status")
def status() -> dict[str, Any]:
    """返回当前运行配置摘要（供前端展示「模型 / 存储」状态）。"""
    cfg = settings()
    llm_ = llm()
    return {
        "model": {
            "available": llm_.available,
            "provider": getattr(llm_, "provider_label", "local-fallback"),
            "name": cfg.openai_model if cfg.openai_api_key else (cfg.deepseek_model if cfg.deepseek_api_key else "-"),
        },
        "memory": {
            "backend": "database",
            "enabled": True,
        },
        "storage": {
            "database": cfg.database_url.split("://")[0],
            "checkpointer": cfg.checkpointer,
        },
        "workspace": {
            "persist": cfg.workspace_persist,
            "root": cfg.effective_workspace_root,
        },
        "mode": "full" if llm_.available else "demo",
        "langsmith": bool(cfg.langsmith_tracing and cfg.langsmith_api_key),
    }


# =====================================================================
# v3.0 视频制作相关 API
# =====================================================================


# ---------- 请求模型 ----------


class ProviderCreate(BaseModel):
    kind: str = "video"
    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    base_url: str = ""
    api_key: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class ProviderUpdate(BaseModel):
    label: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class ModelPreferenceSet(BaseModel):
    task_type: str = Field(min_length=1)
    provider_id: str | None = None
    model_name: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    is_default: bool = True


class VideoVersionCreate(BaseModel):
    shots: list[dict[str, Any]]
    style_guide: dict[str, Any] = Field(default_factory=dict)
    source_type: str = "manual"
    label: str | None = None
    notes: str | None = None
    parent_version_id: str | None = None


class VideoJobCreate(BaseModel):
    shot_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    version_id: str | None = None


# ---------- Provider 管理 ----------


@router.post("/providers")
def create_provider(payload: ProviderCreate) -> dict[str, Any]:
    """添加一个新的 API Provider。"""
    p = store().create_api_provider(
        kind=payload.kind,
        name=payload.name,
        label=payload.label,
        base_url=payload.base_url,
        api_key=payload.api_key,
        config=payload.config,
        enabled=payload.enabled,
    )
    return {"id": p.id, "name": p.name, "label": p.label, "kind": p.kind}


@router.get("/providers")
def list_providers(kind: str | None = None) -> list[dict[str, Any]]:
    """列出所有 API Providers。"""
    rows = store().list_api_providers(kind=kind)
    return [
        {
            "id": r.id,
            "kind": r.kind,
            "name": r.name,
            "label": r.label,
            "base_url": r.base_url,
            "configured": bool(r.api_key),
            "enabled": r.enabled,
            "config": r.config,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/providers/{provider_id}")
def get_provider(provider_id: str) -> dict[str, Any]:
    """获取 Provider 详情。"""
    p = store().get_api_provider(provider_id)
    if not p:
        raise HTTPException(404, "Provider 不存在")
    return {
        "id": p.id,
        "kind": p.kind,
        "name": p.name,
        "label": p.label,
        "base_url": p.base_url,
        "configured": bool(p.api_key),
        "enabled": p.enabled,
        "config": p.config,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


@router.patch("/providers/{provider_id}")
def update_provider(provider_id: str, payload: ProviderUpdate) -> dict[str, Any]:
    """更新 Provider 配置。"""
    fields = {k: v for k, v in payload.model_dump().items() if v is not None}
    p = store().update_api_provider(provider_id, **fields)
    if not p:
        raise HTTPException(404, "Provider 不存在")
    return {"id": p.id, "ok": True}


@router.delete("/providers/{provider_id}")
def delete_provider(provider_id: str) -> dict[str, Any]:
    """删除 Provider。"""
    if not store().delete_api_provider(provider_id):
        raise HTTPException(404, "Provider 不存在")
    return {"ok": True}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str) -> dict[str, Any]:
    """测试 Provider 连接（尝试列出可用模型或发一个空请求）。"""
    p = store().get_api_provider(provider_id)
    if not p:
        raise HTTPException(404, "Provider 不存在")
    if p.kind == "video":
        from .video import get_registry
        registry = get_registry()
        provider = registry.get_provider(p.name, api_key=p.api_key, base_url=p.base_url)
        if not provider:
            return {"ok": False, "error": f"未找到视频 Provider: {p.name}"}
        return {"ok": bool(p.api_key), "provider": p.name, "label": provider.label}
    # LLM provider 测试
    if not p.api_key:
        return {"ok": False, "error": "未配置 API Key"}
    return {"ok": True, "provider": p.name, "label": p.label}


# ---------- 模型偏好 ----------


@router.get("/models/preferences")
def list_preferences() -> list[dict[str, Any]]:
    """列出所有模型偏好设置。"""
    prefs = store().list_model_preferences()
    return [
        {
            "id": p.id,
            "task_type": p.task_type,
            "provider_id": p.provider_id,
            "model_name": p.model_name,
            "params": p.params,
            "is_default": p.is_default,
        }
        for p in prefs
    ]


@router.put("/models/preferences")
def set_preference(payload: ModelPreferenceSet) -> dict[str, Any]:
    """设置模型偏好。"""
    pref = store().set_model_preference(
        task_type=payload.task_type,
        provider_id=payload.provider_id,
        model_name=payload.model_name,
        params=payload.params,
        is_default=payload.is_default,
    )
    return {"id": pref.id, "task_type": pref.task_type, "ok": True}


@router.get("/models/available")
def available_models() -> dict[str, Any]:
    """列出所有可用的模型（按 provider 分组）。"""
    providers = store().list_api_providers()
    llm_providers = []
    video_providers = []
    for p in providers:
        info = {
            "id": p.id,
            "name": p.name,
            "label": p.label,
            "configured": bool(p.api_key),
            "enabled": p.enabled,
        }
        if p.kind == "llm":
            llm_providers.append(info)
        elif p.kind == "video":
            video_providers.append(info)
    return {
        "llm": llm_providers,
        "video": video_providers,
    }


# ---------- 视频版本 ----------


@router.post("/projects/{project_id}/video-versions")
def create_video_version(project_id: str, payload: VideoVersionCreate) -> dict[str, Any]:
    """创建视频版本快照。"""
    _get_project(project_id)
    v = store().create_video_version(
        project_id=project_id,
        shots=payload.shots,
        style_guide=payload.style_guide,
        source_type=payload.source_type,
        label=payload.label,
        notes=payload.notes,
        parent_version_id=payload.parent_version_id,
    )
    return {"id": v.id, "project_id": project_id, "created_at": v.created_at.isoformat()}


@router.get("/projects/{project_id}/video-versions")
def list_video_versions(project_id: str) -> list[dict[str, Any]]:
    """列出项目的所有视频版本。"""
    _get_project(project_id)
    versions = store().list_video_versions(project_id)
    return [
        {
            "id": v.id,
            "parent_version_id": v.parent_version_id,
            "source_type": v.source_type,
            "label": v.label,
            "notes": v.notes,
            "milestone": v.milestone,
            "shot_count": len(v.shots),
            "created_at": v.created_at.isoformat(),
        }
        for v in versions
    ]


@router.get("/video-versions/{version_id}")
def get_video_version(version_id: str) -> dict[str, Any]:
    """获取视频版本详情（含完整镜头数据）。"""
    v = store().get_video_version(version_id)
    if not v:
        raise HTTPException(404, "视频版本不存在")
    return {
        "id": v.id,
        "project_id": v.project_id,
        "parent_version_id": v.parent_version_id,
        "source_type": v.source_type,
        "label": v.label,
        "notes": v.notes,
        "milestone": v.milestone,
        "shots": v.shots,
        "style_guide": v.style_guide,
        "created_at": v.created_at.isoformat(),
    }


@router.post("/video-versions/{version_id}/milestone")
def set_video_milestone(version_id: str, milestone: str | None = None) -> dict[str, Any]:
    """设置视频版本里程碑。"""
    v = store().set_video_version_milestone(version_id, milestone)
    if not v:
        raise HTTPException(404, "视频版本不存在")
    return {"id": v.id, "milestone": v.milestone}


# ---------- 视频生成任务 ----------


@router.post("/projects/{project_id}/video/generate")
def create_video_job(project_id: str, payload: VideoJobCreate) -> dict[str, Any]:
    """提交视频生成任务。"""
    _get_project(project_id)
    # 估算费用
    from .video import get_registry
    registry = get_registry()
    provider = registry.get_provider(payload.provider)
    cost = provider.estimate_cost(5.0) if provider else None

    job = store().create_video_job(
        project_id=project_id,
        shot_id=payload.shot_id,
        provider=payload.provider,
        model=payload.model,
        prompt=payload.prompt,
        params=payload.params,
        version_id=payload.version_id,
        cost_estimate=cost,
    )
    return {
        "id": job.id,
        "status": job.status,
        "provider": job.provider,
        "model": job.model,
        "cost_estimate": job.cost_estimate,
    }


@router.get("/projects/{project_id}/video/jobs")
def list_video_jobs(project_id: str) -> list[dict[str, Any]]:
    """列出项目的所有视频生成任务。"""
    _get_project(project_id)
    jobs = store().list_video_jobs(project_id)
    return [
        {
            "id": j.id,
            "shot_id": j.shot_id,
            "provider": j.provider,
            "model": j.model,
            "prompt": j.prompt,
            "status": j.status,
            "video_url": j.video_url,
            "error_message": j.error_message,
            "cost_estimate": j.cost_estimate,
            "created_at": j.created_at.isoformat(),
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
        for j in jobs
    ]


@router.get("/video/jobs/{job_id}")
def get_video_job(job_id: str) -> dict[str, Any]:
    """查询视频生成任务状态。"""
    j = store().get_video_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    return {
        "id": j.id,
        "project_id": j.project_id,
        "shot_id": j.shot_id,
        "provider": j.provider,
        "model": j.model,
        "prompt": j.prompt,
        "status": j.status,
        "video_url": j.video_url,
        "error_message": j.error_message,
        "cost_estimate": j.cost_estimate,
        "created_at": j.created_at.isoformat(),
        "finished_at": j.finished_at.isoformat() if j.finished_at else None,
    }


@router.post("/video/jobs/{job_id}/cancel")
def cancel_video_job(job_id: str) -> dict[str, Any]:
    """取消视频生成任务。"""
    j = store().get_video_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    store().update_video_job(job_id, status="cancelled", finished_at=_now())
    return {"id": job_id, "status": "cancelled"}


@router.post("/video/jobs/{job_id}/retry")
def retry_video_job(job_id: str) -> dict[str, Any]:
    """重试失败的视频生成任务。"""
    j = store().get_video_job(job_id)
    if not j:
        raise HTTPException(404, "任务不存在")
    if j.status not in ("failed", "cancelled"):
        raise HTTPException(400, f"任务状态为 {j.status}，只能重试失败或已取消的任务")
    store().update_video_job(job_id, status="pending", error_message=None, video_url=None, finished_at=None)
    return {"id": job_id, "status": "pending"}
