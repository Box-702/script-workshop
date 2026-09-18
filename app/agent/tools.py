# =====================================================================
# tools.py —— ReAct 工具集合
#
# Agent 在「计划」阶段通过工具主动读取上下文。
# 工具通过闭包捕获本次运行的目标剧本 / 项目 / 存储。
# =====================================================================

from __future__ import annotations

import logging
from typing import Annotated

from langchain_core.tools import BaseTool, tool

from ..domain import Script
from ..pipeline.knowledge import format_author_style
from ..pipeline.patch import validate_script
from ..store import Project, Store

log = logging.getLogger(__name__)


def _text_excerpt(value: str, limit: int = 1200) -> str:
    """把文本压成单行截断摘要，避免工具输出过长撑爆上下文。"""
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _search_source_text(raw_text: str, query: str, k: int = 3) -> list[str]:
    """在原文中搜索包含关键词的段落（纯文本搜索，无向量）。"""
    text = raw_text or ""
    if not text or not query.strip():
        return []

    # 按句子分割
    import re
    sentences = re.split(r"[。！？!?；;\n]", text)
    sentences = [s.strip() for s in sentences if s.strip()]

    # 提取查询关键词（按空格/逗号分割）
    keywords = [w.strip() for w in re.split(r"[，,、\s]+", query) if len(w.strip()) >= 2]
    if not keywords:
        keywords = [query.strip()]

    # 按关键词命中数打分
    scored: list[tuple[int, str]] = []
    for sent in sentences:
        hits = sum(1 for kw in keywords if kw in sent)
        if hits > 0:
            scored.append((hits, sent))

    scored.sort(key=lambda x: x[0], reverse=True)

    # 合并相邻句子为段落
    results: list[str] = []
    used: set[int] = set()
    for _, sent in scored[:k * 2]:
        idx = sentences.index(sent)
        if idx in used:
            continue
        # 取前后各一句组成上下文
        start = max(0, idx - 1)
        end = min(len(sentences), idx + 2)
        para = "。".join(sentences[start:end]) + "。"
        if para not in results:
            results.append(para)
            for i in range(start, end):
                used.add(i)
        if len(results) >= k:
            break

    return results


def build_tools(
    script: Script,
    project: Project,
    store: Store,
    raw_text: str,
) -> list[BaseTool]:
    """构造本运行可用的工具集合。"""

    @tool
    def get_script_overview() -> str:
        """查看整个剧本的概况：标题、梗概、主题、人物与地点清单、场景列表。"""
        chars = "; ".join(f"{c.name}({c.role or '其他'})" for c in script.characters) or "无"
        locs = "; ".join(loc.name for loc in script.locations) or "无"
        scenes = "; ".join(f"{s.id}: {s.title}({s.purpose})" for s in script.scenes) or "无"
        return (
            f"标题：{script.title}\n"
            f"梗概：{script.logline}\n"
            f"主题：{', '.join(script.themes) or '未填写'}\n"
            f"人物：{chars}\n"
            f"地点：{locs}\n"
            f"场景：\n{scenes}"
        )

    @tool
    def get_scene_detail(scene_id: str) -> str:
        """查看某个场景的完整内容，包括其节拍流。需要传入场景 id。"""
        for scene in script.scenes:
            if scene.id == scene_id:
                return f"场景 {scene.id} {scene.title}\n{scene.model_dump_json(exclude_none=True, indent=2)}"
        return f"未找到场景：{scene_id}"

    @tool
    def get_source_text(max_chars: Annotated[int, "最多返回的字符数"] = 1500) -> str:
        """查看用户提供的原始文本片段（节制长度，避免超长上下文）。"""
        content = _text_excerpt(raw_text or "")
        if not content:
            return "（无原始文本）"
        return content[: max(200, min(max_chars, 6000))]

    @tool
    def search_source(query: Annotated[str, "要搜索的主题或关键词"], k: Annotated[int, "返回段落数"] = 3) -> str:
        """在原始文本中搜索包含关键词的段落，用于让改写更贴近原作。"""
        hits = _search_source_text(raw_text, str(query), max(1, min(int(k or 3), 6)))
        if not hits:
            return "（搜索不到相关原文段落）"
        return "\n---\n".join(f"[{i + 1}] {_text_excerpt(h, 800)}" for i, h in enumerate(hits))

    @tool
    def get_author_style() -> str:
        """查看从原文提取的作者语言风格画像。"""
        return format_author_style(raw_text)

    @tool
    def list_versions(limit: Annotated[int, "返回的版本数"] = 5) -> str:
        """查看最近的历史版本，用于判断何时产生新版本、是否回滚。"""
        versions = store.list_versions(project.id)[: limit]
        if not versions:
            return "（还没有版本）"
        lines = [
            f"{v.id}  [{v.source_type}] {v.label or '未命名'} 由 {v.created_at.isoformat()}"
            for v in versions
        ]
        return "\n".join(lines)

    @tool
    def validate_tool() -> str:
        """校验当前剧本的一致性，返回问题清单（人物/地点引用、id 唯一性等）。"""
        issues = validate_script(script)
        if not issues:
            return "校验通过，没有发现问题。"
        return "\n".join(f"{s.severity}: {s.path} {s.message}" for s in issues)

    return [
        get_script_overview,
        get_scene_detail,
        get_source_text,
        search_source,
        get_author_style,
        list_versions,
        validate_tool,
    ]
