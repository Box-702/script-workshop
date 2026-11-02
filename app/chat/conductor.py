# =====================================================================
# conductor.py —— 对话编排层（Codex / DSH 风格的工作形式）
#
# 职责只剩「编排」，不再装任何工具实现：
#   - 系统提示（触发器层）：决定该调哪个工具；执行细则外置成
#     app/skills/*（audience: main），由 load_skill 工具按需拉取；
#   - 对话图：LLM 绑定工具 + ToolNode 的 ReAct 循环（单轮重入）；
#   - 轮次服务：历史压缩、事件提取、编造拦截、SSE 流式输出；
#   - 审阅动作（接受 / 拒绝 / 重新生成）走确定性路径，不经过 LLM。
#
# 工具实现在 ./tools/ 包（screenplay / crew / video / memory_tools 四个域）。
#
# 服务入口：
#   chat_once()    一次非流式对话（返回完整回复）；
#   chat_stream()  SSE 流式对话（先推工具轨迹，再流式输出正文）；
#   _handle_resume() 审阅动作走确定性路径。
# =====================================================================

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from .. import memory
from ..agent.tasks import SubAgentRunner
from ..config import Settings
from ..llm import LLM
from ..skills import skill_index
from ..store import Store
from .tools import build_chat_tools as _assemble_tools
from .tools.context import ADAPT_TYPE_LABELS as _ADAPT_TYPE_LABELS
from .tools.context import Collector
from .tools.context import short as _short

log = logging.getLogger(__name__)

# 对话 conductor 的 ReAct 工具循环上限。
MAX_CHAT_TOOL_STEPS = 8

# 对话线程：项目下每个对话（Conversation）一条独立线程；
# 还没有项目的全局对话用固定值 GLOBAL_THREAD。
GLOBAL_THREAD = "global"


class ChatState(TypedDict, total=False):
    """对话式 Agent 的状态：消息流 + 工具产生的结构化载荷。"""

    project_id: str | None
    messages: Annotated[list[AnyMessage], add_messages]
    payloads: list[dict[str, Any]]
    events: list[dict[str, Any]]


# 兼容别名：工具闭包写入的收集器类型现在定义在 tools.context。
_Collector = Collector

