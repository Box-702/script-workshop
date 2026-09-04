# =====================================================================
# agent.py —— Agent 运行服务
#
# 这是一层薄服务，专门把「HTTP 请求」和「LangGraph 图」对接起来：
#   start_agent_run()   发起一次改编运行，跑到 review 中断，返回提议；
#   resume_agent_run()  用 Command(resume=...) 恢复被中断的图；
#   get_run()           读取一次运行的当前状态。
#
# 同时提供两个兜底，保证项目在没有模型 / 没有持久 checkpointer 时依旧可用：
#   - 无模型：图节点走本地规则回退（见 patch.fallback_patch）；
#   - 线程丢失（例如 InMemorySaver 因服务重启而失效）：恢复时直接
#     基于已落库的 patch 重新应用，仍能生成新版本，而不是报错。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Command

from .config import Settings
from .graph import build_run_graph, thread_config
from .llm import LLM
from .patch import PatchOp, apply_patch, validate_script
from .store import Project, ScriptVersion, Store
from .vector import VectorStore

log = logging.getLogger(__name__)


def _select_ops(patch: list[dict[str, Any]], indexes: list[int] | None) -> list[PatchOp]:
    """按用户勾选下标挑选 patch 操作；未选择则全接受。"""
    ops = [PatchOp.model_validate(op) for op in patch]
    if not indexes:
        return ops
    return [ops[i] for i in indexes if 0 <= i < len(ops)] or ops


def _interrupt_value(result: dict[str, Any]) -> dict[str, Any] | None:
    """从 invoke 返回中提取 interrupt 载荷（提议内容）。"""
    interrupts = result.get("__interrupt__")
    if interrupts:
        return interrupts[0].value
    return None


def start_agent_run(
    store: Store,
    llm: LLM,
    settings: Settings,
    *,
    project: Project,
    base_version: ScriptVersion,
    instruction: str,
    scene_ids: list[str],
    vector: VectorStore,
    embedder: Any,
    model_label: str = "openai-compatible",
) -> dict[str, Any]:
    """发起一次 Agent 改编运行，并返回「等待审阅」的提议。

    返回：run_id、plan、patch、status，以及中断载荷（用于前端展示）。
    """
    run_id = _new_run_id()
    graph = build_run_graph(
        store,
        llm,
        settings,
        project=project,
        base_script=base_version.script,
        raw_text=project.raw_text,
        vector=vector,
        embedder=embedder,
        base_version_id=base_version.id,
    )
    input_state = {
        "project_id": project.id,
        "base_version_id": base_version.id,
        "scene_ids": scene_ids,
        "instruction": instruction,
        "run_id": run_id,
    }
    steps: list[str] = []
    plan: list[str] = []
    patch: list[dict[str, Any]] = []
    review: dict[str, Any] | None = None
    status = "reviewing"
    error = None
    try:
        # 用 stream 采集节点级执行轨迹 + 拿到中断载荷，作为「可观测」进度。
        interrupt_value, steps = _stream_to_interrupt(graph, input_state, thread_config(run_id))
        payload = interrupt_value or {}
        plan = payload.get("plan") or []
        patch = payload.get("patch") or []
        review = payload.get("review")  # 评审打分 + 一致性保障结果（见 app/review.py）
    except Exception as e:  # noqa: BLE001
        # 模型出错时不直接失败：降级为「可审阅的说明性 patch」，并记录错误。
        log.warning("Agent 运行失败，降级为说明性建议：%s", e)
        from .patch import fallback_patch

        fb_plan, fb_ops = fallback_patch(base_version.script, instruction, scene_ids)
        plan = fb_plan + [f"（模型调用失败，已保留说明性建议：{e}）"]
        patch = [op.model_dump(exclude_none=True) for op in fb_ops]
        status = "reviewing"
        error = str(e)

    store.create_agent_run(
        run_id=run_id,
        project_id=project.id,
        base_version_id=base_version.id,
        user_prompt=instruction,
        scene_ids=scene_ids,
        plan=plan,
        patch=patch,
        steps=steps,
        status=status,
        model=model_label if llm.available else "local-rule-fallback",
        error_message=error,
    )
    return {
        "run_id": run_id,
        "plan": plan,
        "patch": patch,
        "steps": steps,
        "status": status,
        "error": error,
        "review": review,
    }


