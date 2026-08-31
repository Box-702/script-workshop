# =====================================================================
# tools.py —— ReAct 工具集合
#
# 这些工具让 Agent 在「计划」阶段能够主动读取上下文，而不是把一切
# 都塞进提示词里。它们是 LangChain 的 @tool，会被绑定到模型上，
# 由模型在推理时决定何时调用、用什么参数调用。
#
# 设计说明：
#   - 工具通过闭包捕获「本次运行的目标剧本 / 项目 / 存储」。
#     因为每个 Agent 运行都针对一个固定 base 版本，所以这里的
#     script / raw_text / store 对一次运行而言是稳定的。
#   - 工具只做「读」；具体改写的落库由 apply 节点负责。
#   - retrieve_source 是「可选 RAG」工具：有向量后端时按语义检索原文，
#     没有时回退为明文片段，绝不让工具调用阻塞大体流程。
# =====================================================================

from __future__ import annotations

from typing import Annotated, Callable, TypeAlias

from langchain_core.tools import BaseTool, tool

from .domain import Script
from .patch import validate_script
from .store import Project, Store

# 检索回调签名：query -> 片段列表。实现来自 vector.retrieve，或明文回退。
Retriever: TypeAlias = Callable[[str, int], list[str]]


def _text_excerpt(value: str, limit: int = 1200) -> str:
    """把文本压成单行截断摘要，避免工具输出过长撑爆上下文。"""
    text = " ".join((value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def build_tools(
    script: Script,
    project: Project,
    store: Store,
    raw_text: str,
    *,
    retriever: Retriever | None = None,
) -> list[BaseTool]:
    """构造本运行可用的工具集合。"""

    @tool
    def get_script_overview() -> str:
        """查看整个剧本的概况：标题、梗概、主题、人物与地点清单、场景列表。"""
        chars = "; ".join(f"{c.name}({c.role or '其他'})" for c in script.characters) or "无"
        locs = "; ".join(l.name for l in script.locations) or "无"
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

    result: list[BaseTool] = [
        get_script_overview,
        get_scene_detail,
        get_source_text,
        list_versions,
        validate_tool,
    ]

    if retriever is not None:

        @tool
        def retrieve_source(query: Annotated[str, "要检索的主题或关键问题"], k: Annotated[int, "返回片段数"] = 3) -> str:
            """按主题检索原始文本中最相关的片段，用于让改写更贴近原作。"""
            hits = retriever(str(query), max(1, min(int(k or 3), 6)))
            if not hits:
                return "（检索不到相关原文片段）"
            return "\n---\n".join(f"[{i + 1}] {_text_excerpt(h, 800)}" for i, h in enumerate(hits))

        result.append(retrieve_source)

    return result
