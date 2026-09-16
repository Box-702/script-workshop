# =====================================================================
# versions.py —— 剧本版本
#
# 版本列表 / 详情、里程碑标记、编辑器改动落版、可读文本、导出下载。
# =====================================================================

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from ..pipeline.export import EXPORT_FORMATS, export_script, script_to_screenplay
from ..pipeline.patch import validate_script
from . import common, deps
from .schemas import ApplyEdit, MilestoneSet

router = APIRouter()


@router.get("/projects/{project_id}/versions")
def list_versions(project_id: str) -> list[dict[str, Any]]:
    common.get_project(project_id)
    return [common.version_dict(v) for v in deps.store().list_versions(project_id)]


@router.get("/versions/{version_id}")
def get_version(version_id: str) -> dict[str, Any]:
    v = deps.store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    return common.version_dict(v, with_content=True)


@router.post("/versions/{version_id}/milestone")
def set_milestone(version_id: str, payload: MilestoneSet) -> dict[str, Any]:
    """给版本打里程碑标记（草稿 / 候选 / 终稿）。用于「定稿」管理。"""
    allowed = {None, "draft", "candidate", "final"}
    if payload.milestone not in allowed:
        raise HTTPException(400, "milestone 需为 draft/candidate/final 或 null")
    v = deps.store().set_version_milestone(version_id, payload.milestone)
    if not v:
        raise HTTPException(404, "版本不存在")
    return {"ok": True, "version_id": version_id, "milestone": v.milestone}


@router.post("/versions/{version_id}/apply")
def apply_edit(version_id: str, payload: ApplyEdit) -> dict[str, Any]:
    """把编辑器产生的字段级改动应用到一个版本上，生成新版本（source_type=manual_edit）。"""
    from ..pipeline.patch import PatchOp, apply_patch

    v = deps.store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    project = deps.store().get_project(v.project_id)
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
    nv = deps.store().create_version(
        project,
        new_script,
        source_type="manual_edit",
        label="手动编辑",
        notes=f"基于 {version_id} 手动编辑（{len(ops)} 项改动）",
        parent_version_id=version_id,
        set_current=True,
        milestone="draft",
    )
    common.persist_version(project, nv)
    return {"version_id": nv.id, "validation": [i.model_dump() for i in issues]}


# ---------- 版本文本查看（Codex 式「打开文件看内容」）----------


@router.get("/versions/{version_id}/text")
def version_text(version_id: str) -> dict[str, Any]:
    """返回某版本的可读剧本文本（文本查看模式）。"""
    v = deps.store().get_version(version_id)
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
    v = deps.store().get_version(version_id)
    if not v:
        raise HTTPException(404, "版本不存在")
    fmt = (fmt or "txt").lower()
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(400, f"不支持的导出格式：{fmt}，可选：{'/'.join(EXPORT_FORMATS)}")
    try:
        data, ext = export_script(v.script, fmt)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    base = f"{common.proj_title(v.script.title)}_v{version_id}"
    filename = f"{base}{ext}"
    headers = common.content_disposition(filename)
    media_type = EXPORT_FORMATS[fmt]["mime"]

    # 同步写入工作目录（03_导出）——失败不影响下载本身。
    ws = common.workspace()
    if ws.configured:
        try:
            ws.save_export(v.script.title, base, data, ext)
        except Exception:  # noqa: BLE001
            pass

    return Response(content=data, media_type=media_type, headers=headers)
