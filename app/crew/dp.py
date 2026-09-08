# =====================================================================
# dp.py —— 摄影指导 Agent
#
# 职责：为每个镜头生成视频生成 Prompt
# 输入：SceneBreakdown[]（导演的镜头方案）+ Script（上下文）+ StyleGuide（风格）
# 输出：更新后的 Shot[]（含 video_prompt 字段）
#
# 摄影指导根据导演意图和镜头设计，将文字描述转化为
# 符合各视频模型最佳实践的英文 Prompt。
# Prompt 结构：[镜头类型] + [运镜] of [主体] [动作] in [环境], [光线], [风格]
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from ..domain import SceneBreakdown, Script, Shot, StyleGuide
from ..llm import LLM
from .base import CrewAgent, CrewTaskResult

log = logging.getLogger(__name__)

DP_SYSTEM = """你是影视摄影指导（DP），擅长将文字镜头描述转化为视频生成 Prompt。

你的任务是为每个镜头编写高质量的视频生成 Prompt（英文），遵循以下结构：

**Prompt 结构**：
[Shot type] [Camera movement] of [Subject] [Action] in [Setting/Environment], [Lighting], [Style/Mood]

**示例**：
- "A medium close-up shot with slow dolly in of a young woman in white dress sitting alone by a rain-streaked window, soft warm interior lighting mixed with cold blue daylight from outside, cinematic 35mm film, melancholic mood"
- "Wide establishing shot with steady pan from left to right of a bustling night market in old Beijing, neon signs reflecting on wet pavement, warm tungsten streetlights, handheld documentary style, lively atmosphere"
- "Extreme close-up of weathered hands trembling while holding a faded photograph, shallow depth of field, soft natural window light from the left, intimate and nostalgic, 85mm lens"

**关键原则**：
1. 永远用英文写 Prompt（即使原剧本是中文）
2. 把中文场景描述翻译成视觉化的英文
3. 镜头类型和运镜要具体（不要用 "camera moves"，用 "slow dolly in"）
4. 光线描述要具体（不要用 "good lighting"，用 "warm tungsten key light from upper left"）
5. 加入摄影风格参考（cinematic 35mm, handheld documentary, anamorphic lens 等）
6. 情绪通过画面元素传达，不要直接写 "sad scene"
7. 每个 Prompt 控制在 50-150 词

输出 JSON 数组：
```json
[
  {
    "shot_id": "shot_scene001_001",
    "video_prompt": "A wide establishing shot with slow crane up revealing..."
  }
]
```
"""


