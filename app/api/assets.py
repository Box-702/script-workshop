# =====================================================================
# assets.py —— 项目媒体素材（参考视频等）
#
# 两条入库通道：
#   - upload：文件落盘到 workspace_root/assets/<project_id>/，本服务提供回放；
#     适合预览、归档与即梦等支持本地上传的平台。注意 MiniMax 等服务商
#     拉取参考素材要求公网可访问 URL，本机回放地址对他们不可达。
#   - url：直接登记外部公网链接（对象存储 / 图床 / 已生成成片的 CDN 地址）。
# =====================================================================

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import common, deps
from ..store import gen_id

router = APIRouter()
log = logging.getLogger(__name__)

_ALLOWED_EXTS = {".mp4", ".mov", ".webm", ".m4v", ".mkv", ".avi"}
_MAX_BYTES = 200 * 1024 * 1024  # 200MB

_MEDIA_TYPES = {
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".webm": "video/webm", ".mkv": "video/x-matroska", ".avi": "video/x-msvideo",
}


class AssetUrlCreate(BaseModel):
    """登记一个外部素材链接。"""

    url: str = Field(min_length=1, max_length=2000)
    name: str = Field(default="", max_length=200)


def _asset_dict(a: Any) -> dict[str, Any]:
    return {
        "id": a.id,
        "project_id": a.project_id,
        "kind": a.kind,
        "name": a.name,
        "source": a.source,
        "url": a.url,
        "created_at": a.created_at.isoformat(),
    }


def _assets_dir(project_id: str) -> Path:
    root = Path(deps.settings().effective_workspace_root)
    d = root / "assets" / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.get("/projects/{project_id}/assets")
def list_assets(project_id: str, kind: str | None = None) -> list[dict[str, Any]]:
    """列出项目的媒体素材（默认全部，可按 kind 过滤）。"""
    common.get_project(project_id)
    return [_asset_dict(a) for a in deps.store().list_assets(project_id, kind=kind)]


@router.post("/projects/{project_id}/assets/upload")
async def upload_asset(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:  # noqa: B008
    """上传一个媒体文件作为项目素材。"""
    common.get_project(project_id)
    original = file.filename or "video.mp4"
    ext = Path(original).suffix.lower()
    if ext not in _ALLOWED_EXTS:
        raise HTTPException(400, f"不支持的格式 {ext}，可用：{' '.join(sorted(_ALLOWED_EXTS))}")

    asset_id = gen_id("asset")
    dest = _assets_dir(project_id) / f"{asset_id}{ext}"
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > _MAX_BYTES:
                    raise HTTPException(400, "文件超过 200MB 上限")
                out.write(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    rel = dest.relative_to(deps.settings().effective_workspace_root).as_posix()
    asset = deps.store().add_asset(
        project_id, kind="video", name=original, source="upload",
        url=f"/api/assets/file/{asset_id}", file_path=rel, id=asset_id,
    )
    return _asset_dict(asset)


@router.post("/projects/{project_id}/assets/url")
def add_asset_url(project_id: str, payload: AssetUrlCreate) -> dict[str, Any]:
    """登记一个外部素材 URL（公网直链，可直接喂给视频服务商）。"""
    common.get_project(project_id)
    url = payload.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "URL 必须以 http(s) 开头")
    name = payload.name.strip() or url.rsplit("/", 1)[-1] or "外部视频"
    asset = deps.store().add_asset(project_id, kind="video", name=name, source="url", url=url)
    return _asset_dict(asset)


@router.delete("/assets/{asset_id}")
def delete_asset(asset_id: str) -> dict[str, Any]:
    """删除素材记录；上传类文件尽力清理磁盘。

    Windows 下若回放流仍持有文件句柄，unlink 会失败——记录照删，
    留下的孤儿文件不阻塞删除操作（下次覆盖/手动清理）。
    """
    asset = deps.store().delete_asset(asset_id)
    if asset is None:
        raise HTTPException(404, "素材不存在")
    if asset.file_path:
        p = Path(deps.settings().effective_workspace_root) / asset.file_path
        try:
            p.unlink(missing_ok=True)
        except OSError as e:
            log.warning("素材文件未能删除（可能正被回放占用）：%s -> %s", p, e)
    return {"deleted": asset_id}


@router.get("/assets/file/{asset_id}")
def get_asset_file(asset_id: str) -> FileResponse:
    """回放上传的素材文件（预览用；服务商拉取需要公网 URL）。"""
    asset = deps.store().get_asset(asset_id)
    if asset is None or not asset.file_path:
        raise HTTPException(404, "素材不存在")
    p = Path(deps.settings().effective_workspace_root) / asset.file_path
    if not p.is_file():
        raise HTTPException(404, "素材文件已丢失")
    return FileResponse(p, media_type=_MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream"),
                        filename=asset.name)
