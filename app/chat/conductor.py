# =====================================================================
# chat.py —— 对话式 Agent（Codex / DSH 风格的工作形式）
#
# 这是本次改造的核心：把「表单式」的工作台升级为「对话式」的 agent。
# 用户像和 Codex / DSH 对话一样，通过自然语言完成：
#   新建剧本（新建项目）-> 生成初稿 -> 提出改编需求 -> 审阅 / 接受 / 拒绝
#   -> 咨询同类剧本走向 / 写作手法 / 作者风格 -> 让 Agent 记住偏好。
#
# 架构（两层，底层复用既有工作流）：
#   - 上层：ChatConductor —— 一个绑定了工具的对话式 LangGraph 小图，
#     负责理解用户意图并编排动作（ReAct 循环，工具由 ToolNode 执行）；
#   - 底层：既有 LangGraph 改编工作流（app/agent/graph.py / app/agent/runner.py），
#     由 run_adaptation / resume 工具调用，改动仍走
#     propose -> guard -> review(interrupt) -> apply 的审阅闭环。
#   - 记忆：项目知识（同类走向 / 手法 / 作者风格，见 app/pipeline/knowledge.py）
#     与用户记忆（app/pipeline/memory.py 的 memories 表），由 create_project / remember / ask 工具读写。
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
from ..pipeline.generation import generate_script as run_generation
from ..pipeline.knowledge import (
    detect_genres,
    format_author_style,
    format_genre_knowledge,
)
from ..llm import LLM
from ..pipeline.patch import validate_script
from ..store import Project, Store
from ..agent.skills import (
    SubAgentRunner,
    run_analyze_scenes,
    run_check_style,
    run_polish_dialogue,
)

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


class _Collector(TypedDict, total=False):
    """工具通过闭包写入的运行期收集器（图状态保持干净可序列化）。"""

    project_id: str | None
    payloads: list[dict[str, Any]]


SYSTEM_PROMPT = (
    "你是「剧本工坊」的改编协作者 Agent，工作形式类似 Codex / DSH：通过对话与作者协作，"
    "把一部作品改编成结构化剧本，并持续打磨。你的能力边界：\n"
    "1. 新建剧本：用户说「新建项目 / 新建剧本 / 新开一部」时调用 create_project。"
    "缺少标题、改编类型或原文时，先向用户问清楚再创建。\n"
    "2. 生成初稿：用户要求「生成 / 初稿 / 第一版 / 出剧本」时调用 generate_script。\n"
    "3. 改编：用户提出改编需求（改对白、改节奏、改标题、压缩、反转、口语化等）时调用 run_adaptation。"
    "改编会走底层审阅工作流，结果以「审阅卡片」展示，请引导用户接受 / 拒绝 / 重新生成。\n"
    "4. 咨询：用户问「剧本怎么样 / 同类剧怎么走 / 写作手法 / 我的风格」时调用 get_script_overview 或 ask，"
    "用项目知识库（同类剧本走向、写作手法、作者风格）给出有依据的回答，不要凭空编造。\n"
    "5. 记忆：用户表达风格偏好或创作原则（如「我喜欢冷峻的笔调」「结尾要留白」）时调用 remember 记入知识库。\n"
    "6. 场景分析：用户要求「分析场景 / 看看结构 / 场景节奏」时调用 analyze_scenes，会在后台启动专职分析代理。\n"
    "7. 风格检查：用户要求「检查风格 / 看看对白是否一致 / 人设有没有崩」时调用 check_style。\n"
    "8. 对白润色：用户要求「润色对白 / 改一下台词 / 让对白更自然」时调用 polish_dialogue。\n"
    "9. 导演拆解：用户要求「拆镜头 / 分镜 / 设计镜头 / 场景拆解」时调用 breakdown_scenes，将场景拆解为镜头方案。\n"
    "10. 美术指导：用户要求「风格指南 / 视觉风格 / 角色造型 / 画面风格」时调用 generate_style_guide。\n"
    "11. 摄影指导：用户要求「视频 prompt / 生成 prompt / 镜头描述」时调用 generate_video_prompts，为镜头生成英文视频 Prompt。\n"
    "12. 联网搜索：用户要求「搜索 / 查资料 / 找参考 / 同类作品」时调用 web_search，查找创作参考和行业资讯。\n"
    "13. 参考资产：用户要求「定妆图 / 参考图 / 人物形象图 / 视觉参考」时调用 generate_reference_assets，为角色与场景生成定妆图并质检注册，锁跨镜一致性。\n"
    "行为准则：回复简洁、口语化、用简体中文；不确定时先问；不要虚构剧本内容；"
    "不要替用户做最终决定，审阅与落版决定永远交给用户。"
    "子代理（6-11、13）会在后台运行，启动后告知用户可在右栏查看进度。"
)

