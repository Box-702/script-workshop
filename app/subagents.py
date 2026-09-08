# =====================================================================
# subagents.py —— 专职子代理系统
#
# 提供三类专职子代理，由 ChatConductor 作为工具调用：
#   - 场景分析代理（analyze_scenes）：分析场景结构、节拍节奏、人物出场
#   - 风格一致性代理（check_style）：检查全剧风格一致性、对白人设符合度
#   - 对白润色代理（polish_dialogue）：对指定场景的对白做润色建议
#
# 子代理在后台线程中执行，通过 SubAgentRunner 管理生命周期与进度上报。
# =====================================================================

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from .domain import Script
from .llm import LLM

log = logging.getLogger(__name__)


# ---------- 任务模型 ----------


@dataclass
class AgentStep:
    """子代理执行中的一个步骤。"""

    label: str
    status: str = "running"  # running / done / failed
    detail: str = ""


@dataclass
class SubAgentTask:
    """一个子代理任务的完整状态。"""

    id: str
    name: str
    status: str = "pending"  # pending / running / done / failed
    steps: list[AgentStep] = field(default_factory=list)
    result: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "steps": [{"label": s.label, "status": s.status, "detail": s.detail} for s in self.steps],
            "result": self.result,
            "created_at": self.created_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


# ---------- 任务运行器 ----------


