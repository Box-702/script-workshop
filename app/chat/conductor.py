# =====================================================================
# chat.py —— 对话式 Agent（Codex / DSH 风格的工作形式）
#
# 这是本次改造的核心：把「表单式」的工作台升级为「对话式」的 agent。
# 用户像和 Codex / DSH 对话一样，通过自然语言完成：
#   新建剧本（新建项目）-> 生成初稿 -> 提出改编需求 -> 审阅 / 接受 / 拒绝
#   -> 导演拆解 -> 视觉风格 -> 视频 Prompt -> 定妆图参考资产。
#
# 架构（两层，底层复用既有工作流）：
#   - 上层：ChatConductor —— 一个绑定了工具的对话式 LangGraph 小图，
#     负责理解用户意图并编排动作（ReAct 循环，工具由 ToolNode 执行）；
#   - 底层：既有 LangGraph 改编工作流（app/agent/graph.py / app/agent/runner.py），
#     由 run_adaptation / resume 工具调用，改动仍走
#     propose -> guard -> review(interrupt) -> apply 的审阅闭环。
#
# 服务入口：
#   chat_once()    一次非流式对话（返回完整回复）；
#   chat_stream()  SSE 流式对话（先推工具轨迹，再流式输出正文）；
#   _handle_resume() 审阅动作（接受/拒绝/重新生成）走确定性路径，不经过 LLM。
# =====================================================================

from __future__ import annotations

import json
import logging
from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from ..agent import runner as agent_svc
from ..config import Settings
from ..domain import normalize_adaptation_type
from .. import memory
from ..pipeline.generation import generate_script as run_generation
from ..pipeline.knowledge import detect_genres, format_author_style
from ..llm import LLM
from ..pipeline.patch import validate_script
from ..store import Project, Store
from ..agent.skills import SubAgentRunner

log = logging.getLogger(__name__)

# 对话 conductor 的 ReAct 工具循环上限。
MAX_CHAT_TOOL_STEPS = 8

# 超过这个字数的原文视为「长篇」：一次剧本生成（12 个切片 × 约 1200 字）
# 只能覆盖开头一小段，必须诚实告知并引导走「建图 → 选段」。
LONG_TEXT_CHARS = 1200 * 12

# 对话线程：项目下每个对话（Conversation）一条独立线程；
# 还没有项目的全局对话用固定值 GLOBAL_THREAD。
GLOBAL_THREAD = "global"


class ChatState(TypedDict, total=False):
    """对话式 Agent 的状态：消息流 + 工具产生的结构化载荷。"""

    project_id: str | None
    messages: Annotated[list[AnyMessage], add_messages]
    payloads: list[dict[str, Any]]
    events: list[dict[str, Any]]


class _Collector(TypedDict, total=False):
    """工具通过闭包写入的运行期收集器（图状态保持干净可序列化）。"""

    project_id: str | None
    conversation_id: str | None
    payloads: list[dict[str, Any]]


SYSTEM_PROMPT = (
    "你是「剧本工坊」的改编协作者 Agent，工作形式类似 Codex / DSH：通过对话与作者协作，"
    "把一部作品改编成结构化剧本，并持续打磨到成片。你的能力边界：\n"
    "1. 新建剧本：用户说「新建项目 / 新建剧本 / 新开一部」时调用 create_project。"
    "缺少标题、改编类型或原文时，先向用户问清楚再创建。\n"
    "2. 生成初稿：用户要求「生成 / 初稿 / 第一版 / 出剧本」时调用 generate_script。\n"
    "3. 改编：用户提出改编需求（改对白、改节奏、改标题、压缩、反转、口语化等）时调用 run_adaptation。"
    "改编会走底层审阅工作流，结果以「审阅卡片」展示，请引导用户接受 / 拒绝 / 重新生成。\n"
    "4. 咨询：用户问「剧本怎么样 / 这个结尾好不好」时调用 get_script_overview 或 ask，"
    "基于剧本概况与作者风格给出有依据的回答，不要凭空编造。\n"
    "5. 导演拆解：用户要求「拆镜头 / 分镜 / 设计镜头 / 场景拆解」时调用 breakdown_scenes，将场景拆解为镜头方案。\n"
    "6. 美术指导：用户要求「风格指南 / 视觉风格 / 角色造型 / 画面风格」时调用 generate_style_guide。\n"
    "7. 摄影指导：用户要求「视频 prompt / 生成 prompt / 镜头描述」时调用 generate_video_prompts，"
    "先生成待人工审阅的 Prompt 草稿，不直接出片。\n"
    "8. 参考资产：用户要求「定妆图 / 参考图 / 人物形象图 / 视觉参考」时调用 generate_reference_assets，"
    "为角色与场景生成定妆图并质检注册，锁跨镜一致性。\n"
    "9. 镜头盘点：用户问「进度 / 哪些镜头还没批准 / 出片了吗」时调用 list_video_shots 或 get_video_jobs，"
    "用事实回答，不要凭记忆猜。\n"
    "10. 批准提示词：用户明确说「批准」时调用 approve_video_prompts。这是用户的正式决定，"
    "只在其明确表态时执行，绝不代替用户批准。\n"
    "11. 出片：用户说「出片 / 生成视频 / 提交视频」时调用 submit_videos；"
    "用户要求「重试 / 重roll 某个镜头」时调用 rerun_video。\n"
    "12. 后台任务：用户问「拆好了吗 / 好了没」时调用 check_background_tasks 查询真实状态，不要凭记忆回答。\n"
    "13. 记忆：系统提示里的「用户记忆」要主动遵循；用户说「记住… / 以后都…」时调用 remember；"
    "用户问「你记得什么」时调用 recall。用户的长期习惯值得记下来时也可以主动建议保存。\n"
    "14. 长篇小说：原文超过约 1.5 万字时不要直接生成初稿（只会覆盖开头一小段）。"
    "先调用 map_novel 建章节地图，再用 propose_arcs 提候选故事弧，用户选定章节范围后"
    "调用 generate_script(from_chapter, to_chapter) 按段生成；用户说「继续改编下一段」时"
    "不要再提候选弧，直接调用 generate_script 且章节参数留空（自动从已改编进度续接约 1.2 万字），"
    "前情提领会自动带上，生成后汇报本次范围与连载进度。\n"
    "15. 汇报以工具返回为准：说「已生成 / 已建成 / 已挑出 / 已提交」之前，本轮必须真的调用过"
    "对应工具；严禁凭对话历史编造版本号（ver_xxx）、场次、进度或任务结果。"
    "没调工具就直说还没做，或者先做再说。\n"
    "行为准则：回复简洁、口语化、用简体中文；不确定时先问；不要虚构剧本内容；"
    "不要替用户做最终决定，审阅与落版决定永远交给用户。"
    "剧组任务（5-8）会在后台运行，启动后告知用户可在右栏查看进度；"
    "出片（11）走 MiniMax，需要用户先配置自己的 API Key。"
)

