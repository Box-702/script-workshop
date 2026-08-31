# =====================================================================
# deps.py —— 依赖单例（store / llm / vector / embedder / settings）
#
# 用 lru_cache 保证整个进程只创建一份后端实例（Postgres 连接、模型封装、
# 向量后端等），业务路由直接从这取，避免重复初始化。
# =====================================================================

from __future__ import annotations

from functools import lru_cache
from typing import Any

from .config import Settings, get_settings
from .llm import LLM, build_llm
from .store import Store
from .vector import build_embedder, build_vector_store


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
def embedder() -> Any:
    return build_embedder(settings())


@lru_cache
def vector() -> Any:
    return build_vector_store(settings(), embedder())
