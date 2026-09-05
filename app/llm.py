# =====================================================================
# llm.py —— 模型接入层
#
# 统一封装 LangChain 的 ChatOpenAI（兼容任意 OpenAI 兼容服务：
# OpenAI / DeepSeek / Qwen / Moonshot / vLLM 等）。
#
# 关键行为：
#   - 配置了 OPENAI_API_KEY 时，返回一个可用的聊天模型；
#   - 没有 key 时返回 None，由上层图节点走「本地规则回退」，
#     从而保证整个「导入 -> 生成 -> Agent 提议 -> 审阅 -> 接受」链路
#     在没有模型时也能跑通、可演示。
#
# 我们还暴露了：
#   - chat()：获取底层的 ChatOpenAI（可 bind_tools 做 ReAct 工具调用）；
#   - structured(model)：获取 with_structured_output 后的可运行对象；
#   - system_prompt()：统一的、含语言约束的系统提示词。
# =====================================================================

from __future__ import annotations

from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from .config import Settings

# 泛型，用于标注结构化输出的目标模型类型。
T = TypeVar("T", bound=BaseModel)


class LLM:
    """聊天模型封装。``available`` 表示是否真正可以调用模型。

    模型来源按优先级：
      1. OPENAI_*（OpenAI 或任意兼容 base_url）；
      2. DEEPSEEK_*（DeepSeek 原生，走其 OpenAI 兼容协议）。
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider_label = "local-fallback"
        self._model: ChatOpenAI | None = None
        if settings.openai_api_key.strip():
            self.provider_label = "openai-compatible"
            self._model = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url.rstrip("/"),
                temperature=0.4,
            )
        elif settings.deepseek_api_key.strip():
            self.provider_label = "deepseek"
            # DeepSeek V3.x/V4 支持 thinking 开关；默认关闭深度思考可显著降低延迟
            # （单次 ~50s -> ~10s）。注意：必须用 extra_body 透传（model_kwargs
            # 会被 langchain 展开成 kwargs 而报错）。
            extra = {"thinking": {"type": "enabled" if settings.deepseek_thinking else "disabled"}}
            self._model = ChatOpenAI(
                model=settings.deepseek_model,
                api_key=settings.deepseek_api_key,
                base_url=settings.deepseek_base_url.rstrip("/"),
                temperature=0.4,
                extra_body=extra,
            )

    @property
    def available(self) -> bool:
        """是否配置并实例化了模型。"""
        return self._model is not None

    def chat(self) -> BaseChatModel:
        """返回可 bind_tools 的聊天模型（用于 ReAct 工具调用循环）。"""
        if self._model is None:
            raise RuntimeError("模型未配置。请在 .env 中设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY。")
        return self._model

    def structured(self, schema: type[T]) -> Any:
        """返回一个接受消息、输出 ``schema`` 实例的结构化可运行对象。

        用 ``json_mode``（response_format=json_object）做结构化输出：
        对 OpenAI 兼容服务最稳，且 DeepSeek 的思考模式（thinking）不支持
        强制 tool_choice，不能走 function_calling。
        """
        if self._model is None:
            raise RuntimeError("模型未配置。请在 .env 中设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY。")
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


def build_llm(settings: Settings | None = None) -> LLM:
    """构造模型封装单例。"""
    from .config import get_settings

    return LLM(settings or get_settings())
