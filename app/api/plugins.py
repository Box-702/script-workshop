# =====================================================================
# plugins.py —— 插件管理
#
# 列出 / 启用 / 禁用 / 卸载 / 重载 / 从本地目录安装插件。
# 插件系统本身在 app/plugin/。
# =====================================================================

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from . import deps
from .schemas import PluginInstallRequest

router = APIRouter()


@router.get("/plugins")
def list_plugins() -> list[dict[str, Any]]:
    """列出所有已加载的插件。"""
    return deps.plugin_registry().list_plugins()


@router.post("/plugins/{name}/enable")
def enable_plugin(name: str) -> dict[str, Any]:
    """启用插件。"""
    if not deps.plugin_registry().enable(name):
        raise HTTPException(404, f"插件 {name} 不存在")
    return {"ok": True, "name": name}


@router.post("/plugins/{name}/disable")
def disable_plugin(name: str) -> dict[str, Any]:
    """禁用插件。"""
    if not deps.plugin_registry().disable(name):
        raise HTTPException(404, f"插件 {name} 不存在")
    return {"ok": True, "name": name}


@router.delete("/plugins/{name}")
def uninstall_plugin(name: str) -> dict[str, Any]:
    """卸载插件（从注册表移除 + 删除磁盘文件）。"""
    if not deps.plugin_registry().uninstall(name):
        raise HTTPException(404, f"插件 {name} 不存在")
    return {"ok": True, "name": name}


@router.post("/plugins/{name}/reload")
def reload_plugin(name: str) -> dict[str, Any]:
    """重新加载插件。"""
    if not deps.plugin_registry().reload(name):
        raise HTTPException(404, f"插件 {name} 不存在或重载失败")
    return {"ok": True, "name": name}


@router.post("/plugins/install")
def install_plugin(payload: PluginInstallRequest) -> dict[str, Any]:
    """从本地目录安装插件。"""
    from ..plugin.loader import PluginLoader

    plugin_path = Path(payload.path)
    if not plugin_path.is_dir():
        raise HTTPException(400, f"目录不存在：{payload.path}")
    manifest_path = plugin_path / "plugin.yaml"
    if not manifest_path.is_file():
        raise HTTPException(400, f"目录中缺少 plugin.yaml：{payload.path}")

    try:
        plugin = PluginLoader().load_plugin(plugin_path, manifest_path)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"加载插件失败：{e}") from e

    deps.plugin_registry().register(plugin)
    return {"ok": True, "name": plugin.name, "version": plugin.manifest.version}