# 系统提示分两层：
#   · 触发器（每一轮都要用）留在提示词里——它决定「该调哪个工具」，是路由信息；
#   · 执行细则（步骤顺序、硬门槛、失败怎么处理）外置成 app/skills/*（audience: main），
#     由 load_skill 工具按需拉取。
# 为什么不把触发器也搬进技能：路由每轮都要用，搬出去等于每轮多一次工具往返，
# 模型一旦懒得加载就等于不会做事。技能只负责「进去之后怎么做」。
SYSTEM_PROMPT_TEMPLATE = (
    "你是「问剧」的改编协作者 Agent，工作形式类似 Codex / DSH：通过对话与作者协作，"
    "把一部作品改编成结构化剧本，并持续打磨到成片。\n"
    "所有动作都通过工具完成，不要凭空叙述已经做过的事。\n"
    "\n"
    "【触发 → 动作】\n"
    "· 新建剧本（新建项目 / 新建剧本 / 新开一部）→ create_project；缺标题、改编类型或原文时先问清楚\n"
    "· 生成初稿（生成 / 初稿 / 第一版 / 出剧本）→ generate_script\n"
    "· 改编（改对白 / 改节奏 / 压缩 / 反转 / 口语化）→ run_adaptation，细则见 script-review 技能\n"
    "· 咨询（剧本怎么样 / 这个结尾好不好）→ ask，凭剧本概况与作者风格给有依据的回答\n"
    "· 拆镜头（拆解 / 分镜 / 设计镜头 / 场景拆解）→ breakdown_scenes\n"
    "· 风格指南（视觉风格 / 角色造型 / 画面风格）→ generate_style_guide\n"
    "· 定妆图（参考图 / 人物形象图 / 视觉参考）→ generate_reference_assets\n"
    "· 视频 prompt（生成 prompt / 镜头描述）→ generate_video_prompts\n"
    "· 开始制作（一键制作 / 跑完整流程 / 出一版提示词）→ start_production，"
    "五阶段（剧本→拆解→风格→资产图→提示词）自动跑完，已完成的阶段自动复用\n"
    "· 问进度（到哪了 / 拆好了吗 / 出片了吗 / 合成好了没 / 哪些还没批准）→ get_status，"
    "一次问清，不要凭记忆答，也不要靠猜\n"
    "· 批准提示词 → approve_video_prompts（只在用户明确说「批准」时）\n"
    "· 出片（出片 / 生成视频 / 提交视频）→ submit_videos；重试或重 roll 某镜 → rerun_video\n"
    "· 合成成片（拼成片 / 出完整视频）→ finalize_film\n"
    "· 记忆：系统提示里的「用户记忆」要主动遵循；说「记住… / 以后都…」→ remember；问「你记得什么」→ recall\n"
    "· 长篇小说（原文超过约 1.4 万字）→ 先加载 novel-serial 技能，不要直接 generate_script\n"
    "\n"
    "【可用技能】触发器只告诉你该做哪件事，怎么做的细则在技能里，\n"
    "   · 动手之前先 load_skill：只要本轮要执行某个领域的动作（生成 / 改编 / 拆解 / 提交 / 批准 / 合成），"
    "本轮第一个工具调用就应该是 load_skill，拿完细则再动手；\n"
    "   · 例外：纯只读的盘点（看镜头进度、看哪些提示词待批、查后台任务）可以先查，但一旦要动手，先补上 load_skill；\n"
    "   · 只加载与本轮任务相关的那个技能，不要为求保险全加载一遍；同一轮加载过的不必重复。\n"
    "{skill_index}\n"
    "\n"
    "【硬规矩】\n"
    "1. 汇报以工具返回为准：说「已生成 / 已建成 / 已挑出 / 已提交 / 已出片」之前，本轮必须真的调用过对应工具；"
    "严禁凭对话历史编造版本号（ver_xxx）、场次、进度或任务结果。没调工具就直说还没做，或者先做再说。\n"
    "2. 不替用户做最终决定：接受、拒绝、批准永远由用户发起，你只负责解释影响和引导。\n"
    "3. 剧组任务（拆解 / 风格 / 定妆图 / 提示词）与出片都在后台运行，启动后告知用户可在右栏查看进度。\n"
    "4. 回复简洁、口语化、用简体中文；不确定时先问；不要虚构剧本内容。\n"
    "5. 出片走 MiniMax，需要用户先配置自己的 API Key。\n"
)


def system_prompt() -> str:
    """组装系统提示：静态部分 + 主 Agent 技能目录（渐进披露第一级）。

    目录只有 name + description + when_to_use，正文要靠 load_skill 拉——
    所以技能越多，提示词也只长几行。
    """
    # 用 replace 而不是 str.format：技能描述里可能出现花括号，format 会直接炸。
    return SYSTEM_PROMPT_TEMPLATE.replace("{skill_index}", skill_index("main"))


def main_skill_names() -> set[str]:
    """主 Agent 能加载的技能名（供工具校验与测试断言，避免两处硬编码）。"""
    from .tools.context import main_skill_names as _names

    return _names()


# ---------- 工具集 ----------


def build_chat_tools(
    store: Store,
    llm: LLM,
    collector: _Collector,
    runner: SubAgentRunner | None = None,
) -> list[Any]:
    """构造对话 conductor 的工具集（实现在 ./tools/ 按域拆分）。"""
    return _assemble_tools(store, llm, collector, runner=runner)


# ---------- 对话图 ----------


def build_chat_graph(
    store: Store,
    llm: LLM,
    collector: _Collector,
    runner: SubAgentRunner | None = None,
) -> Any:
    """构建（单轮）对话 conductor 图：LLM 绑定工具 + ToolNode ReAct 循环。"""

    tools = build_chat_tools(store, llm, collector, runner=runner)

    def agent_node(state: ChatState) -> dict[str, Any]:
        if not llm.available:
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "当前没有配置对话模型（在 .env 设置 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 后重启）。"
                            "不过审阅动作（接受 / 拒绝 / 重新生成）仍然可用；"
                            "也可以先用 REST / CLI 方式新建项目并生成初稿。"
                        )
                    )
                ]
            }
        # 工具循环上限：防止模型陷入无限工具调用。
        tool_rounds = sum(1 for m in state.get("messages", []) if isinstance(m, ToolMessage))
        if tool_rounds >= MAX_CHAT_TOOL_STEPS:
            return {
                "messages": [
                    AIMessage(content="这轮工具调用有点多，先停在这里。你可以继续说一句，我接着处理。")
                ]
            }
        resp = llm.chat().bind_tools(tools).invoke(state["messages"])
        return {"messages": [resp]}

    graph = StateGraph(ChatState)
    graph.add_node("chat_agent", agent_node)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "chat_agent")
    graph.add_conditional_edges("chat_agent", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "chat_agent")
    return graph.compile()