# 改编类型 -> 中文名，用于提示模型填参数。
_ADAPT_TYPE_LABELS = {
    "short_drama": "短剧",
    "film": "电影",
    "series": "剧集",
    "stage": "舞台剧",
    "other": "自定义",
}


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
        # 提取作者风格存入 notes
        try:
            from ..pipeline.knowledge import extract_author_style
            style = extract_author_style(raw_text, llm=llm, language="zh-CN")
            notes = f"作者风格：{style.get('summary', '')}"
            store.set_project_notes(p.id, notes)
        except Exception:
            pass
        genres = detect_genres(raw_text, top=2)
        return (
            f"已创建剧本项目《{p.title}》（id={p.id}，类型：{label}，题材：{'、'.join(genres)}）。"
            f"需要我现在生成剧本初稿吗？"
        )

    @tool
    def generate_script(project_id: str) -> str:
        """为指定项目生成剧本初稿（生成流水线：故事圣经 -> 场景/节拍）。参数：project_id=项目 id。"""
        p = _project(project_id)
        script, artifacts = run_generation(
            llm,
            settings,
            title=p.title,
            raw_text=p.raw_text,
            adaptation_type=p.adaptation_type,
            language=p.language,
        )
        version = store.create_version(
            p,
            script,
            source_type="generation",
            label="初始生成",
            notes=f"生成模式：{artifacts.get('mode', 'n/a')}",
            parent_version_id=p.current_version_id,
            set_current=True,
        )
        issues = [i for i in validate_script(script) if i.severity == "error"]
        return (
            f"已生成初稿版本 {version.id}（模式：{artifacts.get('mode')}）："
            f"共 {len(script.scenes)} 场，{len(script.characters)} 个人物，"
            f"{len(script.locations)} 个地点。梗概：{script.logline}。"
            f"校验问题 {len(issues)} 项。"
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
        """就剧本 / 改编创作提问（参考题材知识、作者风格、用户偏好），给出有依据的回答。参数：project_id=项目 id，question=问题。"""
        p = _project(project_id)
        overview = _overview_text(p)
        # 题材知识
        genres = detect_genres(p.raw_text, top=2)
        genre_text = format_genre_knowledge(genres)
        # 作者风格
        style_text = format_author_style(p.raw_text)
        # 用户记忆
        from ..pipeline.memory import format_memories, recall_memories
        memories = recall_memories(store, project_id=p.id, limit=5)
        memory_text = format_memories(memories)

        if llm.available:
            try:
                resp = llm.chat().invoke(
                    [
                        SystemMessage(
                            content=(
                                "你是剧本创作顾问。基于下面提供的剧本概况、题材知识、作者风格和用户偏好回答问题；"
                                "回答要具体、可操作，不要编造。"
                            )
                        ),
                        HumanMessage(
                            content=(
                                f"剧本概况：\n{overview}\n\n"
                                f"题材知识：\n{genre_text}\n\n"
                                f"作者风格：\n{style_text}\n\n"
                                f"用户偏好：\n{memory_text or '暂无'}\n\n"
                                f"用户问题：{question}"
                            )
                        ),
                    ]
                )
                return str(resp.content or "").strip()
            except Exception as e:  # noqa: BLE001
                log.warning("ask 组装回答失败：%s", e)
        return f"（未配置模型，以下为直接信息）\n{genre_text}\n\n{style_text}"

    @tool
    def remember(project_id: str, content: str, kind: str = "preference") -> str:
        """把用户表达的偏好 / 创作原则记入项目记忆。kind 可选：preference（偏好）、decision（决策）、feedback（反馈）。参数：project_id=项目 id。"""
        from ..pipeline.memory import save_memory
        p = _project(project_id)
        kind_map = {
            "preference": "preference", "偏好": "preference", "风格": "preference",
            "decision": "decision", "决策": "decision", "决定": "decision",
            "feedback": "feedback", "反馈": "feedback",
        }
        kind_key = kind_map.get(str(kind).strip(), "preference")
        save_memory(store, kind=kind_key, content=content, scope="project", project_id=p.id)
        label = {"preference": "偏好", "decision": "决策", "feedback": "反馈"}.get(kind_key, kind_key)
        return f"已记住（{label}）：{content.strip()}。后续改编会参考这条记忆。"

    # ---- 子代理工具 ----

    @tool
    def analyze_scenes(project_id: str) -> str:
        """启动场景分析子代理：分析场景结构、节拍节奏、人物出场分布。在后台运行，用户可在右栏查看进度。参数：project_id=项目 id。"""
        p = _project(project_id)
        version = store.latest_version(p)
        if version is None:
            return "还没有剧本版本，请先生成初稿。"
        script = version.script

        def _run(task):
            return run_analyze_scenes(task, llm, script)

        task_id = runner.start("场景分析", _run) if runner else "local"
        collector["payloads"].append({
            "type": "sub_agent_started",
            "task_id": task_id,
            "name": "场景分析",
            "project_id": p.id,
        })
        return f"已启动场景分析代理（任务 {task_id}），正在后台分析《{script.title}》的场景结构。你可以在右侧「Agent 任务」面板查看进度，也可以继续对话。"

    @tool
    def check_style(project_id: str) -> str:
        """启动风格一致性检查子代理：检查全剧对白风格一致性、人设符合度。在后台运行。参数：project_id=项目 id。"""
        p = _project(project_id)
        version = store.latest_version(p)
        if version is None:
            return "还没有剧本版本，请先生成初稿。"
        script = version.script

        def _run(task):
            return run_check_style(task, llm, script)

        task_id = runner.start("风格一致性检查", _run) if runner else "local"
        collector["payloads"].append({
            "type": "sub_agent_started",
            "task_id": task_id,
            "name": "风格一致性检查",
            "project_id": p.id,
        })
        return f"已启动风格检查代理（任务 {task_id}），正在后台检查《{script.title}》的风格一致性。可在右侧「Agent 任务」面板查看进度。"

    @tool
    def polish_dialogue(project_id: str, scene_id: str = "") -> str:
        """启动对白润色子代理：对指定场景（或全部场景）的对白做润色建议。在后台运行。参数：project_id=项目 id，scene_id=场景 id（可选，不填则润色全部）。"""
        p = _project(project_id)
        version = store.latest_version(p)
        if version is None:
            return "还没有剧本版本，请先生成初稿。"
        script = version.script
        sid = scene_id.strip() or None

        def _run(task):
            return run_polish_dialogue(task, llm, script, scene_id=sid)

        label = f"对白润色（{sid}）" if sid else "对白润色"
        task_id = runner.start(label, _run) if runner else "local"
        collector["payloads"].append({
            "type": "sub_agent_started",
            "task_id": task_id,
            "name": label,
            "project_id": p.id,
        })
        scope = f"场景 {sid}" if sid else "全部场景"
        return f"已启动对白润色代理（任务 {task_id}），正在后台润色{scope}的对白。可在右侧「Agent 任务」面板查看进度。"

    # ---- v3.0 导演组工具 ----

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
        return f"已启动导演 Agent（任务 {task_id}），正在将{scope}拆解为镜头方案。可在右侧「Agent 任务」面板查看进度。"

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
        return f"已启动美术指导 Agent（任务 {task_id}），正在生成视觉风格指南。可在右侧「Agent 任务」面板查看进度。"

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
                # 更新 video_versions 中的 shots
                shots_data = [s.model_dump() for s in result.data]
                store.create_video_version(
                    project_id=p.id,
                    shots=shots_data,
                    source_type="agent",
                    label="含视频 Prompt",
                    notes=result.summary,
                )
            return result.summary

        task_id = runner.start("摄影指导", _run) if runner else "local"
        collector["payloads"].append({
            "type": "sub_agent_started",
            "task_id": task_id,
            "name": "摄影指导",
            "project_id": p.id,
        })
        return f"已启动摄影指导 Agent（任务 {task_id}），正在为镜头生成视频 Prompt。可在右侧「Agent 任务」面板查看进度。"

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
            f"已启动参考资产流水线（任务 {task_id}）：为角色与场景生成定妆图并做视觉质检。"
            "可在右侧「Agent 任务」面板查看进度。完成后镜头会自动带上这些参考图。"
        )

    @tool
    def web_search(query: str) -> str:
        """联网搜索：查找剧本创作参考、同类作品分析、写作技法、行业资讯等。需要配置 TAVILY_API_KEY。"""
        from ..config import get_settings
        from ..pipeline.search import format_search_results, search_sync
        api_key = get_settings().tavily_api_key
        if not api_key:
            return "（未配置 TAVILY_API_KEY，无法联网搜索。请在 .env 中设置 TAVILY_API_KEY。）"
        try:
            data = search_sync(query, api_key=api_key, max_results=5)
            return format_search_results(data)
        except Exception as e:
            return f"（搜索失败：{e}）"

    result = [create_project, generate_script, run_adaptation, get_script_overview, ask, remember,
              analyze_scenes, check_style, polish_dialogue,
              breakdown_scenes, generate_style_guide, generate_reference_assets,
              generate_video_prompts, web_search]

    # 追加插件工具
    try:
        from ..deps import plugin_registry
        result.extend(plugin_registry().get_all_tools())
    except Exception:  # noqa: BLE001
        pass

    return result


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