class SubAgentRunner:
    """管理后台子代理任务的执行与进度追踪。

    任务在独立线程中运行，进度通过 update_step() 实时上报。
    完成后通过回调通知调用方。
    """

    def __init__(self) -> None:
        self._tasks: dict[str, SubAgentTask] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def _gen_id(self) -> str:
        self._counter += 1
        return f"task_{self._counter:04d}"

    def start(
        self,
        name: str,
        fn: Callable[[SubAgentTask], str],
        *,
        on_done: Callable[[SubAgentTask], None] | None = None,
    ) -> str:
        """启动一个后台子代理任务。返回 task_id。"""
        task_id = self._gen_id()
        task = SubAgentTask(id=task_id, name=name, status="running")
        with self._lock:
            self._tasks[task_id] = task

        def _run() -> None:
            try:
                result = fn(task)
                task.result = result
                task.status = "done"
            except Exception as e:  # noqa: BLE001
                task.result = f"执行失败：{e}"
                task.status = "failed"
                log.warning("子代理 %s(%s) 失败：%s", name, task_id, e)
            finally:
                task.finished_at = datetime.now(UTC)
                if on_done:
                    on_done(task)

        thread = threading.Thread(target=_run, name=f"subagent-{task_id}", daemon=True)
        thread.start()
        return task_id

    def get(self, task_id: str) -> SubAgentTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, *, active_only: bool = False) -> list[SubAgentTask]:
        with self._lock:
            tasks = list(self._tasks.values())
        if active_only:
            tasks = [t for t in tasks if t.status in ("pending", "running")]
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        return tasks

    def update_step(self, task_id: str, label: str, status: str = "running", detail: str = "") -> None:
        """更新任务进度：新增或更新一个步骤。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return
            # 查找已有同名步骤，更新；否则新增
            for step in task.steps:
                if step.label == label:
                    step.status = status
                    step.detail = detail
                    return
            task.steps.append(AgentStep(label=label, status=status, detail=detail))

    def cleanup(self, max_age_hours: int = 24) -> int:
        """清理超过指定小时数的已完成任务。返回清理数量。"""
        now = datetime.now(UTC)
        to_remove = []
        with self._lock:
            for tid, task in self._tasks.items():
                if task.finished_at:
                    age = (now - task.finished_at).total_seconds() / 3600
                    if age > max_age_hours:
                        to_remove.append(tid)
            for tid in to_remove:
                del self._tasks[tid]
        return len(to_remove)


# ---------- 子代理实现 ----------

# 子代理工具名 -> 中文名映射，用于前端展示。
SUBAGENT_LABELS = {
    "analyze_scenes": "场景分析",
    "check_style": "风格一致性检查",
    "polish_dialogue": "对白润色",
}


def run_analyze_scenes(task: SubAgentTask, llm: LLM, script: Script) -> str:
    """场景分析子代理：分析场景结构、节拍节奏、人物出场分布。"""
    runner = _get_runner()

    # 步骤 1：提取场景数据
    runner.update_step(task.id, "提取场景数据", "running")
    scenes_info = []
    for sc in script.scenes:
        beat_types = {"action": 0, "dialogue": 0, "cue": 0}
        for b in sc.beats:
            beat_types[b.type] = beat_types.get(b.type, 0) + 1
        scenes_info.append({
            "id": sc.id, "title": sc.title, "purpose": sc.purpose,
            "conflict": sc.conflict, "characters": sc.characters,
            "beat_counts": beat_types, "total_beats": len(sc.beats),
        })
    runner.update_step(task.id, "提取场景数据", "done", f"共 {len(scenes_info)} 个场景")

    # 步骤 2：统计分析
    runner.update_step(task.id, "统计分析", "running")
    total_beats = sum(s["total_beats"] for s in scenes_info)
    total_dialogue = sum(s["beat_counts"]["dialogue"] for s in scenes_info)
    total_action = sum(s["beat_counts"]["action"] for s in scenes_info)

    # 人物出场频次
    char_freq: dict[str, int] = {}
    for sc in script.scenes:
        for cid in sc.characters:
            char_freq[cid] = char_freq.get(cid, 0) + 1
    char_name_map = {c.id: c.name for c in script.characters}
    top_chars = sorted(char_freq.items(), key=lambda x: x[1], reverse=True)[:8]
    char_stats = "、".join(f"{char_name_map.get(cid, cid)}({cnt}场)" for cid, cnt in top_chars)

    runner.update_step(task.id, "统计分析", "done", f"总节拍 {total_beats}，对白 {total_dialogue}，动作 {total_action}")

    # 步骤 3：LLM 深度分析（可选）
    analysis = ""
    if llm.available:
        runner.update_step(task.id, "LLM 深度分析", "running")
        try:

            prompt = (
                f"你是剧本结构分析专家。请分析以下剧本的场景结构：\n\n"
                f"标题：《{script.title}》\n"
                f"梗概：{script.logline}\n"
                f"场景数：{len(scenes_info)}，总节拍：{total_beats}\n"
                f"对白/动作比：{total_dialogue}/{total_action}\n"
                f"人物出场：{char_stats}\n\n"
                f"场景列表：\n"
            )
            for s in scenes_info:
                prompt += f"- {s['id']} {s['title']}：{s['purpose']}（{s['total_beats']} 节拍）\n"
            prompt += (
                "\n请从以下维度分析：\n"
                "1. 节奏曲线：哪些场景节奏紧凑、哪些舒缓？有无节奏变化？\n"
                "2. 人物出场分布：主角戏份是否充足？配角是否被边缘化？\n"
                "3. 冲突递进：场景间的冲突是否有递进？\n"
                "4. 结构建议：整体结构有什么可以改进的地方？\n"
                "请简洁回答，每点 2-3 句。"
            )
            resp = llm.chat().invoke([
                SystemMessage(content="你是剧本结构分析专家，回答简洁专业。"),
                HumanMessage(content=prompt),
            ])
            analysis = str(resp.content or "").strip()
            runner.update_step(task.id, "LLM 深度分析", "done")
        except Exception as e:  # noqa: BLE001
            runner.update_step(task.id, "LLM 深度分析", "failed", str(e))
    else:
        runner.update_step(task.id, "LLM 深度分析", "done", "未配置模型，跳过")

    # 组装结果
    result_parts = [
        f"## 场景分析报告 —— 《{script.title}》\n",
        f"**总览**：{len(scenes_info)} 个场景，{total_beats} 个节拍",
        f"对白 {total_dialogue} 条 / 动作 {total_action} 条，对白占比 {total_dialogue / max(total_beats, 1) * 100:.0f}%",
        f"**人物出场**：{char_stats}\n",
    ]
    if analysis:
        result_parts.append(f"### 深度分析\n{analysis}")
    result_parts.append("### 场景清单")
    for s in scenes_info:
        bc = s["beat_counts"]
        result_parts.append(
            f"- **{s['id']} {s['title']}**：{s['purpose']}　"
            f"（{s['total_beats']} 拍：动作 {bc['action']} / 对白 {bc['dialogue']} / 提示 {bc['cue']}）"
        )
    return "\n".join(result_parts)


def run_check_style(task: SubAgentTask, llm: LLM, script: Script) -> str:
    """风格一致性子代理：检查全剧风格、对白人设符合度。"""
    runner = _get_runner()

    # 步骤 1：收集对白样本
    runner.update_step(task.id, "收集对白样本", "running")
    char_name_map = {c.id: c.name for c in script.characters}
    char_role_map = {c.id: c.role for c in script.characters}
    dialogue_samples: dict[str, list[str]] = {}
    for sc in script.scenes:
        for b in sc.beats:
            if b.type == "dialogue" and b.speaker and b.line:
                name = char_name_map.get(b.speaker, b.speaker)
                dialogue_samples.setdefault(name, []).append(b.line)
    sample_summary = "、".join(f"{n}({len(lines)}句)" for n, lines in dialogue_samples.items())
    runner.update_step(task.id, "收集对白样本", "done", sample_summary)

    # 步骤 2：LLM 分析
    if not llm.available:
        runner.update_step(task.id, "LLM 风格分析", "done", "未配置模型，跳过")
        return f"## 风格检查报告\n\n未配置模型，无法进行深度风格分析。\n\n**对白统计**：{sample_summary}"

    runner.update_step(task.id, "LLM 风格分析", "running")
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = f"你是剧本风格顾问。请检查《{script.title}》的风格一致性：\n\n"
        prompt += f"梗概：{script.logline}\n主题：{'、'.join(script.themes)}\n\n"
        prompt += "各角色对白样本（每人最多 5 句）：\n"
        for name, lines in dialogue_samples.items():
            role = char_role_map.get(
                next((cid for cid, n in char_name_map.items() if n == name), ""), ""
            )
            prompt += f"\n【{name}】（{role}）：\n"
            for line in lines[:5]:
                prompt += f"  「{line}」\n"
        prompt += (
            "\n请从以下维度检查：\n"
            "1. 对白风格统一性：全剧对白风格是否一致？有无突兀的文风跳变？\n"
            "2. 人设符合度：每个角色的对白是否符合其人设？有无「出戏」的台词？\n"
            "3. 语言时代感：对白是否有统一的时代感？古今混搭是否合适？\n"
            "4. 改进建议：针对发现的问题给出具体修改建议。\n"
            "请简洁回答，每点 2-3 句。有问题时引用具体台词。"
        )
        resp = llm.chat().invoke([
            SystemMessage(content="你是剧本风格顾问，回答简洁专业，有问题时引用具体台词。"),
            HumanMessage(content=prompt),
        ])
        analysis = str(resp.content or "").strip()
        runner.update_step(task.id, "LLM 风格分析", "done")
    except Exception as e:  # noqa: BLE001
        analysis = f"分析失败：{e}"
        runner.update_step(task.id, "LLM 风格分析", "failed", str(e))

    return f"## 风格一致性检查报告 —— 《{script.title}》\n\n**对白统计**：{sample_summary}\n\n{analysis}"


def run_polish_dialogue(
    task: SubAgentTask, llm: LLM, script: Script, scene_id: str | None = None
) -> str:
    """对白润色子代理：对指定场景（或全部场景）的对白做润色建议。"""
    runner = _get_runner()
    char_name_map = {c.id: c.name for c in script.characters}

    # 步骤 1：选定场景
    runner.update_step(task.id, "选定目标场景", "running")
    if scene_id:
        targets = [sc for sc in script.scenes if sc.id == scene_id]
        if not targets:
            runner.update_step(task.id, "选定目标场景", "failed", f"场景 {scene_id} 不存在")
            return f"场景 {scene_id} 不存在，无法润色。"
    else:
        targets = list(script.scenes)
    runner.update_step(task.id, "选定目标场景", "done", f"{len(targets)} 个场景")

    # 步骤 2：提取对白
    runner.update_step(task.id, "提取对白", "running")
    all_lines: list[dict[str, str]] = []
    for sc in targets:
        for b in sc.beats:
            if b.type == "dialogue" and b.speaker and b.line:
                all_lines.append({
                    "scene": sc.title,
                    "speaker": char_name_map.get(b.speaker, b.speaker),
                    "line": b.line,
                    "emotion": b.emotion or "",
                })
    runner.update_step(task.id, "提取对白", "done", f"{len(all_lines)} 条对白")

    if not all_lines:
        return "所选场景中没有对白，无需润色。"

    # 步骤 3：LLM 润色
    if not llm.available:
        runner.update_step(task.id, "LLM 润色", "done", "未配置模型，跳过")
        lines_text = "\n".join(f"【{loc['scene']}】{loc['speaker']}：{loc['line']}" for loc in all_lines[:20])
        return f"## 对白润色报告\n\n未配置模型，以下为当前对白列表：\n\n{lines_text}"

    runner.update_step(task.id, "LLM 润色", "running")
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        prompt = f"你是对白润色专家。请为《{script.title}》的对白提供润色建议。\n\n"
        prompt += f"主题：{'、'.join(script.themes)}\n\n当前对白：\n"
        for loc in all_lines[:30]:
            emo = f"（{loc['emotion']}）" if loc["emotion"] else ""
            prompt += f"【{loc['scene']}】{loc['speaker']}{emo}：{loc['line']}\n"
        prompt += (
            "\n请对每条对白给出润色建议：\n"
            "1. 保留原意但更自然/更有张力的改写版本\n"
            "2. 如果原句已经很好，标注「保持」\n"
            "3. 简要说明修改理由\n\n"
            "格式：\n"
            "原句 → 建议改写（理由）\n"
            "请简洁，每条一行。"
        )
        resp = llm.chat().invoke([
            SystemMessage(content="你是对白润色专家，擅长让台词更自然、更有戏剧张力。回答简洁。"),
            HumanMessage(content=prompt),
        ])
        suggestions = str(resp.content or "").strip()
        runner.update_step(task.id, "LLM 润色", "done")
    except Exception as e:  # noqa: BLE001
        suggestions = f"润色失败：{e}"
        runner.update_step(task.id, "LLM 润色", "failed", str(e))

    return f"## 对白润色建议 —— 《{script.title}》\n\n共 {len(all_lines)} 条对白\n\n{suggestions}"


# ---------- 内部辅助 ----------

_runner: SubAgentRunner | None = None
_runner_lock = threading.Lock()


def _get_runner() -> SubAgentRunner:
    """获取全局 SubAgentRunner 单例。"""
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = SubAgentRunner()
    return _runner


def get_runner() -> SubAgentRunner:
    """公开接口：获取全局 SubAgentRunner 单例。"""
    return _get_runner()
