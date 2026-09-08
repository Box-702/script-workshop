# =====================================================================
# deps.py —— 依赖单例（无 RAG 版）
#
# 用 lru_cache 保证整个进程只创建一份后端实例。
# =====================================================================

from __future__ import annotations

from functools import lru_cache

from .config import Settings, get_settings
from .llm import LLM, build_llm
from .store import Store
from .subagents import SubAgentRunner, get_runner
from .video import ProviderRegistry
from .video import get_registry as get_video_registry
from .video.queue import VideoJobManager
from .video.queue import get_manager as get_video_manager


@lru_cache
def settings() -> Settings:
    return get_settings()


@lru_cache
def store() -> Store:
    return Store(settings().database_url)


@lru_cache
def llm() -> LLM:
    return build_llm(settings())


@lru_cache
def subagent_runner() -> SubAgentRunner:
    return get_runner()


@lru_cache
def video_registry() -> ProviderRegistry:
    return get_video_registry()


@lru_cache
def video_manager() -> VideoJobManager:
    return get_video_manager()