# ---------- 历史 ----------


def load_history(store: Store, conversation_id: str | None) -> list[dict[str, Any]]:
    """读取某条会话线程（= Conversation id）的历史消息（用于前端首屏渲染）。"""
    thread = conversation_id or GLOBAL_THREAD
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            # 字段名与前端契约保持一致：payloads（复数）。此前误作 payload（单数），
            # 历史消息里的审阅卡片载荷从未被前端读到。
            "payloads": m.payload,
            "events": m.events,
            "created_at": m.created_at.isoformat(),
        }
        for m in store.list_chat_messages(thread)
    ]


def _history_lc_messages(
    store: Store,
    conversation_id: str | None,
    messages: list[Any] | None = None,
) -> list[AnyMessage]:
    """把对话历史转成 LangChain 消息（user/assistant），供本轮 LLM 参考。

    传 messages（memory.compress_history_if_needed 的最近窗口）用之；否则直接读库。
    assistant 消息会附上压缩的工具轨迹（来自落库 events）：模型对「我上一轮做了
    什么」的记忆不再只靠自己当时的总结，多轮协作不会丢事实。
    """
    if messages is None:
        messages = store.list_chat_messages(conversation_id or GLOBAL_THREAD, limit=60)
    result: list[AnyMessage] = []
    for m in messages:
        if m.role == "user":
            result.append(HumanMessage(content=m.content))
        elif m.role == "assistant" and m.content:
            content = m.content
            traj = _trajectory_note(m.events or [])
            if traj:
                content = f"{traj}\n\n{content}"
            result.append(AIMessage(content=content))
    return result


_TOOL_ACTION_LABELS = {
    "create_project": "新建项目", "generate_script": "生成初稿", "run_adaptation": "发起改编",
    "ask": "查阅剧本内容",
    "breakdown_scenes": "拆解镜头", "generate_style_guide": "生成视觉风格",
    "generate_video_prompts": "撰写镜头提示词", "generate_reference_assets": "生成定妆图",
    "get_status": "查询进度", "approve_video_prompts": "批准提示词",
    "submit_videos": "提交出片",
    "rerun_video": "重roll镜头", "add_asset": "登记素材", "finalize_film": "合成成片",
    "map_novel": "建立章节地图", "propose_arcs": "挑选改编段落",
}


def _trajectory_note(events: list[dict[str, Any]]) -> str:
    """把一轮的工具轨迹压缩成一行事实记录（仅进 LLM 上下文，不展示给用户）。"""
    result_names = {ev.get("name") for ev in events if ev.get("type") == "tool_result"}
    parts: list[str] = []
    for ev in events:
        name = ev.get("name") or ""
        if not name:
            continue
        label = _TOOL_ACTION_LABELS.get(name, name)
        if ev.get("type") == "tool_result":
            summary = _short(ev.get("summary") or "", 80)
            parts.append(f"{label}：{summary}" if summary else label)
        elif ev.get("type") == "tool_call" and name not in result_names:
            parts.append(f"{label}（未返回）")
    if not parts:
        return ""
    deduped: list[str] = []
    for part in parts:
        if part not in deduped:
            deduped.append(part)
    return "［本轮动作］" + "；".join(deduped[:8])


# ---------- 对话服务 ----------


def _prepare_turn(
    store: Store, llm: LLM, runner: SubAgentRunner | None, conversation_id: str | None,
    project_id: str | None, message: str, meta: dict[str, Any] | None,
) -> tuple[_Collector, Any, dict[str, Any]]:
    """准备一轮对话的 collector, graph, input_state。

    上下文组成：系统提示 + 项目概况 + 用户记忆 + [历史滚动摘要] + 最近消息 + 本轮输入。
    长对话由 memory.compress_history_if_needed 压缩旧消息，掐头不再丢事实。
    """
    collector: _Collector = {"project_id": project_id, "payloads": []}
    thread = conversation_id or GLOBAL_THREAD
    collector["conversation_id"] = thread if conversation_id else None
    graph = build_chat_graph(store, llm, collector, runner=runner)
    note = _current_project_note(store, project_id)
    memory_note = memory.format_memory_note(store, project_id=project_id, conversation_id=thread)
    summary, recent = memory.compress_history_if_needed(store, llm, thread)
    history = _history_lc_messages(store, thread, messages=recent)
    if summary:
        history = [SystemMessage(content=f"[此前对话摘要]\n{summary}")] + history
    input_state: dict[str, Any] = {
        "project_id": project_id,
        "messages": [
            SystemMessage(content=system_prompt() + "\n" + note + memory_note),
            *history,
            HumanMessage(content=message),
        ],
    }
    return collector, graph, input_state


