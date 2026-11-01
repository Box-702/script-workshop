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
        """发送一轮对话，尝试解析 JSON 响应；解析失败重采样一次。

        结构化输出偶发格式抖动（漏围栏/引号转义错/截断），同提示词重采样
        通常就能拿到合法 JSON——先重试再报错，别让一次抖动打断整条流水线。

        注意「截断」和「抖动」不是一回事：模型单次输出有上限，长剧本的分镜
        JSON 一旦超限就是从中间硬切断，整段 `json.loads` 必失败，但**前面的
        对象往往是完整的**。直接报错等于把已经生成好的 5 个场景全丢了
        （2026-11-01 实测：7 场拆解时第二批截断，整批作废）。所以先尝试
        「按对象切分救援」，救不回来才重采样。
        """
        import json
        import re

        def _parse(text: str) -> Any:
            # 尝试从 markdown 代码围栏中提取 JSON
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
            if match:
                text = match.group(1)
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass
            # 尝试找到第一个 { 或 [ 开始的 JSON
            for i, ch in enumerate(text):
                if ch in "{[":
                    try:
                        return json.loads(text[i:])
                    except json.JSONDecodeError:
                        continue
            # 截断救援：切出所有完整的顶层对象，丢掉被切坏的那一个。
            salvaged = salvage_objects(text)
            if salvaged:
                return salvaged
            raise ValueError(f"无法解析 JSON 响应：{text[:200]}") from None

        last_error: ValueError | None = None
        for _ in range(2):
            try:
                return _parse(self._invoke(system, user))
            except ValueError as e:
                last_error = e
        raise last_error if last_error else ValueError("无法解析 JSON 响应：空响应")


def salvage_objects(text: str) -> list[dict[str, Any]]:
    """从可能被截断的 JSON 文本里，切出所有**完整的**顶层对象。

    做法：从第一个 `[` 或 `{` 起扫，用括号深度切分，跳过字符串内部的括号
    （转义也要跳过，否则 `"他说：\\"{"` 会把深度算乱）。每个切出来的片段
    单独 `json.loads`，坏的那个直接丢掉——留下「完整的前 N 个」比整段作废
    有用得多。

    返回空列表表示一个完整对象都没有（那才是真的失败）。
    """
    import json

    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start < 0:
        return []

    out: list[dict[str, Any]] = []
    depth = 0
    in_str = False
    escaped = False
    obj_start: int | None = None

    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                obj_start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and obj_start is not None:
                try:
                    parsed = json.loads(text[obj_start:i + 1])
                    if isinstance(parsed, dict):
                        out.append(parsed)
                except json.JSONDecodeError:
                    pass
                obj_start = None
        elif ch == "[" and depth == 0:
            continue
    return out
