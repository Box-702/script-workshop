# =====================================================================
# search.py —— 联网搜索模块
#
# 使用 Tavily API 为 Agent 提供联网搜索能力。
# Agent 可以搜索剧本创作参考、同类作品分析、写作技法等。
#
# Tavily 是专为 AI Agent 设计的搜索 API，返回结构化结果。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"


async def tavily_search(
    query: str,
    *,
    api_key: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_answer: bool = True,
) -> dict[str, Any]:
    """调用 Tavily 搜索 API。

    Args:
        query: 搜索查询。
        api_key: Tavily API key。
        max_results: 最大结果数。
        search_depth: "basic" 或 "advanced"。
        include_answer: 是否包含 AI 生成的摘要答案。

    Returns:
        {"results": [...], "answer": "...", "query": "..."}
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            TAVILY_API_URL,
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": search_depth,
                "include_answer": include_answer,
            },
        )
        resp.raise_for_status()
        return resp.json()


def search_sync(
    query: str,
    *,
    api_key: str,
    max_results: int = 5,
) -> dict[str, Any]:
    """同步版本的搜索（用于非 async 上下文）。"""
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已有 event loop 中（如 FastAPI），用 nest_asyncio 或直接 httpx 同步
            with httpx.Client(timeout=30) as client:
                resp = client.post(
                    TAVILY_API_URL,
                    json={
                        "api_key": api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                        "include_answer": True,
                    },
                )
                resp.raise_for_status()
                return resp.json()
        return asyncio.run(tavily_search(query, api_key=api_key, max_results=max_results))
    except Exception:
        # fallback: 同步调用
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                TAVILY_API_URL,
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": "basic",
                    "include_answer": True,
                },
            )
            resp.raise_for_status()
            return resp.json()


def format_search_results(data: dict[str, Any]) -> str:
    """将搜索结果格式化为可读文本。"""
    lines = []
    answer = data.get("answer")
    if answer:
        lines.append(f"AI 摘要：{answer}")
        lines.append("")

    results = data.get("results", [])
    if not results:
        lines.append("（未找到相关结果）")
        return "\n".join(lines)

    for i, r in enumerate(results, 1):
        title = r.get("title", "")
        url = r.get("url", "")
        snippet = r.get("content", "")
        lines.append(f"[{i}] {title}")
        if url:
            lines.append(f"    {url}")
        if snippet:
            lines.append(f"    {snippet[:200]}")
        lines.append("")

    return "\n".join(lines).strip()