def _extract_events(node: str, update: dict[str, Any]) -> list[dict[str, Any]]:
    """从 graph stream chunk 中提取事件列表。"""
    events: list[dict[str, Any]] = []
    msgs = update.get("messages") or []
    if node == "tools":
        for m in msgs:
            if isinstance(m, ToolMessage):
                events.append({
                    "type": "tool_result",
                    "name": m.name or "",
                    "summary": _short(_msg_text(m.content), 160),
                })
    elif node == "chat_agent":
        for m in msgs:
            if isinstance(m, AIMessage) and m.tool_calls:
                for tc in m.tool_calls:
                    events.append({
                        "type": "tool_call",
                        "name": tc.get("name", ""),
                        "args": _short(json.dumps(tc.get("args", {}), ensure_ascii=False), 200),
                    })
    return events


def _finalize_turn(
    store: Store, collector: _Collector, conversation_id: str | None,
    project_id: str | None, message: str, meta: dict[str, Any] | None,
    final_text: str, events: list[dict[str, Any]],
    save_user: bool = True,
) -> dict[str, Any]:
    """保存消息并返回对话结果。

    save_user=False：流式路径已在流开始时保存过用户消息，这里只补 assistant，
    避免同一条用户消息重复入库。
    """
    final_text = _guard_unverified_claims(final_text, events)
    thread = conversation_id or GLOBAL_THREAD
    new_project_id = collector.get("project_id") or project_id
    if save_user:
        store.save_chat_message(thread_id=thread, role="user", content=message, payload=[meta or {}])
    store.save_chat_message(
        thread_id=thread, role="assistant", content=final_text,
        payload=collector.get("payloads") or [], events=events,
    )
    return {
        "reply": final_text,
        "payloads": collector.get("payloads") or [],
        "events": events,
        "project_id": new_project_id,
        "thread_id": thread,
    }


# 声称「已经完成某动作」的结果短语。模型（deepseek 实测）偶尔会模仿历史消息里的
# 「［本轮动作］生成初稿：已生成初稿版本 ver_xxx…」轨迹格式，在没调工具的情况下
# 凭对话记忆编一份结果（假版本号、假进度）。这里做确定性护栏：有结果短语、
# 本轮却没有一条真实的工具返回 → 追加系统更正，防止用户被假版本号误导。
_CLAIM_PATTERNS = (
    "已生成初稿",
    "已改编自",
    "已改编到第",
    "章节地图已建成",
    "个候选故事弧",
    "已提交出片",
    "已批准",
)

_FABRICATED_NOTICE = (
    "\n\n（系统更正：本轮我没有实际调用工具，上面提到的「结果」是不可信的误报。"
    "请再说一次你的需求，我会真正执行、以工具返回为准后再汇报。）"
)

_CORRECTION_PROMPT = (
    "（系统拦截：你上一条回复在没有调用任何工具的情况下报告了「结果」——这是编造，已被系统标记。"
    "请现在真正调用需要的工具完成用户请求；确实做不到就如实说明原因。一切以工具返回为准。）"
)


