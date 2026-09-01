# =====================================================================
# test_workspace.py —— 工作目录（结构化文件夹工作流程）
# =====================================================================

import os
import shutil
import time
from pathlib import Path

import pytest

from app.workspace import SUBDIRS, Workspace, sanitize_folder


@pytest.fixture()
def ws_dir() -> Path:
    """在项目 data/ 下建一个可写目录（沙箱会拒绝系统临时目录）。"""
    d = Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"workspace_test_{os.getpid()}_{time.time_ns()}"
    yield p
    shutil.rmtree(p, ignore_errors=True)


def test_sanitize_folder_strips_illegal_chars():
    assert sanitize_folder('a/b\\c:d"e*f?g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"
    assert sanitize_folder("   ") != ""
    assert sanitize_folder("雨夜") == "雨夜"


def test_workspace_unconfigured_raises_on_ensure():
    ws = Workspace(None)
    assert not ws.configured
    with pytest.raises(ValueError):
        ws.ensure_root()


def test_workspace_creates_structure(ws_dir: Path):
    ws = Workspace(ws_dir)
    pdir = ws.project_dir("雨夜")
    assert pdir.name == "雨夜"
    for code, _ in SUBDIRS:
        assert (pdir / code).is_dir()


def test_workspace_saves_original_version_export(ws_dir: Path):
    ws = Workspace(ws_dir)
    original = ws.save_original("雨夜", "原著.txt", "凌晨三点，雨夜。")
    version = ws.save_version("雨夜", "剧本版本_v2", "版本内容")
    exported = ws.save_export("雨夜", "导出_v2", b"bytes", ".docx")

    assert original.exists() and "凌晨三点" in original.read_text(encoding="utf-8")
    assert version.exists() and version.read_text(encoding="utf-8") == "版本内容"
    assert exported.exists() and exported.read_bytes() == b"bytes"

    # 结构化分格：原稿/版本/导出 分别在对应的 0X_ 子目录。
    assert "01_原稿" in str(original)
    assert "02_版本" in str(version)
    assert "03_导出" in str(exported)


def test_workspace_trees_and_readme(ws_dir: Path):
    ws = Workspace(ws_dir)
    ws.save_original("雨夜", "原著.txt", "内容")
    ws.save_note("雨夜", "风格.md", "冷峻、留白")
    tree = ws.tree_text("雨夜")
    assert "01_原稿" in tree and "02_版本" in tree and "04_知识库" in tree
    assert (ws_dir / "_README.txt").exists()


def test_workspace_remove_project(ws_dir: Path):
    ws = Workspace(ws_dir)
    ws.save_original("雨夜", "原著.txt", "内容")
    assert (ws_dir / "雨夜").exists()
    ws.save_original("另一个", "原著.txt", "其他内容")
    # 只删目标项目，不影响其它项目与根目录。
    assert ws.remove_project("雨夜") is True
    assert not (ws_dir / "雨夜").exists()
    assert (ws_dir / "另一个").exists()
    assert ws.remove_project("不存在") is False


def test_list_project_files_groups_by_subdir(ws_dir: Path):
    ws = Workspace(ws_dir)
    ws.save_original("雨夜", "原著.txt", "内容")
    ws.save_version("雨夜", "v1", "版本")
    ws.save_export("雨夜", "v1", b"docs", ".docx")
    listing = ws.list_project_files("雨夜")
    assert listing is not None
    codes = [f["code"] for f in listing["folders"]]
    assert "01_原稿" in codes and "02_版本" in codes and "03_导出" in codes


def test_resolve_file_blocks_traversal(ws_dir: Path):
    ws = Workspace(ws_dir)
    ws.save_original("雨夜", "原著.txt", "内容")
    assert ws.resolve_file("雨夜", "01_原稿/原著_雨夜.txt") is not None
    assert ws.resolve_file("雨夜", "../../secret.txt") is None
    assert ws.resolve_file("雨夜", "../other") is None


def test_list_files_in_app_mode_returns_none(ws_dir: Path):
    ws = Workspace(ws_dir, persist=False)
    assert ws.list_project_files("雨夜") is None
    assert ws.resolve_file("雨夜", "01_原稿/a.txt") is None


def test_runtime_configure_root():
    from app import workspace as ws_mod

    saved = ws_mod._runtime_root
    try:
        assert not ws_mod.current_workspace(None).configured
        configured = ws_mod.configure_root("C:/somewhere")
        assert configured.configured
        assert ws_mod.current_workspace().root is not None
    finally:
        ws_mod._runtime_root = saved
