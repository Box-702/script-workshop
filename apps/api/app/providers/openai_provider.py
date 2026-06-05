"""OpenAI provider. Falls back to mock if no API key configured."""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .base import LLMProvider, Stage
from ..config import Settings

log = logging.getLogger(__name__)


def _model_for(stage: Stage, s: Settings) -> str:
    return {
        Stage.SUMMARY: s.llm_model_summary or s.openai_model,
        Stage.BIBLE: s.llm_model_bible or s.openai_model,
        Stage.CHARACTERS: s.openai_model,
        Stage.SCENE_PLAN: s.llm_model_scene or s.openai_model,
        Stage.DIALOGUE: s.llm_model_dialogue or s.openai_model,
        Stage.REPAIR: s.llm_model_repair or s.openai_model,
    }[stage]


class OpenAIProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        if settings.openai_api_key:
            try:
                from openai import OpenAI  # type: ignore

                self._client = OpenAI(
                    api_key=settings.openai_api_key, base_url=settings.openai_base_url
                )
            except Exception as e:
                log.warning("failed to init OpenAI client: %s", e)

    def generate_structured(
        self, prompt: str, schema: dict, *, stage: Stage
    ) -> dict:
        # No key: degrade to mock so dev still works offline
        if self._client is None:
            from .mock_provider import MockProvider

            return MockProvider().generate_structured(prompt, schema, stage=stage)

        model = _model_for(stage, self.settings)
        sys_prompt = (
            "You are a strict JSON generator. Output ONLY a valid JSON object matching the "
            "provided JSON schema. No commentary, no markdown fence."
        )
        user_prompt = f"{prompt}\n\n# JSON Schema\n{json.dumps(schema, ensure_ascii=False)}"
        try:
            resp = self._client.chat.completions.create(  # type: ignore[union-attr]
                model=model,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.4,
            )
            content = resp.choices[0].message.content or "{}"
        except Exception as e:
            log.error("openai call failed at stage=%s: %s", stage, e)
            from .mock_provider import MockProvider

            return MockProvider().generate_structured(prompt, schema, stage=stage)
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
