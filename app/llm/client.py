# =====================================================================
# client.py —— 模型调用统一门面
#
# 全项目只有这一个类会去构造具体模型客户端。上层业务（图节点 / 剧组 /
# 对话 / 质检 / 文生图）统一通过它取能力，不关心厂商差异：
#
#   llm.available         是否配置了对话模型（无 key 时上层走本地回退）
#   llm.chat()            可 bind_tools 的聊天模型（ReAct / 工具调用）
#   llm.structured(Schema) 结构化输出（json_mode，兼容推理模型）
#   llm.system_prompt()   带语言约束的统一系统提示词
#   llm.vision()          视觉客户端（定妆图质检）
#   llm.image()           文生图客户端（参考资产）
#
# 没有 key 时返回 None / 抛异常由调用方兜底，保证「导入 → 生成 → 提议
# → 审阅 → 接受」链路在离线状态下依然可跑通、可演示。
# =====================================================================

from __future__ import annotations

from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from pydantic import BaseModel

from ..config import Settings
from .base import Modality, ModelConfig
from .image import ImageClient, build_image_client
from .providers import build_chat_model, get_provider_spec
from .registry import describe_providers, resolve_chat, resolve_image, resolve_vision
from .vision import VisionClient

T = TypeVar("T", bound=BaseModel)


class LLM:
    """对话模型 + 视觉 + 文生图的统一入口（单例，见 app/deps.py）。"""

    def __init__(self, settings: Settings, store: Any = None) -> None:
        self.settings = settings
        self._store = store
        self.config: ModelConfig | None = resolve_chat(settings, store)
        self._model: BaseChatModel | None = (
            build_chat_model(self.config) if self.config else None
        )

    # ---------- 对话能力 ----------

    @property
    def available(self) -> bool:
        """是否配置并实例化了对话模型。"""
        return self._model is not None

    @property
    def provider_label(self) -> str:
        """厂商展示名；无模型时为 local-fallback（前端与提示词都用它）。"""
        return self.config.label if self.config else "local-fallback"

    def chat(self) -> BaseChatModel:
        """返回可 bind_tools 的聊天模型（用于 ReAct 工具调用循环）。"""
        if self._model is None:
            raise RuntimeError(
                "模型未配置。请在 .env 中设置 OPENAI_API_KEY / ZHIPUAI_API_KEY / "
                "DEEPSEEK_API_KEY，或在前端「设置 → 模型」里添加 provider。"
            )
        return self._model

    def structured(self, schema: type[T]) -> Any:
        """返回一个接受消息、输出 ``schema`` 实例的结构化可运行对象。

        用 ``json_mode``（response_format=json_object）做结构化输出：
        对 OpenAI 兼容服务最稳，且 DeepSeek 的思考模式不支持强制
        tool_choice，不能走 function_calling。
        """
        if self._model is None:
            raise RuntimeError("模型未配置，无法进行结构化输出。")
        return self._model.with_structured_output(schema, method="json_mode")

    def system_prompt(self) -> str:
        """构造统一的系统提示词，包括语言约束与输出规范。"""
        lang = self.settings.output_language or "zh-CN"
        if lang.lower().startswith("zh"):
            style = "简体中文" if lang.lower() in {"zh-cn", "zh-hans", "zh"} else "繁體中文"
            lang_note = (
                f"所有面向用户的自然语言字段必须使用 {style}（{lang}），包括 title、logline、"
                "purpose、conflict、action、dialogue、line、emotion、subtext、"
                "entry_state、exit_state、adaptation_notes.reason。"
                "id 字段必须保持纯 ASCII（小写字母、数字、下划线）。"
            )
        else:
            lang_note = (
                f"所有面向用户的自然语言字段必须使用 {lang}。"
                "id 字段必须保持纯 ASCII（小写字母、数字、下划线）。"
            )
        return (
            "你是剧本改写助手，负责把用户的小说或剧本片段改编成结构化剧本。"
            "你只输出符合给定 JSON Schema 的有效对象，不要输出额外说明或 Markdown 代码围栏。"
            f"{lang_note}"
        )

    # ---------- 其他能力维度 ----------

    def vision(self) -> VisionClient:
        """视觉客户端（看图质检）。未配置时 available=False，调用方应跳过。"""
        config = resolve_vision(self.settings, self._store)
        return VisionClient(config) if config else VisionClient(
            ModelConfig(provider="none", model="", label="未配置视觉模型")
        )

    def image(self) -> ImageClient | None:
        """文生图客户端。未配置时返回 None。"""
        return build_image_client(resolve_image(self.settings, self._store))

    # ---------- 自省 ----------

    def describe(self) -> dict[str, Any]:
        """当前模型配置摘要（不含 key），供 /api/status 与设置页展示。"""
        config = self.config
        return {
            "available": self.available,
            "provider": config.provider if config else "local-fallback",
            "provider_label": self.provider_label,
            "model": config.model if config else "",
            "base_url": config.base_url if config else "",
            "source": config.source if config else "none",
            "vision": self.describe_vision(),
            "providers": describe_providers(),
        }

    def describe_vision(self) -> dict[str, Any]:
        config = resolve_vision(self.settings, self._store)
        return {
            "available": bool(config and config.api_key),
            "provider": config.provider if config else "",
            "model": config.model if config else "",
        }


def build_llm(settings: Settings | None = None, store: Any = None) -> LLM:
    """构造模型门面。未显式传入时使用全局 Settings。"""
    from ..config import get_settings

    return LLM(settings or get_settings(), store)


# 供上层按能力维度做校验/展示。
__all__ = ["LLM", "Modality", "ModelConfig", "build_llm", "get_provider_spec"]
