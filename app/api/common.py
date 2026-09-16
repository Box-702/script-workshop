# =====================================================================
# common.py —— API 层共享辅助
#
# 路由之间复用的序列化、错误处理与「落盘不阻断主流程」的写入逻辑。
# 约定：这些函数只做编排与格式转换，不承载业务规则——业务在
# pipeline / agent / store 里。
# =====================================================================

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from fastapi import HTTPException

from ..domain import Script
from ..pipeline.export import script_to_screenplay
from ..pipeline.patch import validate_script
from ..workspace import current_workspace
from . import deps


def now() -> datetime:
    return datetime.now(UTC)


def get_project(project_id: str) -> Any:
    """获取项目，不存在则 404。"""
    p = deps.store().get_project(project_id)
    if not p:
        raise HTTPException(404, "项目不存在")
    return p


def content_disposition(filename: str, *, inline: bool = False) -> dict[str, str]:
    """构造 RFC 5987 Content-Disposition 头（中文文件名兼容）。"""
    ascii_name = re.sub(r"[^\x20-\x7e]", "_", filename) or filename
    encoded = quote(filename)
    disp = "inline" if inline else "attachment"
    return {"Content-Disposition": f'{disp}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded}'}


def script_to_dict(script: Script) -> dict[str, Any]:
    data = script.model_dump(exclude_none=True)
    data["validation"] = [i.model_dump() for i in validate_script(script)]
    return data


def project_dict(project: Any) -> dict[str, Any]:
    st = deps.store()
    runs = st.list_agent_runs(project.id)
    latest_run = runs[0] if runs else None
    return {
        "id": project.id,
        "title": project.title,
        "adaptation_type": project.adaptation_type,
        "language": project.language,
        "status": project.status,
        "current_version_id": project.current_version_id,
        "created_at": project.created_at.isoformat(),
        "version_count": len(st.list_versions(project.id)),
        "run_count": len(runs),
        "latest_run": {"status": latest_run.status, "updated_at": latest_run.updated_at.isoformat()}
        if latest_run
        else None,
    }


def version_dict(version: Any, *, with_content: bool = False) -> dict[str, Any]:
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
        script_dict = script_to_dict(version.script)
        data["script"] = script_dict
        data["validation"] = script_dict.get("validation", [])
    return data


def sse_frame(event: str, data: dict[str, Any]) -> str:
    """把事件封装成 SSE 文本帧。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---------- 工作目录写入（失败不阻断主流程）----------


def workspace() -> Any:
    """取当前工作目录实例（未配置 / 仅应用内时，写文件会静默跳过）。"""
    cfg = deps.settings()
    return current_workspace(cfg.effective_workspace_root, cfg.workspace_persist)


def proj_title(raw_title: str) -> str:
    """把任意标题清洗成适合做文件名的安全文本。"""
    text = str(raw_title or "").strip() or "未命名剧本"
    text = re.sub(r'[<>:"\\|?*]', "_", text)
    return text[:80] or "未命名剧本"


def persist_original(project: Any) -> None:
    """把项目原著写入工作目录的「01_原稿」。"""
    ws = workspace()
    if not ws.configured:
        return
    try:
        ws.save_original(project.title, proj_title(project.title) + ".txt", project.raw_text)
    except Exception:  # noqa: BLE001
        pass  # 落盘失败不影响主流程


def persist_version(project: Any, version: Any, *, label: str | None = None) -> None:
    """把一份剧本版本写入工作目录的「02_版本」。"""
    ws = workspace()
    if not ws.configured:
        return
    try:
        text = script_to_screenplay(version.script)
        name = f"{proj_title(project.title)}_v{(version.label or label or '').strip() or 'version'}"
        ws.save_version(project.title, name, text)
    except Exception:  # noqa: BLE001
        pass
