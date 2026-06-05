"""LLM provider interface."""
from __future__ import annotations

from typing import Protocol, runtime_checkable
from enum import Enum


class Stage(str, Enum):
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
    """Factory: pick provider by env."""
    from ..config import get_settings

    settings = get_settings()
    name = (settings.llm_provider or "openai").lower()
    if name == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider(settings)
    if name == "mock":
        from .mock_provider import MockProvider

        return MockProvider()
    # graceful fallback
    from .mock_provider import MockProvider

    return MockProvider()
