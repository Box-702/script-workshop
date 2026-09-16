# =====================================================================
# research 插件 —— 深度调研工具
#
# 对指定主题进行联网搜索，汇总多个来源的资料。
# =====================================================================

from __future__ import annotations

from langchain_core.tools import tool


@tool
def deep_research(topic: str, focus: str = "") -> str:
    """对指定主题进行深度调研，搜索多个来源并汇总成结构化报告。

    Args:
        topic: 调研主题。
        focus: 调研重点（如：写作技法、市场分析、同类作品）。

    Returns:
        结构化调研报告。
    """
    from app.config import get_settings
    from app.pipeline.search import format_search_results, search_sync

    api_key = get_settings().tavily_api_key
    if not api_key:
        return "（未配置 TAVILY_API_KEY，无法进行深度调研。请在 .env 中设置。）"

    query = topic
    if focus:
        query = f"{topic} {focus}"

    results = []
    # 搜索多个角度
    queries = [query, f"{query} 分析", f"{query} 技巧"]
    for q in queries[:2]:  # 最多 2 次搜索避免超时
        try:
            data = search_sync(q, api_key=api_key, max_results=3)
            results.append(format_search_results(data))
        except Exception as e:
            results.append(f"（搜索失败：{e}）")

    report = f"## 调研报告：{topic}\n\n"
    if focus:
        report += f"**调研重点**：{focus}\n\n"
    for i, r in enumerate(results, 1):
        report += f"### 来源 {i}\n{r}\n\n"

    return report
