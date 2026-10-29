# =====================================================================
# director.py —— 导演 Agent
#
# 职责：创意总控、场景拆解
# 输入：Script（完整剧本）
# 输出：list[SceneBreakdown]（每个场景的镜头拆解方案）
#
# 导演分析每场戏的戏剧目标、情绪曲线、节奏需求，
# 决定如何用镜头语言讲好这个故事。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from ..domain import (
    CameraMovement,
    SceneAnchors,
    SceneBreakdown,
    Script,
    Shot,
)
from ..llm import LLM
from ..skills import render_skill
from .base import CrewAgent, CrewTaskResult
from .dramaturgy import SHOT_FUNCTIONS, audit_breakdowns

log = logging.getLogger(__name__)

# 导演的系统提示词外置为技能文件：app/skills/director-breakdown/SKILL.md
# （改规则改 .md 即可，不必动代码；原因见 docs/DECISIONS.md D-12）
def director_system() -> str:
    """导演系统提示词（内容在 app/skills/director-breakdown/SKILL.md）。"""
    return render_skill("director-breakdown")


# 分镜连续性校验失败后的最大重做次数（有界，避免死循环）。
MAX_DESIGN_ITERATIONS = 3

# 枚举容错：模型常给出非标准值（如 "push_in" / "close-up" / "OTS"）。
_SHOT_TYPES = {"extreme_wide", "wide", "medium", "close_up", "extreme_close_up", "over_shoulder", "pov"}
_CAMERA_TYPES = {"static", "pan", "tilt", "dolly", "tracking", "crane", "handheld", "zoom", "steady", "orbit"}
# 有实际位移/旋转的运镜（这些必须有 camera_path，否则模型只会瞎动）
_MOVING_CAMERA_TYPES = _CAMERA_TYPES - {"static"}
_CAMERA_SPEEDS = {"slow", "medium", "fast"}
_PACINGS = {"slow", "medium", "fast", "variable"}
_SHOT_ALIASES = {
    "wide_shot": "wide", "full": "wide", "full_shot": "wide", "wide_angle": "wide",
    "establishing": "wide", "establishing_shot": "wide", "long_shot": "wide",
    "medium_shot": "medium", "mid": "medium", "mid_shot": "medium",
    "closeup": "close_up", "close": "close_up", "reaction": "close_up", "insert": "close_up",
    "extreme_closeup": "extreme_close_up", "ecu": "extreme_close_up",
    "ots": "over_shoulder", "over_the_shoulder": "over_shoulder",
    "pov_shot": "pov", "first_person": "pov",
}
_CAMERA_ALIASES = {
    "push": "dolly", "push_in": "dolly", "pull": "dolly", "pull_out": "dolly",
    "dolly_in": "dolly", "dolly_out": "dolly", "track": "tracking", "follow": "tracking",
    "zoom_in": "zoom", "zoom_out": "zoom", "fixed": "static", "stable": "steady",
    "hand_held": "handheld", "handheld_camera": "handheld", "crane_up": "crane",
    "orbit_shot": "orbit", "arc": "orbit", "revolve": "orbit", "rotate_around": "orbit",
}


def _pick_enum(value: Any, allowed: set[str], aliases: dict[str, str], default: str) -> str:
    """把模型给的值规整到枚举内；不认识就用默认值兜底。"""
    v = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    if v in allowed:
        return v
    return aliases.get(v, default)



