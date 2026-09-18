# =====================================================================
# test_plugin_loader.py —— 插件加载器测试
#
# 覆盖三级目录扫描（项目级 > 用户级 > 内置）、同名去重、tool 型插件加载。
# 用户级/项目级目录用 tmp_path + monkeypatch 模拟，不碰真实 home。
# =====================================================================

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.tools import tool as lc_tool

from app.plugin.base import Plugin, PluginManifest, PluginType
from app.plugin.loader import PluginLoader


def _make_plugin(root: Path, name: str, *, tools_py: str | None = None, mcp: bool = False) -> Path:
    """在 root 下造一个最小插件目录。"""
    d = root / name
    d.mkdir(parents=True)
    mcp_block = """
mcp:
  command: npx
  args: ["-y", "@some/server"]
""" if mcp else ""
    (d / "plugin.yaml").write_text(
        f'name: {name}\nversion: "1.0"\ndescription: {name} 测试插件\ntype: tool{mcp_block}\n',
        encoding="utf-8",
    )
    if tools_py:
        (d / "tools.py").write_text(tools_py, encoding="utf-8")
    return d


TOOLS_PY = '''
from langchain_core.tools import tool

@tool
def hello_plugin() -> str:
    \'\'\'插件测试工具。\'\'\'
    return "hi"
'''


def test_discover_scans_user_and_project_dirs(tmp_path, monkeypatch):
    """用户级与项目级目录里的插件都能被发现。"""
    user_dir = tmp_path / "user_plugins"
    proj_dir = tmp_path / "proj"
    user_dir.mkdir()
    proj_dir.mkdir()
    _make_plugin(user_dir, "user_tool")
    _make_plugin(proj_dir / ".plugins", "proj_tool")

    import app.plugin.loader as loader_mod
    monkeypatch.setattr(loader_mod, "_USER_PLUGINS_DIR", user_dir)

    plugins = PluginLoader(project_dir=proj_dir).discover()
    names = {p.name for p in plugins}
    assert {"user_tool", "proj_tool"} <= names


def test_same_name_project_overrides_user(tmp_path, monkeypatch):
    """同名插件按优先级去重：项目级 > 用户级。"""
    user_dir = tmp_path / "user_plugins"
    proj_dir = tmp_path / "proj"
    user_dir.mkdir()
    _make_plugin(user_dir, "dup")
    _make_plugin(proj_dir / ".plugins", "dup")

    import app.plugin.loader as loader_mod
    monkeypatch.setattr(loader_mod, "_USER_PLUGINS_DIR", user_dir)

    plugins = PluginLoader(project_dir=proj_dir).discover()
    dups = [p for p in plugins if p.name == "dup"]
    assert len(dups) == 1
    assert dups[0].manifest.path.parent.name == ".plugins"  # 项目级胜出


def test_tool_type_plugin_loads_langchain_tools(tmp_path, monkeypatch):
    """tools.py 里的 @tool 函数被加载为 LangChain 工具；mcp 段被忽略不报错。"""
    user_dir = tmp_path / "user_plugins"
    user_dir.mkdir()
    _make_plugin(user_dir, "with_tools", tools_py=TOOLS_PY, mcp=True)

    import app.plugin.loader as loader_mod
    monkeypatch.setattr(loader_mod, "_USER_PLUGINS_DIR", user_dir)

    plugins = PluginLoader().discover()
    plugin = next(p for p in plugins if p.name == "with_tools")
    assert plugin.error is None
    assert plugin.manifest.type == PluginType.TOOL
    assert len(plugin.all_tools()) == 1
    assert plugin.all_tools()[0].invoke({}) == "hi"


def test_broken_plugin_becomes_placeholder_with_error(tmp_path, monkeypatch):
    """清单损坏的插件不阻断扫描，生成带 error 的占位 Plugin。"""
    user_dir = tmp_path / "user_plugins"
    bad = user_dir / "bad"
    bad.mkdir(parents=True)
    (bad / "plugin.yaml").write_text("name: [broken", encoding="utf-8")  # 非法 YAML

    import app.plugin.loader as loader_mod
    monkeypatch.setattr(loader_mod, "_USER_PLUGINS_DIR", user_dir)

    plugins = PluginLoader().discover()
    bad = [p for p in plugins if p.name == "bad"]
    assert len(bad) == 1
    assert bad[0].error


def test_missing_dir_is_skipped(tmp_path, monkeypatch):
    """用户级目录不存在时静默跳过（连同项目级也不给目录）。"""
    import app.plugin.loader as loader_mod
    monkeypatch.setattr(loader_mod, "_USER_PLUGINS_DIR", tmp_path / "nonexistent")

    # 只有 builtin 目录可扫；这里只验证不抛异常、返回的是列表。
    plugins = PluginLoader(project_dir=tmp_path / "no_proj").discover()
    assert isinstance(plugins, list)


def test_manifest_defaults(tmp_path):
    """清单缺省字段回退：无 name 用目录名，无 type 回退 tool。"""
    d = tmp_path / "noname"
    d.mkdir()
    (d / "plugin.yaml").write_text("description: 只有描述\n", encoding="utf-8")

    plugin = PluginLoader().load_plugin(d, d / "plugin.yaml")
    assert isinstance(plugin, Plugin)
    assert plugin.name == "noname"
    assert plugin.manifest.type == PluginType.TOOL