class DPAgent(CrewAgent):
    """摄影指导 Agent：为镜头生成视频 Prompt。"""

    name = "dp"
    label = "摄影指导"
    emoji = "📹"

    def run(
        self,
        script: Script,
        *,
        breakdowns: list[SceneBreakdown] | None = None,
        style_guide: StyleGuide | None = None,
        **kwargs: Any,
    ) -> CrewTaskResult:
        """为镜头生成视频 Prompt。

        Args:
            script: 完整剧本（用于上下文）。
            breakdowns: 导演的场景拆解结果。
            style_guide: 美术指导的风格指南（可选）。

        Returns:
            CrewTaskResult.data = list[Shot]（含 video_prompt）
        """
        if not breakdowns:
            return CrewTaskResult(success=False, summary="没有收到导演的镜头方案")

        # 收集所有需要生成 prompt 的镜头
        all_shots: list[Shot] = []
        for bd in breakdowns:
            all_shots.extend(bd.shots)

        if not all_shots:
            return CrewTaskResult(success=False, summary="镜头方案中没有镜头")

        if not self.llm.available:
            return self._fallback(all_shots, script)

        # 构造 LLM 输入
        user_prompt = self._build_prompt(script, all_shots, style_guide)

        try:
            raw = self._invoke_json(DP_SYSTEM, user_prompt)
            updated_shots = self._apply_prompts(all_shots, raw)
            prompt_count = sum(1 for s in updated_shots if s.video_prompt)
            summary = f"摄影指导为 {prompt_count}/{len(updated_shots)} 个镜头生成了视频 Prompt"
            return CrewTaskResult(data=updated_shots, summary=summary)
        except Exception as e:  # noqa: BLE001
            log.warning("摄影指导 Agent 失败：%s", e)
            return CrewTaskResult(success=False, summary=f"摄影指导工作失败：{e}", errors=[str(e)])

    def _build_prompt(
        self,
        script: Script,
        shots: list[Shot],
        style_guide: StyleGuide | None,
    ) -> str:
        char_map = {c.id: c.name for c in script.characters}
        loc_map = {loc.id: loc.name for loc in script.locations}

        parts = [
            f"剧本：《{script.title}》",
            f"梗概：{script.logline}",
            "",
        ]

        if style_guide:
            parts.append("视觉风格指南：")
            if style_guide.lighting_style:
                parts.append(f"  光线风格：{style_guide.lighting_style}")
            if style_guide.camera_style:
                parts.append(f"  摄影风格：{style_guide.camera_style}")
            if style_guide.color_palette:
                parts.append(f"  主色调：{'、'.join(style_guide.color_palette[:5])}")
            parts.append("")

        parts.append("请为以下镜头生成视频 Prompt：\n")

        for shot in shots:
            scene = next((sc for sc in script.scenes if sc.id == shot.scene_id), None)
            loc_name = ""
            char_names = ""
            if scene:
                loc_name = loc_map.get(scene.location_id, scene.location_id)
                char_names = "、".join(char_map.get(cid, cid) for cid in scene.characters)

            parts.append(f"--- {shot.id} ---")
            parts.append(f"场景：{scene.title if scene else shot.scene_id}")
            parts.append(f"地点：{loc_name}　人物：{char_names}")
            parts.append(f"镜头类型：{shot.shot_type}")
            parts.append(f"运镜：{shot.camera.type}" + (f" ({shot.camera.direction})" if shot.camera.direction else ""))
            parts.append(f"主体：{shot.subject}")
            parts.append(f"动作：{shot.action}")
            if shot.lighting:
                parts.append(f"光线：{shot.lighting}")
            if shot.mood:
                parts.append(f"情绪：{shot.mood}")
            parts.append(f"时长：{shot.duration_sec}秒")
            parts.append("")

        return "\n".join(parts)

    def _apply_prompts(self, shots: list[Shot], raw: Any) -> list[Shot]:
        """将 LLM 生成的 prompt 应用到镜头上。"""
        if isinstance(raw, dict):
            raw = [raw]

        prompt_map: dict[str, str] = {}
        for item in raw:
            if isinstance(item, dict):
                sid = item.get("shot_id", "")
                prompt = item.get("video_prompt", "")
                if sid and prompt:
                    prompt_map[sid] = prompt

        updated: list[Shot] = []
        for shot in shots:
            if shot.id in prompt_map:
                shot.video_prompt = prompt_map[shot.id]
            updated.append(shot)

        return updated

    def _fallback(self, shots: list[Shot], script: Script) -> CrewTaskResult:
        """无模型时的回退：用简单模板生成 prompt。"""
        loc_map = {loc.id: loc.name for loc in script.locations}

        for shot in shots:
            scene = next((sc for sc in script.scenes if sc.id == shot.scene_id), None)
            loc_name = loc_map.get(scene.location_id, "") if scene else ""
            parts = [f"A {shot.shot_type.replace('_', ' ')} shot"]
            if shot.camera.type != "static":
                parts.append(f"with {shot.camera.speed} {shot.camera.type}")
            parts.append(f"of {shot.subject}")
            if shot.action:
                parts.append(shot.action)
            if loc_name:
                parts.append(f"in {loc_name}")
            if shot.lighting:
                parts.append(shot.lighting)
            if shot.mood:
                parts.append(f"{shot.mood} mood")
            shot.video_prompt = ", ".join(parts)

        return CrewTaskResult(
            data=shots,
            summary=f"（无模型回退）为 {len(shots)} 个镜头生成简单 Prompt",
        )


def run_dp(
    llm: LLM,
    script: Script,
    *,
    breakdowns: list[SceneBreakdown] | None = None,
    style_guide: StyleGuide | None = None,
) -> CrewTaskResult:
    """快捷入口：执行摄影指导 Prompt 生成。"""
    agent = DPAgent(llm)
    return agent.run(script, breakdowns=breakdowns, style_guide=style_guide)