class DirectorAgent(CrewAgent):
    """导演 Agent：将剧本拆解为镜头方案。"""

    name = "director"
    label = "导演"
    emoji = "🎬"

    def run(self, script: Script, *, scene_ids: list[str] | None = None, **kwargs: Any) -> CrewTaskResult:
        """执行场景拆解。

        Args:
            script: 完整剧本。
            scene_ids: 指定要拆解的场景 ID 列表；None = 全部。

        Returns:
            CrewTaskResult.data = list[SceneBreakdown]
        """
        if not self.llm.available:
            return self._fallback(script, scene_ids)

        # 筛选目标场景
        targets = script.scenes
        if scene_ids:
            targets = [sc for sc in script.scenes if sc.id in scene_ids]

        if not targets:
            return CrewTaskResult(success=False, summary="没有找到目标场景")

        # 有界重做循环：先拆解 → 连续性校验 → 有问题把 critique 回喂模型重拆。
        critique: list[str] = []
        last: list[SceneBreakdown] | None = None
        for _ in range(MAX_DESIGN_ITERATIONS):
            user_prompt = self._build_prompt(script, targets)
            if critique:
                user_prompt += (
                    "\n\n上一版分镜的连续性校验发现以下问题，请修正后重新输出：\n"
                    + "\n".join(f"- {c}" for c in critique)
                )
            try:
                raw = self._invoke_json(director_system(), user_prompt)
                breakdowns = self._parse_breakdowns(raw)
            except Exception as e:  # noqa: BLE001
                log.warning("导演 Agent 失败：%s", e)
                return CrewTaskResult(success=False, summary=f"导演工作失败：{e}", errors=[str(e)])
            last = breakdowns
            critique = self._validate_continuity(breakdowns)
            if not critique:
                summary = f"导演完成 {len(breakdowns)} 个场景的镜头拆解，共 {sum(len(b.shots) for b in breakdowns)} 个镜头"
                return CrewTaskResult(data=breakdowns, summary=summary)

        total = sum(len(b.shots) for b in last) if last else 0
        summary = f"导演完成拆解（共 {total} 镜），但连续性校验仍待完善：{critique[0] if critique else ''}"
        return CrewTaskResult(data=last, summary=summary, errors=critique)

    def _validate_continuity(self, breakdowns: list[SceneBreakdown]) -> list[str]:
        """确定性校验分镜（不靠固定镜头数，只查结构自洽、生成器可行性与戏剧结构）。

        检查项：
          1. 同场景多镜必须指定 reference_group，才能共享环境参考图；
          2. chain_from 只能接力到更早的镜头（不悬空、不自指、不向后指）；
          3. 单镜时长必须落在目标模型单次生成的可行区间（默认 4–15 秒）；
          4. 非首镜必须填写 cut_reason（写不出切镜理由就该合并）；
          5. 相邻镜头不应是同一个人的重复面部特写（AI 视频里最伤的重复切镜）；
          6. 运动镜头必须写 camera_path——写不出轨迹，模型就会自己乱动；
          7-10. 戏剧结构审计（先戏剧，后语法）：三工作 function、最终画面 final_frame、
             细节律三细节、场景五锚点——由 dramaturgy.audit_breakdowns 提供。
        """
        issues: list[str] = []
        all_orders = {s.order for bd in breakdowns for s in bd.shots}
        for bd in breakdowns:
            scene_shots = sorted(bd.shots, key=lambda s: s.order)
            groups = {s.reference_group for s in scene_shots if s.reference_group}
            if len(scene_shots) > 1 and not groups:
                issues.append(
                    f"场景 {bd.scene_id} 有 {len(scene_shots)} 个镜头但都没有 reference_group，"
                    "请给同场景镜头统一分组（硬切新地点可另起分组）以共享环境参考图"
                )
            prev = None
            for s in scene_shots:
                # 3) 时长必须在模型可行区间内
                if s.duration_sec < 4.0 or s.duration_sec > 15.0:
                    issues.append(
                        f"镜头 {s.id} 的时长 {s.duration_sec}s 超出生成器可行区间（4–15 秒），请调整"
                    )
                # 6) 运动镜头必须有运镜轨迹（固定机位不需要）
                if s.camera.type in _MOVING_CAMERA_TYPES and not s.camera.path.strip():
                    issues.append(
                        f"镜头 {s.id} 用了 {s.camera.type} 运镜却没有写 camera_path："
                        "请写清镜头从哪出发、到哪停下、相对主体的距离与机位高度怎么变，"
                        "写不出来就改成 static"
                    )
                # 4) 非首镜要说明为什么必须切
                if prev is not None and not str(s.cut_reason or "").strip():
                    issues.append(
                        f"镜头 {s.id} 没有填写 cut_reason：只有时间跳变/地点切换/无可回避的戏剧切口才允许切镜，"
                        "否则请合并进上一个镜头"
                    )
                # 5) 相邻重复的同一主体特写
                if prev is not None and s.subject.strip() and s.subject.strip() == str(prev.subject).strip():
                    issues.append(
                        f"镜头 {s.id} 与上一镜是同一主体（{s.subject}）的重复特写，"
                        "除非有强戏剧理由，否则合并成一个镜头"
                    )
                # 2) 接力只能指向更早的镜头
                if s.chain_from is not None:
                    if s.chain_from not in all_orders:
                        issues.append(f"镜头 {s.id} 的 chain_from={s.chain_from} 指向不存在的镜头")
                    elif s.chain_from >= s.order:
                        issues.append(f"镜头 {s.id} 的 chain_from={s.chain_from} 不是前序镜头，首帧无法接力（只能链到更早的镜头）")
                prev = s
        # 7-10) 戏剧结构审计：三工作 / 最终画面 / 三细节 / 五锚点（先戏剧，后语法）
        issues.extend(audit_breakdowns(breakdowns))
        return issues

    def _build_prompt(self, script: Script, targets: list) -> str:
        char_map = {c.id: c.name for c in script.characters}
        loc_map = {loc.id: loc.name for loc in script.locations}

        parts = [
            f"剧本：《{script.title}》",
            f"梗概：{script.logline}",
            f"主题：{'、'.join(script.themes)}",
            f"人物：{'、'.join(c.name + '(' + (c.role or '未定') + ')' for c in script.characters)}",
            "",
            "请为以下场景设计镜头方案：",
        ]

        for sc in targets:
            loc_name = loc_map.get(sc.location_id, sc.location_id)
            char_names = "、".join(char_map.get(cid, cid) for cid in sc.characters)
            parts.append(f"\n--- {sc.id} {sc.title} ---")
            parts.append(f"地点：{loc_name}　时间：{sc.time or '未定'}")
            parts.append(f"人物：{char_names}")
            parts.append(f"目的：{sc.purpose}")
            parts.append(f"冲突：{sc.conflict}")

            if sc.entry_state:
                parts.append(f"入口状态：{sc.entry_state}")
            if sc.exit_state:
                parts.append(f"出口状态：{sc.exit_state}")

            parts.append("节拍：")
            for b in sc.beats:
                if b.type == "action":
                    parts.append(f"  [动作] {b.text}")
                elif b.type == "dialogue":
                    name = char_map.get(b.speaker, b.speaker) if b.speaker else "?"
                    emo = f"（{b.emotion}）" if b.emotion else ""
                    parts.append(f"  [对白] {name}{emo}：{b.line}")
                elif b.type == "cue":
                    parts.append(f"  [提示] {b.text}")

        return "\n".join(parts)

    def _parse_breakdowns(self, raw: Any) -> list[SceneBreakdown]:
        """将 LLM JSON 输出解析为 SceneBreakdown 列表。

        模型给的是「场景内局部 order」（每场都从 0 开始），而接力/参考逻辑需要
        全片唯一的全局 order。这里统一重编号，并把 chain_from 从局部编号映射到全局。
        """
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            raise ValueError(f"期望数组，得到 {type(raw)}")

        breakdowns: list[SceneBreakdown] = []
        next_order = 0
        for item in raw:
            scene_id = item.get("scene_id", "")
            shots_in = sorted(item.get("shots", []), key=lambda x: x.get("order", 0))

            # 第一遍：局部 order -> 全局 order
            local_to_global: dict[Any, int] = {}
            for idx, s in enumerate(shots_in):
                local_to_global[s.get("order", idx)] = next_order
                next_order += 1

            # 第二遍：构造 Shot，chain_from 映射到全局编号
            shots: list[Shot] = []
            for idx, s in enumerate(shots_in):
                direction = str(s.get("camera_direction") or "").strip() or None
                cam = CameraMovement(
                    type=_pick_enum(s.get("camera_type"), _CAMERA_TYPES, _CAMERA_ALIASES, "static"),
                    direction=direction,
                    speed=_pick_enum(s.get("camera_speed"), _CAMERA_SPEEDS, {}, "medium"),
                    path=str(s.get("camera_path") or "").strip(),
                    height=str(s.get("camera_height") or "").strip(),
                )
                g_order = local_to_global[s.get("order", idx)]
                chain = self._coerce_chain(s.get("chain_from"))
                if chain is not None:
                    # 模型在场景内用局部 order 接力：映射到全局；映射不到则丢弃。
                    chain = local_to_global.get(chain)
                shot = Shot(
                    id=f"shot_{scene_id or 'scene_000'}_{g_order:03d}",
                    scene_id=scene_id,
                    order=g_order,
                    shot_type=_pick_enum(s.get("shot_type"), _SHOT_TYPES, _SHOT_ALIASES, "medium"),
                    camera=cam,
                    subject=s.get("subject", ""),
                    action=s.get("action", ""),
                    dialogue_ref=s.get("dialogue_ref"),
                    # 模型偶尔给出 0.8 这类非法时长，钳制到 Shot 允许区间。
                    duration_sec=min(30.0, max(1.0, float(s.get("duration_sec") or 5.0))),
                    lighting=s.get("lighting"),
                    mood=s.get("mood"),
                    spatial=str(s.get("spatial") or "").strip(),
                    background_action=str(s.get("background_action") or "").strip(),
                    cut_reason=str(s.get("cut_reason") or ""),
                    # 三工作规则：非法值一律置空，交给校验环节批评重拆。
                    function=str(s.get("function") or "").strip() if str(s.get("function") or "").strip() in SHOT_FUNCTIONS else "",
                    final_frame=str(s.get("final_frame") or "").strip(),
                    reference_group=str(s.get("reference_group") or ""),
                    chain_from=chain,
                )
                shots.append(shot)

            anchors_raw = item.get("anchors")
            if isinstance(anchors_raw, SceneAnchors):
                anchors = anchors_raw
            elif isinstance(anchors_raw, dict):
                # 模型可能多给键/给错类型：只收五锚点字段，宽松收场。
                anchors = SceneAnchors(
                    **{k: str(v or "") for k, v in anchors_raw.items() if k in SceneAnchors.model_fields}
                )
            else:
                anchors = SceneAnchors()
            breakdown = SceneBreakdown(
                scene_id=scene_id,
                director_notes=item.get("director_notes", ""),
                visual_approach=item.get("visual_approach", ""),
                pacing=_pick_enum(item.get("pacing"), _PACINGS, {}, "medium"),
                key_moments=item.get("key_moments", []),
                anchors=anchors,
                shots=shots,
            )
            breakdowns.append(breakdown)

        return breakdowns

    @staticmethod
    def _coerce_chain(value: Any) -> int | None:
        """把模型给的 chain_from 规整为 int 或 None。"""
        if value is None or value == "" or str(value).strip().lower() in {"null", "none"}:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    def _fallback(self, script: Script, scene_ids: list[str] | None) -> CrewTaskResult:
        """无模型时的回退：为每个场景生成最少 1 个镜头。"""
        targets = script.scenes
        if scene_ids:
            targets = [sc for sc in script.scenes if sc.id in scene_ids]

        breakdowns: list[SceneBreakdown] = []
        for sc in targets:
            shot = Shot(
                id=f"shot_{sc.id}_001",
                scene_id=sc.id,
                order=0,
                shot_type="medium",
                camera=CameraMovement(type="static"),
                subject=sc.title,
                action=sc.purpose,
                duration_sec=5.0,
                reference_group=sc.id,  # 单镜场景也挂一个分组，便于后续扩展
            )
            breakdown = SceneBreakdown(
                scene_id=sc.id,
                director_notes="（无模型回退：默认中景固定镜头）",
                pacing="medium",
                shots=[shot],
            )
            breakdowns.append(breakdown)

        return CrewTaskResult(
            data=breakdowns,
            summary=f"（无模型）为 {len(breakdowns)} 个场景生成默认镜头方案",
        )


def run_director(llm: LLM, script: Script, *, scene_ids: list[str] | None = None) -> CrewTaskResult:
    """快捷入口：执行导演场景拆解。"""
    agent = DirectorAgent(llm)
    return agent.run(script, scene_ids=scene_ids)
