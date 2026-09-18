# =====================================================================
# chat —— 对话式编排层（Codex / DSH 风格的工作形式）
#
# conductor.py 把「表单式工作台」升级为「对话式 Agent」：
#   - 上层：绑定工具的 ReAct 小图，负责理解意图并编排动作；
#   - 底层：复用 app/agent 的改编工作流（run_adaptation / resume）；
#   - 后台任务：剧组工具在 app/agent/skills.py 的运行器里执行，进度写回任务面板。
#
# 服务入口：chat_once() / chat_stream()（SSE）/ _handle_resume()（确定性路径）。
# =====================================================================

from .conductor import (
    build_chat_graph,
    build_chat_tools,
    chat_once,
    chat_stream,
    load_history,
    _handle_resume,
)

__all__ = [
    "build_chat_graph",
    "build_chat_tools",
    "chat_once",
    "chat_stream",
    "load_history",
    "_handle_resume",
]