# 改编类型 -> 中文名，用于提示模型填参数。
_ADAPT_TYPE_LABELS = {
    "short_drama": "短剧",
    "film": "电影",
    "series": "剧集",
    "stage": "舞台剧",
    "other": "自定义",
}

# 记忆类型 -> 中文名（recall 工具的展示与 remember 的确认共用）。
_MEMORY_KIND_LABELS = {"preference": "用户偏好", "decision": "项目决定", "feedback": "对话反馈"}


# ---------- 工具集 ----------


def build_chat_tools(
    store: Store,
    llm: LLM,
    collector: _Collector,
    runner: SubAgentRunner | None = None,
) -> list[Any]:
    """构造对话 conductor 的工具集（无 RAG 版）。"""
    from ..config import get_settings
    settings = get_settings()

    def _project(project_id: str) -> Project | None:
        p = store.get_project(project_id)
        if p is None:
            raise ValueError(f"项目不存在：{project_id}")
        collector["project_id"] = project_id
        return p

    def _overview_text(project: Project) -> str:
        version = store.latest_version(project)
        if version is None:
            return "（还没有生成剧本版本，可以先让我生成初稿）"
        s = version.script
        scenes = "; ".join(f"{sc.id}:{sc.title}" for sc in s.scenes[:12])
        chars = "; ".join(c.name for c in s.characters[:12])
        return (
            f"标题《{s.title}》\n梗概：{s.logline}\n主题：{'、'.join(s.themes) or '未填写'}\n"
            f"人物：{chars}\n场景：{scenes}"
        )

    @tool
    def create_project(title: str, adaptation_type: str, raw_text: str) -> str:
        """新建一部剧本项目。参数：title=剧名，adaptation_type=改编类型（short_drama 短剧 / film 电影 / series 剧集 / stage 舞台剧 / other 自定义），raw_text=原著或故事原文。"""
        name = normalize_adaptation_type(adaptation_type)
        p = store.create_project(
            title=title.strip(),
            adaptation_type=name,
            language="zh-CN",
            raw_text=(raw_text or "").strip(),
        )
        collector["project_id"] = p.id
        label = _ADAPT_TYPE_LABELS.get(name, name)
        # 作者风格只做规则画像（无网络调用），避免对话轮次被额外 LLM 调用拖慢
        try:
            from ..pipeline.knowledge import extract_author_style
            style = extract_author_style(raw_text)
            notes = f"作者风格：{style.get('summary', '')}"
            store.set_project_notes(p.id, notes)
        except Exception:
            pass
        genres = detect_genres(raw_text, top=2)
        reply = (
            f"已创建剧本项目《{p.title}》（id={p.id}，类型：{label}，题材：{'、'.join(genres)}）。"
        )
        # 诚实化：超长原文一次生成只覆盖开头一小段，必须说清楚并给出路。
        from ..pipeline.chunking import chapter_spans
        text_len = len((raw_text or "").strip())
        n_chapters = len(chapter_spans((raw_text or "").strip()))
        if text_len > LONG_TEXT_CHARS:
            w = text_len / 10000
            chapter_tip = f"、共识别出 {n_chapters} 章" if n_chapters > 1 else ""
            reply += (
                f"注意：原文约 {w:.1f} 万字{chapter_tip}，直接生成初稿只会改编开头约 1.4 万字。"
                f"建议先让我「建立章节地图」，再从里面挑一段最适合改编的故事弧。"
            )
        reply += "需要我现在生成剧本初稿吗？"
        return reply

    @tool
    def map_novel(project_id: str, rebuild: str = "") -> str:
        """为长篇原文建立章节地图：逐章摘要 + 出场人物，作为「选段改编」的依据。超过约 1.5 万字的小说建议先建图。后台运行（章节数多时要几分钟）。已有地图时会拒绝重复建图，除非 rebuild=true（用户明确要求重建）。参数：project_id=项目 id；rebuild=传 "true" 强制重建。"""
        p = _project(project_id)
        text = (p.raw_text or "").strip()
        if len(text) <= LONG_TEXT_CHARS:
            return f"原文只有约 {len(text) / 10000:.1f} 万字，不算长篇，直接「生成初稿」就能全部覆盖，不需要建图。"
        existing = len((p.novel_map or {}).get("chapters") or [])
        if existing and str(rebuild).lower() != "true":
            return (
                f"这本书已经有章节地图（{existing} 章），不用重建，直接说「挑一段改编」就能选段；"
                f"只有当原文替换过或摘要有问题时才需要重建（那时传 rebuild=true）。"
            )
        if not llm.available:
            return "建立章节地图需要对话模型（当前不可用），请先在设置里配置模型。"

        def _run(task):
            from ..pipeline.novel_map import build_novel_map
            m = build_novel_map(
                text, llm,
                on_progress=(lambda msg: runner.update_step(task.id, msg, "running")) if runner else None,
            )
            store.set_novel_map(p.id, m)
            n = len(m.get("chapters") or [])
            kind = "伪章节（原文没有章节标题，按长度切分）" if m.get("pseudo") else "章"
            return f"章节地图已建成：共 {n} {kind}，可从中挑选改编段落。"

        if runner:
            task_id = runner.start("章节地图", _run)
            collector["payloads"].append({
                "type": "sub_agent_started", "task_id": task_id, "name": "章节地图", "project_id": p.id,
            })
            return "正在为全书逐章建立地图（摘要每章剧情与出场人物），完成后告诉我可以「挑一段改编」。"
        m = _run(type("_T", (), {"id": "local"})())
        return m

    @tool
    def propose_arcs(project_id: str, from_chapter: str = "") -> str:
        """基于章节地图提出 2-3 个候选改编故事弧（章节范围+戏剧钩子），由用户选定后再生成剧本。需要先完成「建立章节地图」。参数：project_id=项目 id；from_chapter=起始章号（可选，默认从已改编进度之后开始）。"""
        p = _project(project_id)
        m = p.novel_map
        chapters = m.get("chapters") or []
        if not chapters:
            return "还没有章节地图。请先让我「建立章节地图」，再挑选改编段落。"
        if not llm.available:
            return "挑选故事弧需要对话模型（当前不可用）。"
        from ..pipeline.novel_map import ARCS_PROMPT, arcs_context, parse_arcs

        try:
            start = int(from_chapter) if str(from_chapter).strip() else (p.adapted_until + 1 if p.adapted_until else 1)
        except ValueError:
            return "from_chapter 需要是章号数字。"
        start = max(1, min(start, len(chapters)))
        ctx = arcs_context(m, from_chapter=start)
        resp = llm.chat().invoke([
            {"role": "system", "content": ARCS_PROMPT},
            {"role": "user", "content": f"改编范围：第 {start} 章到第 {len(chapters)} 章。\n\n章节地图：\n{ctx}"},
        ])
        raw = getattr(resp, "content", "") or ""
        if isinstance(raw, list):
            raw = " ".join(b.get("text", "") for b in raw if isinstance(b, dict) and b.get("type") == "text")
        try:
            arcs = parse_arcs(str(raw))
        except ValueError:
            return "这次没能从章节地图里提炼出合适的故事弧，可以让我再试一次，或直接告诉我你想改编的章节范围。"
        lines = []
        for i, arc in enumerate(arcs, 1):
            line = f"{i}. 「{arc['title']}」第 {arc['from']}–{arc['to']} 章：{arc['hook']}"
            if arc["why"]:
                line += f"（{arc['why']}）"
            lines.append(line)
        return (
            f"从第 {start} 章起共 {len(chapters)} 章，为你挑出 {len(arcs)} 个候选故事弧：\n"
            + "\n".join(lines)
            + "\n告诉我选哪个（如「选 1」），或直接给我章节范围（如「改编第 5 到 16 章」），我就开始生成剧本。"
        )

    @tool
    def generate_script(project_id: str, from_chapter: str = "", to_chapter: str = "") -> str:
        """为指定项目生成剧本初稿（生成流水线：故事圣经 -> 场景/节拍）。

        长篇建议配合章节地图按章选段：from_chapter/to_chapter=章号（1 起，含两端）。
        有章节地图时不传 to_chapter 会按一次生成的容量（约 1.2 万字）自动续接；
        用户说「继续改编下一段」时直接调用本工具、章节参数留空即可，从进度接续并自动带前情提要。
        参数：project_id=项目 id。
        """
        p = _project(project_id)
        raw = p.raw_text or ""
        span_label = ""
        prior_context = ""
        text = raw
        if str(from_chapter).strip() or str(to_chapter).strip() or (p.novel_map.get("chapters") if p.novel_map else None):
            from ..pipeline.chunking import slice_by_chapter
            from ..pipeline.novel_map import next_to_chapter, previous_context

            try:
                a = int(from_chapter) if str(from_chapter).strip() else (p.adapted_until + 1 if p.adapted_until else 1)
                if str(to_chapter).strip():
                    b = int(to_chapter)
                elif p.novel_map.get("chapters"):
                    b = next_to_chapter(p.novel_map, a)  # 按容量自动续接，不再默认切到全书末尾
                else:
                    b = 0
                text, span_label, b = slice_by_chapter(raw, a, b or 10**9)
            except ValueError as e:
                return f"选段失败：{e}"
            if a > 1:
                prior_context = previous_context(p.novel_map, a - 1)
        script, artifacts = run_generation(
            llm,
            settings,
            title=p.title,
            raw_text=text,
            adaptation_type=p.adaptation_type,
            language=p.language,
            prior_context=prior_context,
        )
        version_label = f"初始生成（{span_label}）" if span_label else "初始生成"
        version = store.create_version(
            p,
            script,
            source_type="generation",
            label=version_label,
            notes=f"生成模式：{artifacts.get('mode', 'n/a')}",
            parent_version_id=p.current_version_id,
            set_current=True,
        )
        if span_label:
            store.set_adapted_until(p.id, b)
        issues = [i for i in validate_script(script) if i.severity == "error"]
        # 覆盖诚实化：说清这次改编的原文范围。
        from ..pipeline.chunking import chapter_spans
        n_chapters = len(chapter_spans(raw))
        if span_label:
            coverage = f"本次改编自{span_label}（约 {len(text) / 10000:.1f} 万字）"
            if len(text) > LONG_TEXT_CHARS:
                coverage += (
                    f"。注意：这个选段超过一次生成的容量（约 {LONG_TEXT_CHARS / 10000:.1f} 万字），"
                    f"初稿只覆盖了选段开头，建议把章节范围切小（单次不超过 2 章左右）再分别生成"
                )
            if p.adapted_until:
                total = len((p.novel_map.get('chapters') or [])) or n_chapters
                coverage += f"，连载进度：已改编到第 {p.adapted_until} 章（全书 {total} 章）"
        elif len(raw) > LONG_TEXT_CHARS:
            coverage = (
                f"注意：原文约 {len(raw) / 10000:.1f} 万字，本次初稿只基于开头约 {len(text) / 10000:.1f} 万字。"
                f"要改编后面的内容，先让我「建立章节地图」再选段。"
            )
        else:
            coverage = f"原文约 {len(raw) / 10000:.1f} 万字，已全部纳入改编"
        tail = f"（有 {len(issues)} 处结构问题需注意）" if issues else ""
        return (
            f"已生成初稿版本 {version.id}（模式：{artifacts.get('mode')}）："
            f"共 {len(script.scenes)} 场，{len(script.characters)} 个人物，"
            f"{len(script.locations)} 个地点。{coverage}。梗概：{script.logline}。{tail}"
            f"你可以说「把对白改口语一点」「节奏改紧凑」等让我开始改编。"
        )

    @tool
    def run_adaptation(project_id: str, instruction: str) -> str:
        """对指定项目发起一次改编：走底层 LangGraph 审阅工作流，产出可逐条接受的结构化提议。参数：project_id=项目 id，instruction=改编需求描述。"""
        p = _project(project_id)
        base_version = store.latest_version(p)
        if base_version is None:
            # 没有初稿时先自动生成，保证链路闭环。
            script, artifacts = run_generation(
                llm,
                settings,
                title=p.title,
                raw_text=p.raw_text,
                adaptation_type=p.adaptation_type,
                language=p.language,
            )
            base_version = store.create_version(
                p, script, source_type="generation", label="初始生成",
                notes=f"生成模式：{artifacts.get('mode', 'n/a')}", set_current=True,
            )
        result = agent_svc.start_agent_run(
            store,
            llm,
            settings,
            project=p,
            base_version=base_version,
            instruction=instruction,
            scene_ids=[],
        )
        collector["payloads"].append(
            {
                "type": "patch_review",
                "run_id": result.get("run_id"),
                "project_id": p.id,
                "plan": result.get("plan") or [],
                "patch": result.get("patch") or [],
                "steps": result.get("steps") or [],
                "status": result.get("status"),
                "error": result.get("error"),
                "review": result.get("review"),  # 评审打分 + 一致性保障结果
            }
        )
        if result.get("error"):
            return (
                f"已生成改编提议（{len(result.get('patch') or [])} 项操作），"
                f"但模型调用出现异常，已保留说明性建议：{result['error']}"
            )
        return (
            f"已完成改编分析，共 {len(result.get('patch') or [])} 项改动建议（"
            f"计划：{'；'.join((result.get('plan') or [])[:3])}）。"
            f"请审阅下面的卡片：可勾选部分接受、接受全部、拒绝，或给我反馈重新生成。"
        )

    @tool
    def get_script_overview(project_id: str) -> str:
        """查看当前剧本的概况（标题、梗概、主题、人物、场景清单）。参数：project_id=项目 id。"""
        p = _project(project_id)
        return _overview_text(p)

    @tool
    def ask(project_id: str, question: str) -> str:
        """就剧本 / 改编创作提问（参考剧本概况与作者风格），给出有依据的回答。参数：project_id=项目 id，question=问题。"""
        p = _project(project_id)
        overview = _overview_text(p)
        style_text = format_author_style(p.raw_text)

        if llm.available:
            try:
                resp = llm.chat().invoke(
                    [
                        SystemMessage(
                            content=(
                                "你是剧本创作顾问。基于下面提供的剧本概况和作者风格回答问题；"
                                "回答要具体、可操作，不要编造。"
                            )
                        ),
                        HumanMessage(
                            content=(
                                f"剧本概况：\n{overview}\n\n"
                                f"作者风格：\n{style_text}\n\n"
                                f"用户问题：{question}"
                            )
                        ),
                    ]
                )
                return str(resp.content or "").strip()
            except Exception as e:  # noqa: BLE001
                log.warning("ask 组装回答失败：%s", e)
        return f"（未配置模型，以下为直接信息）\n{style_text}"

    # ---- 导演组工具 ----

    @tool
    def breakdown_scenes(project_id: str, scene_ids: str = "") -> str:
        """启动导演 Agent，将剧本场景拆解为镜头方案。分析每场戏的戏剧目标和节奏需求，设计镜头类型、运镜、光线。在后台运行。参数：project_id=项目 id，scene_ids=场景 id 列表（逗号分隔，可选，不填则拆解全部场景）。"""
        p = _project(project_id)
        version = store.latest_version(p)
        if version is None:
            return "还没有剧本版本，请先生成初稿。"
        script = version.script
        sids = [s.strip() for s in scene_ids.split(",") if s.strip()] or None

        def _run(task):
            from ..crew.director import run_director
            result = run_director(llm, script, scene_ids=sids)
            if result.success:
                # 保存到 video_versions
                shots_data = []
                for bd in result.data:
                    for shot in bd.shots:
                        shots_data.append(shot.model_dump())
                store.create_video_version(
                    project_id=p.id,
                    shots=shots_data,
                    source_type="agent",
                    label="导演拆解",
                    notes=result.summary,
                )
                # 同时保存 breakdown 到 script_version
                breakdown_data = [bd.model_dump() for bd in result.data]
                store.set_version_breakdown(version.id, breakdown_data)
            return result.summary

        task_id = runner.start("导演场景拆解", _run) if runner else "local"
        collector["payloads"].append({
            "type": "sub_agent_started",
            "task_id": task_id,
            "name": "导演场景拆解",
            "project_id": p.id,
        })
        scope = f"{len(sids)} 个指定场景" if sids else "全部场景"
        return f"正在把{scope}拆解成镜头方案，完成后会出现在右侧「视频工作台」。"

    @tool
    def generate_style_guide(project_id: str, director_notes: str = "") -> str:
        """启动美术指导 Agent，生成视觉风格指南。包括色彩方案、光线风格、摄影风格、角色造型、环境描述。在后台运行。参数：project_id=项目 id，director_notes=导演额外创意意图（可选）。"""
        p = _project(project_id)
        version = store.latest_version(p)
        if version is None:
            return "还没有剧本版本，请先生成初稿。"
        script = version.script

        def _run(task):
            from ..crew.art_director import run_art_director
            from ..crew.dp import language_for
            # 视觉锚的语言必须与下游提示词构建一致：从已启用的视频 provider 推断。
            lang = "zh"
            try:
                rows = [r for r in store.list_api_providers(kind="video") if r.enabled]
                if rows:
                    lang = language_for(rows[0].name, script.language)
            except Exception:  # noqa: BLE001
                pass
            result = run_art_director(llm, script, director_notes=director_notes, language=lang)
            if result.success:
                # 风格指南（含角色造型 / 环境描述）随项目持久化，是下游视觉锚的唯一来源。
                store.set_video_style(p.id, result.data.model_dump())
            return result.summary

        task_id = runner.start("美术指导", _run) if runner else "local"
        collector["payloads"].append({
            "type": "sub_agent_started",
            "task_id": task_id,
            "name": "美术指导",
            "project_id": p.id,
        })
        return "正在统一全片的视觉风格（人物造型、环境光线），完成后会自动应用到每个镜头。"

    @tool
    def generate_video_prompts(project_id: str) -> str:
        """启动摄影指导 Agent，为镜头方案中的每个镜头生成视频生成 Prompt（英文）。需要先完成导演场景拆解。在后台运行。参数：project_id=项目 id。"""
        p = _project(project_id)
        version = store.latest_version(p)
        if version is None:
            return "还没有剧本版本，请先生成初稿。"
        script = version.script

        # 读取已有的 breakdown 与风格指南（两者都随项目/版本持久化）
        breakdowns_data = store.get_version_breakdown(version.id)
        if not breakdowns_data:
            return "还没有完成导演场景拆解，请先运行「导演拆解」（breakdown_scenes）。"
        style_data = store.get_video_style(p.id)

        # 目标视频 provider：决定提示词方言（中文/英文）与单镜时长约束
        target_provider, provider_label, max_duration = "", "", 0.0
        try:
            from ..video import get_registry
            rows = [r for r in store.list_api_providers(kind="video") if r.enabled]
            if rows:
                target_provider = rows[0].name
                prov = get_registry().get_provider(
                    target_provider, api_key=rows[0].api_key, base_url=rows[0].base_url
                )
                if prov:
                    provider_label = prov.label
                    max_duration = prov.max_duration_sec
        except Exception:  # noqa: BLE001
            pass

        def _run(task):
            from ..crew.dp import run_dp
            from ..domain import SceneBreakdown, StyleGuide
            bds = [SceneBreakdown.model_validate(b) for b in breakdowns_data]
            sg = StyleGuide.model_validate(style_data) if style_data else None
            result = run_dp(
                llm, script, breakdowns=bds, style_guide=sg,
                target_provider=target_provider, provider_label=provider_label,
                max_duration=max_duration,
            )
            if result.success:
                # 摄影指导只提交草稿，人工批准前不得进入视频任务队列。
                shots_data = [
                    {
                        **s.model_dump(),
                        "prompt_status": "needs_review",
                        "prompt_review_note": "",
                    }
                    for s in result.data
                ]
                previous = p.current_video_version_id and store.get_video_version(
                    p.current_video_version_id
                )
                store.create_video_version(
                    project_id=p.id,
                    shots=shots_data,
                    source_type="agent",
                    label="视频提示词待审阅",
                    notes=f"{result.summary}；生成后需逐镜人工批准，才能提交视频任务。",
                    parent_version_id=previous.id if previous else None,
                )
            return result.summary

        task_id = runner.start("摄影指导", _run) if runner else "local"
        collector["payloads"].append({
            "type": "sub_agent_started",
            "task_id": task_id,
            "name": "摄影指导",
            "project_id": p.id,
        })
        return (
            "正在为每个镜头撰写视频提示词，完成后请在右侧「视频工作台」逐镜确认，"
            "确认后才会开始出片。"
        )

    @tool
    def generate_reference_assets(project_id: str) -> str:
        """启动参考资产流水线：为角色与场景生成定妆图，用视觉模型质检合格后注册为全局视觉参考，供视频生成锁住跨镜一致性。在后台运行。参数：project_id=项目 id。"""
        p = _project(project_id)
        version = store.latest_version(p)
        if version is None:
            return "还没有剧本版本，请先生成初稿。"
        script = version.script

        def _run(task):
            from ..domain import StyleGuide
            from ..media.refs import build_reference_assets

            style_raw = store.get_video_style(p.id)
            guide = StyleGuide.model_validate(style_raw) if style_raw else None

            def _progress(msg: str) -> None:
                if runner:
                    runner.update_step(task.id, msg, "running")

            refs = build_reference_assets(
                script, guide,
                on_progress=_progress,
            )
            # 写回风格指南：reference_images 与风格锚一起持久化（无需改数据库表）
            store.merge_video_style(p.id, {"reference_images": refs})
            return f"已生成并注册 {len(refs)} 张参考资产：{'、'.join(refs)}"

        task_id = runner.start("参考资产", _run) if runner else "local"
        collector["payloads"].append({
            "type": "sub_agent_started",
            "task_id": task_id,
            "name": "参考资产",
            "project_id": p.id,
        })
        return (
            "正在为角色与场景生成定妆图（会自动做质量把关）。"
            "完成后镜头会自动带上这些参考图，用于锁住跨镜头的角色与场景一致。"
        )

    # ---- 视频侧：让「批准 → 出片 → 查进度 → 重roll」也能在对话里完成 ----

    def _latest_video_version(p: Project):
        versions = sorted(store.list_video_versions(p.id), key=lambda v: v.created_at)
        return versions[-1] if versions else None

    _PROMPT_STATUS_LABELS = {"draft": "待审", "needs_revision": "需修改", "approved": "已批准"}
    _JOB_STATUS_LABELS = {
        "pending": "排队中", "queued": "排队中", "generating": "生成中",
        "succeeded": "已出片", "failed": "失败", "cancelled": "已取消",
    }

    def _latest_job_by_shot(project_id: str) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for j in sorted(store.list_video_jobs(project_id), key=lambda x: x.created_at):
            latest[j.shot_id] = j  # 后写的覆盖先写的，留下每个镜头最新一次任务
        return latest

    @tool
    def list_video_shots(project_id: str) -> str:
        """盘点镜头与出片进度：列出每个镜头的提示词审阅状态（待审/需修改/已批准）和成片状态。用户问「镜头进度 / 哪些还没批准 / 出片了吗」时先调用这个。参数：project_id=项目 id。"""
        p = _project(project_id)
        v = _latest_video_version(p)
        if v is None or not v.shots:
            return "还没有镜头方案——需要先「拆解镜头」。"
        jobs = _latest_job_by_shot(p.id)
        lines = []
        for s in v.shots:
            if not isinstance(s, dict) or not s.get("id"):
                continue
            sid = s["id"]
            prompt = _PROMPT_STATUS_LABELS.get(s.get("prompt_status") or "draft", "待审")
            job = jobs.get(sid)
            video = _JOB_STATUS_LABELS.get(job.status, "") if job else ""
            if job is not None and job.status == "failed" and getattr(job, "error_message", None):
                video += f"（{job.error_message}）"
            subject = s.get("subject") or ""
            lines.append(f"- {sid}{'（' + subject + '）' if subject else ''}：提示词{prompt}"
                         + (f"，视频{video}" if video else ""))
        n_approved = sum(1 for s in v.shots if isinstance(s, dict) and s.get("prompt_status") == "approved")
        head = f"共 {len(lines)} 个镜头，已批准 {n_approved} 个：\n"
        return head + "\n".join(lines)

    @tool
    def approve_video_prompts(project_id: str, shot_ids: str = "") -> str:
        """批准镜头的提示词，使其可以提交视频生成（批准后生成新的镜头版本，可回滚）。注意：这是用户的正式决定，只在用户明确说「批准」时才调用。参数：project_id=项目 id；shot_ids=镜头 id 列表（逗号分隔），留空=批准全部有待审提示词的镜头。"""
        p = _project(project_id)
        current = _latest_video_version(p)
        if current is None or not current.shots:
            return "还没有镜头方案——需要先「拆解镜头」再「撰写镜头提示词」。"
        from ..crew.dramaturgy import refresh_prompt_audits

        wanted = {s.strip() for s in shot_ids.split(",") if s.strip()}
        shots = [dict(s) for s in current.shots if isinstance(s, dict)]
        targets = [
            s for s in shots
            if s.get("id") and s.get("video_prompt")
            and (not wanted or s["id"] in wanted)
            and s.get("prompt_status") != "approved"
        ]
        if not targets:
            return "没有可批准的镜头（可能都已批准，或选中镜头没有提示词）。"
        for s in targets:
            s["prompt_status"] = "approved"
            s["prompt_review_note"] = "对话中批准"
        refresh_prompt_audits(shots)
        version = store.create_video_version(
            project_id=p.id, shots=shots, style_guide=current.style_guide,
            source_type="manual", label="对话中批准镜头提示词",
            notes=None, parent_version_id=current.id,
        )
        names = "、".join(s["id"] for s in targets)
        return f"已批准 {len(targets)} 个镜头的提示词（{names}），新镜头版本 {version.id}。现在可以说「出片」来提交视频生成。"

    @tool
    def submit_videos(project_id: str, shot_ids: str = "") -> str:
        """提交视频生成：为提示词已批准的镜头启动批量出片（串行推进，前一镜成片自动作为后一镜的接力参考）。参数：project_id=项目 id；shot_ids 可选（逗号分隔只出指定镜头），留空=全部已批准的镜头。"""
        p = _project(project_id)
        v = _latest_video_version(p)
        if v is None or not v.shots:
            return "还没有镜头方案：请先「拆解镜头」「撰写镜头提示词」并批准。"
        wanted = {s.strip() for s in shot_ids.split(",") if s.strip()}
        approved = [
            s["id"] for s in v.shots
            if isinstance(s, dict) and s.get("id") and s.get("video_prompt")
            and s.get("prompt_status") == "approved" and (not wanted or s["id"] in wanted)
        ]
        if not approved:
            return "没有可提交的镜头：提示词需要先经过人工批准。可以说「批准全部提示词」，或先看看镜头清单。"
        from ..api.video import _create_and_submit_job, generate_batch
        from ..api.schemas import VideoJobCreate

        try:
            if wanted:
                # 指定镜头：逐镜直接提交（接力链主要服务整片连拍，这里不强求）。
                for sid in approved:
                    shot = next(s for s in v.shots if isinstance(s, dict) and s.get("id") == sid)
                    _create_and_submit_job(p.id, VideoJobCreate(
                        shot_id=sid, provider="minimax", model="default",
                        prompt=shot.get("video_prompt") or "", version_id=v.id,
                    ))
                return f"已提交 {len(approved)} 个指定镜头的视频生成，稍后可问我进度。"
            # 整片：走批次（串行推进，前一镜成片自动作为后一镜接力参考）。
            from ..api.video import BatchCreateRequest
            batch = generate_batch(p.id, BatchCreateRequest(version_id=v.id))
        except Exception as e:  # noqa: BLE001  FastAPI HTTPException 也走这里，转成用户可读文本
            detail = getattr(e, "detail", None) or str(e)
            return f"提交视频生成失败：{detail}"
        if batch.get("status") == "failed":
            return f"批次启动失败：{batch.get('error') or '未知原因'}"
        collector["payloads"].append({
            "type": "batch_started", "batch_id": batch.get("id"), "project_id": p.id,
        })
        total = batch.get("total") or len(approved)
        return f"已开始出片：共 {total} 个镜头会按顺序生成，前一镜完成后自动作为后一镜的参考以保持连贯。可以随时问我「出片进度」。"

    @tool
    def get_video_jobs(project_id: str) -> str:
        """查询视频生成任务的最新状态（排队/生成中/已出片/失败原因）。用户问「出片了吗 / 生成得怎么样」时调用。参数：project_id=项目 id。"""
        p = _project(project_id)
        jobs = store.list_video_jobs(p.id)
        if not jobs:
            return "还没有提交过视频生成任务。"
        latest = _latest_job_by_shot(p.id)
        lines = []
        for sid, j in latest.items():
            label = _JOB_STATUS_LABELS.get(j.status, j.status)
            suffix = f"（{j.error_message}）" if j.status == "failed" and getattr(j, "error_message", None) else ""
            lines.append(f"- {sid}：{label}{suffix}")
        done = sum(1 for j in latest.values() if j.status == "succeeded")
        failed = sum(1 for j in latest.values() if j.status == "failed")
        head = f"各镜头最新状态（{done} 个已出片，{failed} 个失败）：\n"
        return head + "\n".join(lines)

    @tool
    def rerun_video(project_id: str, shot_id: str) -> str:
        """重新生成某个镜头的视频：任务失败时重试；对成片不满意时重新出一版。参数：project_id=项目 id；shot_id=镜头 id（形如 shot_scene001_001）。"""
        p = _project(project_id)
        shot_id = shot_id.strip()
        v = _latest_video_version(p)
        shot = next(
            (s for s in (v.shots if v else []) if isinstance(s, dict) and s.get("id") == shot_id),
            None,
        )
        if shot is None:
            return f"没有找到镜头 {shot_id}，可以先查镜头清单确认 id。"
        job = _latest_job_by_shot(p.id).get(shot_id)
        from ..api.schemas import VideoJobCreate
        from ..api.video import _create_and_submit_job, retry_video_job

        try:
            if job is not None and job.status in ("failed", "cancelled"):
                retry_video_job(job.id)
                return f"已重新排队镜头 {shot_id}（之前失败/取消的任务重试）。"
            if not shot.get("video_prompt") or shot.get("prompt_status") != "approved":
                return "该镜头的提示词还没批准，重跑前需要先批准。"
            _create_and_submit_job(p.id, VideoJobCreate(
                shot_id=shot_id, provider="minimax", model="default",
                prompt=shot.get("video_prompt") or "", version_id=v.id,
            ))
            return f"已提交镜头 {shot_id} 的重新生成，稍后可问我进度。"
        except Exception as e:  # noqa: BLE001
            detail = getattr(e, "detail", None) or str(e)
            return f"重跑失败：{detail}"

    @tool
    def add_asset(project_id: str, url: str, name: str = "") -> str:
        """把一个公网素材直链（参考视频等，http/https）登记进项目素材库，供视频生成挂参考。用户在对话里发来链接并说「当参考/加进素材」时调用。参数：project_id=项目 id，url=公网直链，name=可选的名字。"""
        p = _project(project_id)
        url = (url or "").strip()
        if not url.startswith(("http://", "https://")):
            return "需要 http(s) 开头的公网直链；本地文件请用左上角「＋」上传。"
        name = (name or "").strip() or url.rsplit("/", 1)[-1] or "外部视频"
        asset = store.add_asset(p.id, kind="video", name=name, source="url", url=url)
        return f"已登记素材「{asset.name}」，生成视频时可以在镜头提示词里把它挂为参考视频。"

    @tool
    def finalize_film(project_id: str, subtitles: bool = True, dubbing: bool = True) -> str:
        """把已生成成功的镜头合成为完整成片（拼装 + 台词配音 + 台词字幕，后台执行）。用户说「合成成片 / 拼成片 / 出完整视频」时调用。参数：project_id=项目 id，subtitles=是否烧台词字幕（默认开），dubbing=是否配台词语音（默认开，无台词或未配语音 key 时自动跳过）。"""
        from ..deps import finalize_manager as _manager

        p = _project(project_id)
        _manager().start(p.id, subtitles=subtitles, dubbing=dubbing)
        opts = [o for o, on in (("配音", dubbing), ("字幕", subtitles)) if on]
        suffix = f"（含{'/'.join(opts)}）" if opts else ""
        return (
            f"已开始合成成片{suffix}，正在后台拼装各镜头。"
            "完成后成片会出现在作品工作台里，稍等片刻或直接问「合成好了吗」。"
        )

    @tool
    def check_finalize() -> str:
        """查询成片合成的进度与结果。用户问「合成好了吗 / 成片好了没」时调用，不要凭记忆回答。无需参数。"""
        from ..deps import finalize_manager as _manager

        pid = collector.get("project_id")
        rec = _manager().latest_for_project(pid) if pid else None
        if rec is None:
            return "这个项目还没有发起过成片合成。说「合成成片」即可开始。"
        if rec["status"] == "running":
            tail = rec["messages"][-1] if rec["messages"] else "正在准备"
            return f"合成进行中：{tail}"
        if rec["status"] == "failed":
            return f"合成失败了：{rec['error']}。可以排查后再让我重新合成。"
        r = rec["result"] or {}
        head = (f"成片已合成完成（{r.get('duration_sec', 0)} 秒，"
                f"用了 {r.get('shots_used', 0)}/{r.get('shots_total', 0)} 个镜头）")
        flags = [
            "已配音" if r.get("dubbed") else "未配音（无台词或未配置语音）",
            "已烧字幕" if r.get("subtitled") else "无字幕",
        ]
        for w in r.get("warnings") or []:
            flags.append(f"注意：{w}")
        return "；".join([head, *flags]) + "。成片在作品工作台里可直接播放下载。"

    @tool
    def check_background_tasks() -> str:
        """查询后台任务（导演拆解 / 美术 / 摄影 / 定妆图）的状态和结果。用户问「拆好了吗 / 好了没 / 进度如何」时调用，不要凭记忆回答。无需参数。"""
        if runner is None:
            return "后台任务系统未启用，剧组任务会同步执行完成。"
        tasks = runner.list_tasks()[:8]
        if not tasks:
            return "当前没有后台任务记录。"
        lines = []
        for t in tasks:
            status = {"pending": "排队中", "running": "进行中", "done": "已完成", "failed": "失败"}.get(t.status, t.status)
            line = f"- {t.name}：{status}"
            if t.status == "running" and t.steps:
                line += f"，当前：{t.steps[-1].label}"
            if t.status == "done" and t.result:
                line += f"——{_short(t.result, 120)}"
            if t.status == "failed":
                line += "——可以让我重新发起这一步"
            lines.append(line)
        return "\n".join(lines)

    @tool
    def remember(content: str, kind: str = "preference") -> str:
        """记住用户的长期偏好或本项目的决定，之后每轮对话都会自动遵循。kind=preference（用户偏好，跨项目生效）/ decision（项目决定，只在本项目生效）/ feedback（对话内反馈，只在本对话生效）。用户说「记住我喜欢… / 以后都… / 这个项目定下来…」时主动调用。参数：content=要记住的内容（一句话）；kind=记忆类型。"""
        text = (content or "").strip()
        if not text:
            return "要记住的内容不能为空。"
        kind = kind if kind in ("preference", "decision", "feedback") else "preference"
        pid = collector.get("project_id")
        tid = collector.get("conversation_id")
        scope = {"preference": "global", "decision": "project", "feedback": "conversation"}[kind]
        if kind == "decision" and not pid:
            return "项目级决定需要先有项目上下文，请改用 preference 或先创建项目。"
        store.add_memory(
            kind=kind, scope=scope, content=text,
            project_id=pid if scope in ("project", "conversation") else None,
            conversation_id=tid if scope == "conversation" else None,
        )
        return f"已记住（{_MEMORY_KIND_LABELS[kind]}）：{text}"

    @tool
    def recall() -> str:
        """列出当前生效的全部记忆（全局偏好 + 本项目决定 + 本对话反馈），用于回答「你记得什么 / 我之前说过什么」。无需参数。"""
        rows = store.list_memories(
            project_id=collector.get("project_id"),
            conversation_id=collector.get("conversation_id"),
        )
        if not rows:
            return "还没有任何记忆。用户明确说「记住…」时可以用 remember 保存。"
        lines = [
            f"- （{_MEMORY_KIND_LABELS.get(m.kind, m.kind)}）{m.content.strip()}"
            for m in rows[:20] if m.content.strip()
        ]
        return "当前生效的记忆：\n" + "\n".join(lines)

    return [
        create_project,
        map_novel,
        propose_arcs,
        generate_script,
        run_adaptation,
        get_script_overview,
        ask,
        breakdown_scenes,
        generate_style_guide,
        generate_reference_assets,
        generate_video_prompts,
        list_video_shots,
        approve_video_prompts,
        submit_videos,
        get_video_jobs,
        rerun_video,
        add_asset,
        finalize_film,
        check_finalize,
        check_background_tasks,
        remember,
        recall,
    ]


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
    "get_script_overview": "通读剧本", "ask": "查阅剧本内容",
    "breakdown_scenes": "拆解镜头", "generate_style_guide": "生成视觉风格",
    "generate_video_prompts": "撰写镜头提示词", "generate_reference_assets": "生成定妆图",
    "list_video_shots": "盘点镜头", "approve_video_prompts": "批准提示词",
    "submit_videos": "提交出片", "get_video_jobs": "查询出片状态",
    "rerun_video": "重roll镜头", "add_asset": "登记素材", "check_background_tasks": "查询后台任务",
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
            SystemMessage(content=SYSTEM_PROMPT + "\n" + note + memory_note),
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


def _short(text: str, limit: int) -> str:
    """截断工具轨迹展示文本。"""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


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
