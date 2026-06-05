"""LLM provider interface."""
from __future__ import annotations

from enum import StrEnum
from typing import Protocol, runtime_checkable


class Stage(StrEnum):
    SUMMARY = "summary"
    BIBLE = "bible"
    CHARACTERS = "characters"
    SCENE_PLAN = "scene_plan"
    DIALOGUE = "dialogue"
    REPAIR = "repair"


@runtime_checkable
class LLMProvider(Protocol):
    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        *,
        stage: Stage,
    ) -> dict: ...


def get_provider() -> LLMProvider:
    """Factory: only OpenAI is supported. Mock fallback removed per project decision."""
    from ..config import get_settings
    from .openai_provider import OpenAIProvider

    return OpenAIProvider(get_settings())