def _execute_graph_turn(graph: Any, input_state: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """跑一轮 ReAct 图（非流式），返回 (最终回复文本, 工具事件)。"""
    events: list[dict[str, Any]] = []
    final_text = ""
    for chunk in graph.stream(input_state, stream_mode="updates"):
        for node, update in chunk.items():
            events.extend(_extract_events(node, update))
            if node == "chat_agent":
                for m in (update.get("messages") or []):
                    if isinstance(m, AIMessage) and not m.tool_calls and m.content:
                        final_text = _msg_text(m.content)
    return final_text, events


def _claims_unverified(final_text: str, events: list[dict[str, Any]] | None) -> bool:
    """回复里有没有「声称了动作结果、但本轮没有任何真实工具返回」。"""
    text = final_text or ""
    if not text or any(ev.get("type") == "tool_result" for ev in events or []):
        return False
    return any(pattern in text for pattern in _CLAIM_PATTERNS)


def _guard_unverified_claims(final_text: str, events: list[dict[str, Any]]) -> str:
    """回复声称了动作结果、但本轮没有任何真实工具返回时，追加系统更正。"""
    text = final_text or ""
    if _claims_unverified(text, events):
        return text + _FABRICATED_NOTICE
    return text


def _current_project_note(store: Store, project_id: str | None) -> str:
    if not project_id:
        return "当前还没有选定剧本项目。如果用户要新建剧本，调用 create_project；创建后把项目 id 交给用户，并提示已创建。"
    p = store.get_project(project_id)
    if p is None:
        return f"注意：project_id={project_id} 在数据库中不存在，需要时请先创建项目。"
    version = store.latest_version(p)
    version_note = "（尚未生成初稿）" if version is None else f"（当前版本 {version.id}，共 {len(version.script.scenes)} 场）"
    return f"当前剧本项目：《{p.title}》 id={p.id}，类型 {_ADAPT_TYPE_LABELS.get(p.adaptation_type, p.adaptation_type)}{version_note}。"


def _humanized_user_message(meta: dict[str, Any] | None, message: str) -> str:
    """把审阅动作转成可读的用户消息（用于历史展示）。"""
    if not meta or meta.get("intent") != "resume":
        return message
    action = meta.get("action", "accept")
    if action == "accept":
        indexes = meta.get("patch_indexes")
        if indexes:
            return f"接受改编提议（勾选 {len(indexes)} 项）"
        return "接受全部改编提议"
    if action == "reject":
        return "拒绝这次改编提议"
    if action == "regenerate":
        return f"重新生成（反馈：{meta.get('feedback') or '换个思路'}）"
    if action == "edit":
        return "编辑 patch 后接受"
    return message


def _resume_reply(store: Store, result: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """把 resume 结果转成 (助手正文, 结构化载荷)。"""
    status = result.get("status")
    if status == "reviewing":
        payload = {
            "type": "patch_review",
            "run_id": result.get("run_id"),
            "plan": result.get("plan") or [],
            "patch": result.get("patch") or [],
            "steps": result.get("steps") or [],
            "status": "reviewing",
            "review": result.get("review"),
        }
        return "已按你的反馈重新生成提议，请继续审阅下面的卡片。", [payload]
    if status == "applied":
        vid = result.get("new_version_id")
        issues = result.get("validation_issues") or []
        errors = [i for i in issues if i.get("severity") == "error"]
        payload = {
            "type": "version_applied",
            "version_id": vid,
            "fallback": bool(result.get("fallback")),
            "validation_issues": issues,
        }
        note = "（兜底应用：线程状态丢失，基于已落库提议直接应用）" if result.get("fallback") else ""
        return f"✅ 已接受，生成新版本 {vid}，校验问题 {len(errors)} 项。{note}", [payload]
    if status == "rejected":
        return "已拒绝这次改编提议，剧本保持不变。", []
    if status == "failed":
        return f"⚠️ 应用改动失败，未生成新版本：{result.get('error') or '校验未通过'}。", []
    if status == "not_found":
        return "运行记录不存在，可能已过期。", []
    return f"操作完成（状态：{status}）。", []


def _handle_resume(
    store: Store,
    llm: LLM,
    settings: Settings,
    *,
    run_id: str,
    action: str,
    patch_indexes: list[int] | None,
    feedback: str | None,
    patch: list[dict[str, Any]] | None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """确定性处理审阅动作（不经过 LLM），复用底层 resume_agent_run。"""
    from ..agent import runner as agent_svc

    run = store.get_agent_run(run_id)
    if run is None:
        return {"reply": "运行记录不存在，可能已过期。", "payloads": [], "result": {"status": "not_found"}}
    if run.status in ("applied", "rejected"):
        return {
            "reply": f"这条提议已处理过（状态：{run.status}），无需重复操作。",
            "payloads": [],
            "result": {"status": run.status},
        }
    result = agent_svc.resume_agent_run(
        store,
        llm,
        settings,
        run_id=run_id,
        action=action,
        patch_indexes=patch_indexes,
        patch=patch,
        feedback=feedback,
    )
    # 审阅动作沉淀为记忆：接受 → 项目决定；拒绝/重生成带反馈 → 对话反馈。
    memory.learn_from_decision(
        store,
        project_id=run.project_id,
        conversation_id=conversation_id,
        action=action,
        instruction=run.user_prompt,
        feedback=feedback,
        patch_count=len(run.patch) if action == "accept" else 0,
    )
    reply, payloads = _resume_reply(store, result)
    return {"reply": reply, "payloads": payloads, "result": result}


def _run_turn(
    store: Store,
    llm: LLM,
    settings: Settings,
    *,
    conversation_id: str | None,
    project_id: str | None,
    message: str,
    meta: dict[str, Any] | None,
    runner: SubAgentRunner | None = None,
) -> dict[str, Any]:
    """执行一轮对话（非流式），返回 {reply, payloads, events, project_id, thread_id}。"""
    # 审阅动作走确定性路径。
    if meta and meta.get("intent") == "resume":
        handled = _handle_resume(
            store, llm, settings,
            run_id=str(meta.get("run_id") or ""),
            action=str(meta.get("action") or "accept"),
            patch_indexes=meta.get("patch_indexes"),
            feedback=meta.get("feedback"),
            patch=meta.get("patch"),
            conversation_id=conversation_id,
        )
        thread = conversation_id or GLOBAL_THREAD
        store.save_chat_message(thread_id=thread, role="user", content=_humanized_user_message(meta, message), payload=[meta])
        store.save_chat_message(thread_id=thread, role="assistant", content=handled["reply"], payload=handled["payloads"], events=[])
        return {
            "reply": handled["reply"],
            "payloads": handled["payloads"],
            "events": [],
            "project_id": project_id,
            "thread_id": thread,
        }

    collector, graph, input_state = _prepare_turn(
        store, llm, runner,
        conversation_id, project_id, message, meta,
    )
    events: list[dict[str, Any]] = []
    final_text = ""
    try:
        final_text, events = _execute_graph_turn(graph, input_state)
        if _claims_unverified(final_text, events):
            # 编造拦截：模型没调工具就报告了「结果」。带着更正指令重跑一次，
            # 让请求真正落到工具上；重跑仍失败则如实把更正留给 finalize。
            log.warning("对话轮检测到未执行的动作报告，自动重跑一次")
            retry_state = {
                **input_state,
                "messages": list(input_state.get("messages") or []) + [HumanMessage(content=_CORRECTION_PROMPT)],
            }
            retry_text, retry_events = _execute_graph_turn(graph, retry_state)
            if retry_text:
                final_text, events = retry_text, events + retry_events
    except Exception as e:  # noqa: BLE001
        log.warning("对话运行失败：%s", e)
        final_text = f"对话运行出错了：{e}"

    return _finalize_turn(store, collector, conversation_id, project_id, message, meta, final_text, events)


def chat_once(
    store: Store,
    llm: LLM,
    settings: Settings,
    *,
    conversation_id: str | None,
    project_id: str | None,
    message: str,
    meta: dict[str, Any] | None = None,
    runner: SubAgentRunner | None = None,
) -> dict[str, Any]:
    """非流式对话：执行一轮并返回完整结果。"""
    return _run_turn(
        store, llm, settings,
        conversation_id=conversation_id, project_id=project_id, message=message, meta=meta,
        runner=runner,
    )


def chat_stream(
    store: Store,
    llm: LLM,
    settings: Settings,
    *,
    conversation_id: str | None,
    project_id: str | None,
    message: str,
    meta: dict[str, Any] | None = None,
    runner: SubAgentRunner | None = None,
):
    """SSE 流式对话：逐条 yield {event, data} 事件。

    事件序列：tool_call / tool_result（工具轨迹）-> token（正文增量）
    -> done（完整结果）。审阅动作直接返回 done（无 LLM）。
    """
    # 审阅动作：确定性执行，直接产出 done。
    if meta and meta.get("intent") == "resume":
        handled = _handle_resume(
            store, llm, settings,
            run_id=str(meta.get("run_id") or ""),
            action=str(meta.get("action") or "accept"),
            patch_indexes=meta.get("patch_indexes"),
            feedback=meta.get("feedback"),
            patch=meta.get("patch"),
            conversation_id=conversation_id,
        )
        thread = conversation_id or GLOBAL_THREAD
        store.save_chat_message(thread_id=thread, role="user", content=_humanized_user_message(meta, message), payload=[meta])
        store.save_chat_message(thread_id=thread, role="assistant", content=handled["reply"], payload=handled["payloads"], events=[])
        yield {"event": "done", "data": {
            "reply": handled["reply"],
            "payloads": handled["payloads"],
            "events": [],
            "project_id": project_id,
            "thread_id": thread,
        }}
        return

    collector, graph, input_state = _prepare_turn(
        store, llm, runner,
        conversation_id, project_id, message, meta,
    )
    # 用户消息在流开始时就落库：生成中途断开（客户端切走/刷新）或出错时，
    # 至少保住用户说过的话——此前只在整轮结束时统一保存，一旦中断整段丢失。
    thread = conversation_id or GLOBAL_THREAD
    store.save_chat_message(thread_id=thread, role="user", content=message, payload=[meta or {}])
    events: list[dict[str, Any]] = []
    final_text = ""
    last_update_text = ""

    def _pump(state: dict[str, Any]):
        """跑一遍图并实时 yield 事件；结果写回外层 holder。"""
        nonlocal final_text, last_update_text
        text = ""
        for chunk in graph.stream(state, stream_mode=["updates", "messages"]):
            if isinstance(chunk, tuple):
                mode, data = chunk[0], chunk[1]
            else:
                mode, data = chunk.get("type"), chunk.get("data", {})
            if mode == "updates":
                for node, update in (data or {}).items():
                    evts = _extract_events(node, update)
                    for ev in evts:
                        events.append(ev)
                        yield {"event": ev["type"], "data": ev}
                    if node == "chat_agent":
                        for m in (update.get("messages") or []):
                            if isinstance(m, AIMessage) and not m.tool_calls and m.content:
                                last_update_text = _msg_text(m.content)
                                text = _msg_text(m.content)
            elif mode == "messages":
                pairs = data if isinstance(data, list) else [data]
                for pair in pairs:
                    msg_chunk = pair[0] if isinstance(pair, (tuple, list)) else pair
                    # 注意用 isinstance：AIMessageChunk.type 返回 'AIMessageChunk'
                    # 而不是 'ai'，按 type 字符串过滤会把所有 token 块丢弃（实测踩坑）。
                    if not isinstance(msg_chunk, AIMessage):
                        continue
                    # 推理模型的思考增量（DeepSeek/GLM 风格 reasoning_content）：
                    # 只实时展示给用户看，不进入回复正文。
                    reasoning = _reasoning_delta(msg_chunk)
                    if reasoning:
                        yield {"event": "thinking", "data": {"delta": reasoning}}
                    delta = _msg_text(getattr(msg_chunk, "content", None))
                    if delta:
                        text += delta
                        yield {"event": "token", "data": {"delta": delta}}
        final_text = text or last_update_text

    try:
        for sse in _pump(input_state):
            yield sse
        if _claims_unverified(final_text, events):
            # 编造拦截：流式路径同样自动重跑一次（done 事件会用重跑结果覆盖正文）。
            log.warning("对话流式轮检测到未执行的动作报告，自动重跑一次")
            retry_state = {
                **input_state,
                "messages": list(input_state.get("messages") or []) + [HumanMessage(content=_CORRECTION_PROMPT)],
            }
            for sse in _pump(retry_state):
                yield sse
        if not final_text:
            final_text = last_update_text
    except GeneratorExit:
        # 客户端断开（切走会话/刷新页面）：把已生成的部分回复落库，避免全部丢失。
        if final_text:
            store.save_chat_message(
                thread_id=thread, role="assistant", content=final_text,
                payload=collector.get("payloads") or [], events=events,
            )
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("对话流式运行失败：%s", e)
        yield {"event": "error", "data": {"message": str(e)}}
        return

    result = _finalize_turn(
        store, collector, conversation_id, project_id, message, meta, final_text, events,
        save_user=False,
    )
    yield {"event": "done", "data": result}


def _reasoning_delta(msg_chunk: Any) -> str:
    """从流式 AIMessageChunk 中提取思考增量（reasoning_content）。"""
    kw = getattr(msg_chunk, "additional_kwargs", None) or {}
    value = kw.get("reasoning_content") or getattr(msg_chunk, "reasoning_content", None)
    return value if isinstance(value, str) else ""


def _msg_text(content: Any) -> str:
    """把 LangChain 消息 content（可能是 str / 内容块列表）规整为纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                if block.get("type") == "text" and block.get("text"):
                    parts.append(str(block["text"]))
                elif block.get("text"):
                    parts.append(str(block["text"]))
        return "".join(parts)
    return str(content) if content else ""