def _stream_to_interrupt(graph: Any, input: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """用 ``graph.stream(stream_mode="updates")`` 运行到中断，返回 (中断载荷, 节点轨迹)。

    stream 会按节点产出 update；遇到 interrupt 时产出 ``__interrupt__`` 并停住。
    这里据此拿到提议载荷与「实际执行了哪些节点」，供前端展示进度。
    """
    interrupt_value: dict[str, Any] | None = None
    steps: list[str] = []
    for chunk in graph.stream(input, config, stream_mode="updates"):
        for node_name, update in chunk.items():
            if node_name == "__interrupt__":
                interrupt_value = update[0].value
            else:
                steps.append(node_name)
    # 结束节点（finalize）后，最后再用 get_state 读一次全量状态，保证拿到终态字段。
    return interrupt_value, steps


def resume_agent_run(
    store: Store,
    llm: LLM,
    settings: Settings,
    *,
    run_id: str,
    action: str,
    patch_indexes: list[int] | None = None,
    patch: list[dict[str, Any]] | None = None,
    feedback: str | None = None,
    vector: VectorStore,
    embedder: Any,
) -> dict[str, Any]:
    """恢复被中断的图，执行用户决策（接受/编辑/重新生成/拒绝）。

    优先走 LangGraph 的 ``Command(resume=HumanDecision)`` 恢复；
    若线程状态已丢失（如 InMemorySaver 随服务重启失效），则回退为
    基于已落库 patch 的直接应用（见 _apply_directly）。
    """
    run = store.get_agent_run(run_id)
    if run is None:
        return {"status": "not_found", "error": "运行记录不存在"}
    project = store.get_project(run.project_id)
    base_version = store.get_version(run.base_version_id)
    if project is None or base_version is None:
        return {"status": "failed", "error": "找不到项目或基础版本"}

    decision = {
        "action": action,
        "patch_indexes": patch_indexes,
        "patch": patch,
        "feedback": feedback,
    }
    try:
        graph = build_run_graph(
            store,
            llm,
            settings,
            project=project,
            base_script=base_version.script,
            raw_text=project.raw_text,
            vector=vector,
            embedder=embedder,
            base_version_id=base_version.id,
        )
        interrupt_value, steps = _stream_to_interrupt(
            graph, Command(resume=decision), thread_config(run_id)
        )
        if interrupt_value is not None:
            # 重新生成（regenerate）后再次中断，等待人类继续审阅新的提议。
            new_plan = interrupt_value.get("plan") or run.plan
            new_patch = interrupt_value.get("patch") or run.patch
            new_review = interrupt_value.get("review")
            store.update_agent_run(
                run_id,
                status="reviewing",
                plan=new_plan,
                patch=new_patch,
                steps=run.steps + steps,
                decision=decision,
            )
            return {
                "status": "reviewing",
                "plan": new_plan,
                "patch": new_patch,
                "steps": run.steps + steps,
                "decision": decision,
                "review": new_review,
            }
        final_state = graph.get_state(thread_config(run_id)).values
        status = final_state.get("status", "applied")
        store.update_agent_run(run_id, steps=run.steps + steps)
        return {
            "status": status,
            "new_version_id": final_state.get("new_version_id"),
            "decision": decision,
            "steps": run.steps + steps,
        }
    except Exception as e:  # noqa: BLE001
        log.warning("LangGraph 恢复失败，使用 direct-apply 兜底：%s", e)
        return _apply_directly(store, run, project, base_version, decision)


def _apply_directly(
    store: Store,
    run: Any,
    project: Project,
    base_version: ScriptVersion,
    decision: dict[str, Any],
) -> dict[str, Any]:
    """线程丢失时的兜底：基于已落库 patch（或人工修订 patch）直接应用，仍生成新版本。

    - accept / edit -> 应用并生成新版本（edit 优先采用人工修订的操作清单）；
    - reject        -> 拒绝；
    - regenerate    -> 线程已丢无法真正重做，按拒绝处理并说明。
    """
    action = decision.get("action", "reject")
    if action not in ("accept", "edit"):
        store.update_agent_run(run.id, status="rejected", decision=decision)
        return {"status": "rejected", "decision": decision, "fallback": True}

    # 优先取人工修订后的操作清单（edit），否则取已落库 patch 按下标筛选。
    if decision.get("patch"):
        from .patch import PatchOp

        ops = [PatchOp.model_validate(op) for op in decision["patch"]]
    else:
        ops = _select_ops(run.patch, decision.get("patch_indexes"))
    new_script = apply_patch(base_version.script, ops)
    issues = validate_script(new_script)
    version = store.create_version(
        project,
        new_script,
        source_type="agent_adaptation",
        label="AI 改编",
        notes=f"用户需求：{run.user_prompt}（应用 {len(ops)} 项，兜底应用）",
        parent_version_id=base_version.id,
        set_current=True,
    )
    store.update_agent_run(
        run.id,
        status="applied",
        decision=decision,
        result_version_id=version.id,
    )
    return {
        "status": "applied",
        "new_version_id": version.id,
        "decision": decision,
        "fallback": True,
        "validation_issues": [i.model_dump() for i in issues],
    }


def get_run(store: Store, run_id: str) -> dict[str, Any] | None:
    """读取一次运行的当前状态与提议。"""
    run = store.get_agent_run(run_id)
    if run is None:
        return None
    return {
        "run_id": run.id,
        "project_id": run.project_id,
        "base_version_id": run.base_version_id,
        "result_version_id": run.result_version_id,
        "user_prompt": run.user_prompt,
        "scene_ids": run.scene_ids,
        "plan": run.plan,
        "patch": run.patch,
        "steps": run.steps,
        "status": run.status,
        "decision": run.decision,
        "model": run.model,
        "error_message": run.error_message,
        "created_at": run.created_at.isoformat(),
    }


def _new_run_id() -> str:
    """生成线程 / 运行共用的 id。"""
    from .store import gen_id

    return gen_id("run")
