"""OpenAI-compatible provider."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..config import Settings
from .base import Stage

log = logging.getLogger(__name__)


def _model_for(stage: Stage, s: Settings, override: str = "") -> str:
    if override:
        return override
    return {
        Stage.SUMMARY: s.llm_model_summary or s.openai_model,
        Stage.BIBLE: s.llm_model_bible or s.openai_model,
        Stage.CHARACTERS: s.openai_model,
        Stage.SCENE_PLAN: s.llm_model_scene or s.openai_model,
        Stage.DIALOGUE: s.llm_model_dialogue or s.openai_model,
        Stage.REPAIR: s.llm_model_repair or s.openai_model,
        Stage.AGENT: s.openai_model,
    }[stage]


# Errors we will retry. We import lazily because openai might be missing in
# environments where the user is using a different SDK.
def _build_retryable_exceptions() -> tuple[type, ...]:
    try:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            InternalServerError,
            RateLimitError,
        )
    except Exception:  # pragma: no cover - openai not installed
        return ()
    return (APIConnectionError, APITimeoutError, InternalServerError, RateLimitError)


_RETRYABLE: tuple[type, ...] = _build_retryable_exceptions()


class OpenAIProvider:
    def __init__(
        self,
        settings: Settings,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        language: str | None = None,
    ) -> None:
        self.settings = settings
        self.model_override = (model or "").strip()
        self.language = (language or settings.output_language or "zh-CN").strip()
        effective_api_key = (api_key or settings.openai_api_key or "").strip()
        effective_base_url = (base_url or settings.openai_base_url or "").strip()
        self._client = None
        self._init_error: str | None = None
        if not effective_api_key:
            self._init_error = (
                "OpenAI API key is not configured. Set X-OpenAI-API-Key header "
                "or OPENAI_API_KEY env var."
            )
            log.warning("OpenAI provider constructed without an API key")
            return
        try:
            from openai import OpenAI  # type: ignore

            self._client = OpenAI(
                api_key=effective_api_key, base_url=effective_base_url
            )
        except Exception as e:
            self._init_error = f"failed to init OpenAI client: {e}"
            log.warning(self._init_error)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(_RETRYABLE),
        before_sleep=before_sleep_log(log, logging.WARNING),
    )
    def _call(self, model: str, sys_prompt: str, user_prompt: str) -> str:
        resp = self._client.chat.completions.create(  # type: ignore[union-attr]
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )
        return resp.choices[0].message.content or "{}"

    def generate_structured(
        self, prompt: str, schema: dict, *, stage: Stage
    ) -> dict:
        if self._client is None:
            raise RuntimeError(
                self._init_error or "OpenAI client is not initialized"
            )

        model = _model_for(stage, self.settings, self.model_override)
        lang = (self.language or "zh-CN").strip() or "zh-CN"
        # For Chinese output, instruct the model explicitly. For English, the
        # default instructions are sufficient.
        if lang.lower().startswith("zh"):
            lang_instruction = (
                f"所有面向用户的中文/外文自然语言值必须使用 {lang}，包括 title、logline、"
                "summary、purpose、conflict、action、dialogue、line、emotion、subtext、"
                "personality、goal、motivation、speech_style、adaptation_notes.reason 等。"
                "专有名词（如人名、地名、品牌）保留原文。id 字段必须保持纯 ASCII "
                "（小写字母、数字、下划线）。"
            )
        else:
            lang_instruction = (
                f"All user-facing natural-language values must be written in {lang}. "
                "Keep id fields as plain ASCII (lowercase letters, digits, underscores)."
            )
        sys_prompt = (
            "You are a strict JSON generator. Output ONLY a valid JSON object matching the "
            "provided JSON schema. No commentary, no markdown fence. "
            f"{lang_instruction}"
        )
        user_prompt = f"{prompt}\n\n# JSON Schema\n{json.dumps(schema, ensure_ascii=False)}"
        try:
            content = self._call(model, sys_prompt, user_prompt)
        except Exception as e:
            # Surface non-retryable errors verbatim; log the rest with type info.
            if not _RETRYABLE or not isinstance(e, _RETRYABLE):
                log.error("openai call failed at stage=%s: %s", stage, e)
            raise
        return _safe_json(content)


def _safe_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from text, even if wrapped in fences or chatter."""
    text = text.strip()
    # strip code fences
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # greedy object match
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    return {}
