# =====================================================================
# memory_tools.py —— 轻件域：长期记忆 + 技能加载
#
# remember / recall 是「AI 只提议，人做决定」在偏好层的延伸：用户明说才记。
# load_skill 是渐进披露的第二级：系统提示里只有目录（每技能几行），
# 正文要靠它拉——技能再多，提示词也只长目录那几行。
# =====================================================================

from __future__ import annotations

from langchain_core.tools import tool

from .context import ToolContext, main_skill_names

# 记忆类型 -> 中文名（recall 的展示与 remember 的确认共用）。
MEMORY_KIND_LABELS = {"preference": "用户偏好", "decision": "项目决定", "feedback": "对话反馈"}


def build(ctx: ToolContext) -> list:
    """装配记忆与技能工具。"""
    store = ctx.store

    @tool
    def remember(content: str, kind: str = "preference") -> str:
        """记住用户的长期偏好或本项目的决定，之后每轮对话都会自动遵循。kind=preference（用户偏好，跨项目生效）/ decision（项目决定，只在本项目生效）/ feedback（对话内反馈，只在本对话生效）。用户说「记住我喜欢… / 以后都… / 这个项目定下来…」时主动调用。参数：content=要记住的内容（一句话）；kind=记忆类型。"""
        text = (content or "").strip()
        if not text:
            return "要记住的内容不能为空。"
        kind = kind if kind in ("preference", "decision", "feedback") else "preference"
        pid = ctx.collector.get("project_id")
        tid = ctx.collector.get("conversation_id")
        scope = {"preference": "global", "decision": "project", "feedback": "conversation"}[kind]
        if kind == "decision" and not pid:
            return "项目级决定需要先有项目上下文，请改用 preference 或先创建项目。"
        store.add_memory(
            kind=kind, scope=scope, content=text,
            project_id=pid if scope in ("project", "conversation") else None,
            conversation_id=tid if scope == "conversation" else None,
        )
        return f"已记住（{MEMORY_KIND_LABELS[kind]}）：{text}"

    @tool
    def recall() -> str:
        """列出当前生效的全部记忆（全局偏好 + 本项目决定 + 本对话反馈），用于回答「你记得什么 / 我之前说过什么」。无需参数。"""
        rows = store.list_memories(
            project_id=ctx.collector.get("project_id"),
            conversation_id=ctx.collector.get("conversation_id"),
        )
        if not rows:
            return "还没有任何记忆。用户明确说「记住…」时可以用 remember 保存。"
        lines = [
            f"- （{MEMORY_KIND_LABELS.get(m.kind, m.kind)}）{m.content.strip()}"
            for m in rows[:20] if m.content.strip()
        ]
        return "当前生效的记忆：\n" + "\n".join(lines)

    @tool
    def load_skill(name: str) -> str:
        """加载某个工作流的完整执行细则（步骤顺序、硬门槛、失败怎么处理）。只能加载系统提示「可用技能」里列出的名字；进入该领域做事之前先调用一次，同一轮里不必重复。参数：name=技能名。"""
        from ...skills import load_skill as _load_skill_body

        key = (name or "").strip()
        allowed = main_skill_names()
        if key not in allowed:
            # 不抛异常：工具报错会污染这一轮的消息流，返回可读提示让模型自己改口。
            return f"没有这个技能：{key or '（空）'}。可加载：{'、'.join(sorted(allowed)) or '无'}。"
        try:
            skill = _load_skill_body(key)
        except Exception as e:  # noqa: BLE001
            return f"技能 {key} 读取失败：{e}"
        extra = f"\n\n（该技能还有附属文件：{'、'.join(skill.files)}）" if skill.files else ""
        return skill.body + extra

    return [load_skill, remember, recall]
