# =====================================================================
# base.py —— 剧组 Agent 基类
#
# 定义 CrewAgent 抽象和 CrewTaskResult 统一返回格式。
# 所有剧组 Agent 继承 CrewAgent，实现 run() 方法。
# =====================================================================

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from ..domain import Script
from ..llm import LLM

log = logging.getLogger(__name__)


@dataclass
class CrewTaskResult:
    """Agent 任务执行结果。"""

    success: bool = True
    data: Any = None  # 结构化输出（Pydantic 模型或 dict）
    summary: str = ""  # 人类可读的摘要
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class CrewAgent(ABC):
    """剧组 Agent 抽象基类。

    子类必须实现：
      - name / label：角色标识
      - run()：执行逻辑
    """

    name: str = ""  # 唯一标识，如 "director"
    label: str = ""  # 显示名，如 "导演"
    emoji: str = "🎬"  # 角色图标

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    @abstractmethod
    def run(self, script: Script, **kwargs: Any) -> CrewTaskResult:
        """执行 Agent 任务。

        Args:
            script: 当前剧本。
            **kwargs: Agent 特有参数。

        Returns:
            CrewTaskResult 含结构化输出。
        """
        ...

    def _chat(self) -> BaseChatModel:
        """获取聊天模型。未配置时抛异常。"""
        if not self.llm.available:
            raise RuntimeError(f"{self.label} 需要配置对话模型才能工作")
        return self.llm.chat()

    def _invoke(self, system: str, user: str) -> str:
        """发送一轮对话，返回文本响应。"""
        from langchain_core.messages import HumanMessage, SystemMessage

        resp = self._chat().invoke([
            SystemMessage(content=system),
            HumanMessage(content=user),
        ])
        return str(resp.content or "").strip()

    def _invoke_json(self, system: str, user: str) -> dict[str, Any]:
        """发送一轮对话，尝试解析 JSON 响应。"""
        import json
        import re

        text = self._invoke(system, user)
        # 尝试从 markdown 代码围栏中提取 JSON
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
        if match:
            text = match.group(1)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # 尝试找到第一个 { 或 [ 开始的 JSON
            for i, ch in enumerate(text):
                if ch in "{[":
                    try:
                        return json.loads(text[i:])
                    except json.JSONDecodeError:
                        continue
            raise ValueError(f"无法解析 JSON 响应：{text[:200]}") from None
