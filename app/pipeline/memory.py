# =====================================================================
# memory.py —— 用户级记忆系统（替代 RAG）
#
# 三层记忆：
#   1. 偏好记忆（长期）：用户的写作风格偏好、改编习惯
#   2. 项目记忆（中期）：某个项目的具体决策、冻结区域
#   3. 对话记忆（短期）：当前对话中的即时反馈
#
# 全部存储在关系数据库中，不依赖向量库。
# Agent 通过工具调用读写记忆，而非预检索注入。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)

# 记忆种类
MEMORY_KINDS = ("preference", "decision", "feedback", "pattern")

# 记忆作用域
MEMORY_SCOPES = ("global", "project", "conversation")

# 中文标签
KIND_LABELS = {
    "preference": "用户偏好",
    "decision": "项目决策",
    "feedback": "即时反馈",
    "pattern": "行为模式",
}


def save_memory(
    store: Any,  # Store 实例
    *,
    kind: str,
    content: str,
    scope: str = "global",
    project_id: str | None = None,
    conversation_id: str | None = None,
    source: str = "user",
) -> str:
    """保存一条记忆。

    Args:
        kind: preference / decision / feedback / pattern
        content: 记忆内容
        scope: global / project / conversation
        project_id: 项目级记忆必填
        conversation_id: 对话级记忆必填
        source: user（用户主动说）/ agent（Agent 从行为中学）/ system

    Returns:
        memory_id
    """
    if kind not in MEMORY_KINDS:
        raise ValueError(f"未知记忆种类：{kind}")

    with store.session() as s:
        from ..store import Memory, gen_id

        m = Memory(
            id=gen_id("mem"),
            kind=kind,
            content=content.strip(),
            scope=scope,
            project_id=project_id,
            conversation_id=conversation_id,
            source=source,
        )
        s.add(m)
        s.commit()
        s.refresh(m)
        return m.id


def recall_memories(
    store: Any,
    *,
    project_id: str | None = None,
    conversation_id: str | None = None,
    kinds: list[str] | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """召回记忆。

    优先级：对话级 > 项目级 > 全局级。
    按创建时间倒序。
    """
    with store.session() as s:
        from ..store import Memory

        q = s.query(Memory)

        # 按作用域过滤
        conditions = []
        if conversation_id:
            conditions.append(
                (Memory.scope == "conversation") & (Memory.conversation_id == conversation_id)
            )
        if project_id:
            conditions.append(
                (Memory.scope == "project") & (Memory.project_id == project_id)
            )
        conditions.append(Memory.scope == "global")

        from sqlalchemy import or_

        q = q.filter(or_(*conditions))

        if kinds:
            q = q.filter(Memory.kind.in_(kinds))

        rows = q.order_by(Memory.created_at.desc()).limit(limit).all()

        return [
            {
                "id": r.id,
                "kind": r.kind,
                "content": r.content,
                "scope": r.scope,
                "project_id": r.project_id,
                "source": r.source,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]


def format_memories(memories: list[dict[str, Any]]) -> str:
    """将记忆格式化为可读文本，用于注入 prompt。"""
    if not memories:
        return ""
    lines = []
    for m in memories:
        kind_label = KIND_LABELS.get(m["kind"], m["kind"])
        lines.append(f"- [{kind_label}] {m['content']}")
    return "\n".join(lines)


def learn_from_decision(
    store: Any,
    *,
    project_id: str,
    action: str,
    instruction: str,
    patch_summary: str,
) -> None:
    """从用户的 accept/reject 行为中自动学习偏好。

    简单规则：
    - 用户拒绝时附带了反馈 → 记为偏好
    - 用户连续接受某类改动 → 记为模式
    """
    if action == "reject":
        # 用户拒绝并给出原因 = 明确的偏好信号
        save_memory(
            store,
            kind="preference",
            content=f"用户拒绝了「{instruction}」方向的改编：{patch_summary}",
            scope="project",
            project_id=project_id,
            source="agent",
        )
    elif action == "accept":
        # 接受 = 正面信号，但不单独记（避免噪声）
        pass