def _history_lc_messages(store: Store, conversation_id: str | None, limit: int = 60) -> list[AnyMessage]:
    """把 DB 里的对话历史转成 LangChain 消息（user/assistant），供本轮 LLM 参考。"""
    thread = conversation_id or GLOBAL_THREAD
    messages: list[AnyMessage] = []
    for m in store.list_chat_messages(thread, limit=limit):
        if m.role == "user":
            messages.append(HumanMessage(content=m.content))
        elif m.role == "assistant" and m.content:
            messages.append(AIMessage(content=m.content))
    return messages


# ---------- 对话服务 ----------


def _prepare_turn(
    store: Store, llm: LLM, runner: SubAgentRunner | None, conversation_id: str | None,
    project_id: str | None, message: str, meta: dict[str, Any] | None,
) -> tuple[_Collector, Any, dict[str, Any]]:
    """准备一轮对话的 collector, graph, input_state。"""
    collector: _Collector = {"project_id": project_id, "payloads": []}
    graph = build_chat_graph(store, llm, collector, runner=runner)
    note = _current_project_note(store, project_id)
    input_state: dict[str, Any] = {
        "project_id": project_id,
        "messages": [
            SystemMessage(content=SYSTEM_PROMPT + "\n\n" + note),
            *_history_lc_messages(store, conversation_id),
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
) -> dict[str, Any]:
    """保存消息并返回对话结果。"""
    thread = conversation_id or GLOBAL_THREAD
    new_project_id = collector.get("project_id") or project_id
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
        for chunk in graph.stream(input_state, stream_mode="updates"):
            for node, update in chunk.items():
                events.extend(_extract_events(node, update))
                if node == "chat_agent":
                    for m in (update.get("messages") or []):
                        if isinstance(m, AIMessage) and not m.tool_calls and m.content:
                            final_text = _msg_text(m.content)
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
    events: list[dict[str, Any]] = []
    final_text = ""
    last_update_text = ""
    try:
        for chunk in graph.stream(input_state, stream_mode=["updates", "messages"]):
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
            elif mode == "messages":
                pairs = data if isinstance(data, list) else [data]
                for pair in pairs:
                    msg_chunk = pair[0] if isinstance(pair, (tuple, list)) else pair
                    if getattr(msg_chunk, "type", "") != "ai":
                        continue
                    delta = _msg_text(getattr(msg_chunk, "content", None))
                    if delta:
                        final_text += delta
                        yield {"event": "token", "data": {"delta": delta}}
        if not final_text:
            final_text = last_update_text
    except Exception as e:  # noqa: BLE001
        log.warning("对话流式运行失败：%s", e)
        yield {"event": "error", "data": {"message": str(e)}}
        return

    result = _finalize_turn(store, collector, conversation_id, project_id, message, meta, final_text, events)
    yield {"event": "done", "data": result}


def _short(text: str, limit: int) -> str:
    """截断工具轨迹展示文本。"""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit] + "…"


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
