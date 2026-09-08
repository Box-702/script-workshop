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
    SceneBreakdown,
    Script,
    Shot,
)
from ..llm import LLM
from .base import CrewAgent, CrewTaskResult

log = logging.getLogger(__name__)

DIRECTOR_SYSTEM = """你是影视导演，擅长将文字剧本转化为视觉叙事。

你的任务是为每场戏设计镜头方案：
1. 分析每场戏的戏剧目标、情绪弧线、节奏需求
2. 决定镜头数量和类型（远景/中景/近景/特写等）
3. 设计运镜方式（固定/推/拉/摇/移/跟等）
4. 标注关键时刻（情绪转折、冲突爆发、悬念设置）
5. 控制整体节奏：开场紧凑、中段有张有弛、高潮密集

输出要求（JSON 数组，每个元素是一场戏的拆解）：
```json
[
  {
    "scene_id": "scene_001",
    "director_notes": "这场戏是开场，需要快速建立紧张感...",
    "visual_approach": "手持摄影为主，增强临场感...",
    "pacing": "fast",
    "key_moments": ["发现尸体", "第一次对峙", "线索浮现"],
    "shots": [
      {
        "order": 0,
        "shot_type": "wide",
        "camera_type": "handheld",
        "camera_direction": null,
        "camera_speed": "medium",
        "subject": "昏暗的房间全景",
        "action": "镜头缓慢扫过凌乱的现场",
        "dialogue_ref": null,
        "duration_sec": 4.0,
        "lighting": "昏暗，只有一盏台灯",
        "mood": "压抑、不安"
      }
    ]
  }
]
```

shot_type 枚举：extreme_wide, wide, medium, close_up, extreme_close_up, over_shoulder, pov
camera_type 枚举：static, pan, tilt, dolly, tracking, crane, handheld, zoom, steady
camera_speed 枚举：slow, medium, fast
pacing 枚举：slow, medium, fast, variable

注意：
- 每场戏通常 3-8 个镜头，根据戏份重要程度调整
- 对白密集的戏用正反打（over_shoulder）和近景
- 动作戏用远景+特写交替，节奏快
- 抒情戏用慢推/慢拉，节奏缓
- 所有对白引用请使用 beat_xxx 格式的 id
"""


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

        # 构造 LLM 输入
        user_prompt = self._build_prompt(script, targets)

        try:
            raw = self._invoke_json(DIRECTOR_SYSTEM, user_prompt)
            breakdowns = self._parse_breakdowns(raw)
            summary = f"导演完成 {len(breakdowns)} 个场景的镜头拆解，共 {sum(len(b.shots) for b in breakdowns)} 个镜头"
            return CrewTaskResult(data=breakdowns, summary=summary)
        except Exception as e:  # noqa: BLE001
            log.warning("导演 Agent 失败：%s", e)
            return CrewTaskResult(success=False, summary=f"导演工作失败：{e}", errors=[str(e)])

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
        """将 LLM JSON 输出解析为 SceneBreakdown 列表。"""
        if isinstance(raw, dict):
            raw = [raw]
        if not isinstance(raw, list):
            raise ValueError(f"期望数组，得到 {type(raw)}")

        breakdowns: list[SceneBreakdown] = []
        for item in raw:
            shots = []
            for s in item.get("shots", []):
                cam = CameraMovement(
                    type=s.get("camera_type", "static"),
                    direction=s.get("camera_direction"),
                    speed=s.get("camera_speed", "medium"),
                )
                shot = Shot(
                    id=f"shot_{item.get('scene_id', 'xxx')}_{s.get('order', 0):03d}",
                    scene_id=item.get("scene_id", ""),
                    order=s.get("order", 0),
                    shot_type=s.get("shot_type", "medium"),
                    camera=cam,
                    subject=s.get("subject", ""),
                    action=s.get("action", ""),
                    dialogue_ref=s.get("dialogue_ref"),
                    duration_sec=s.get("duration_sec", 5.0),
                    lighting=s.get("lighting"),
                    mood=s.get("mood"),
                )
                shots.append(shot)

            breakdown = SceneBreakdown(
                scene_id=item.get("scene_id", ""),
                director_notes=item.get("director_notes", ""),
                visual_approach=item.get("visual_approach", ""),
                pacing=item.get("pacing", "medium"),
                key_moments=item.get("key_moments", []),
                shots=shots,
            )
            breakdowns.append(breakdown)

        return breakdowns

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
