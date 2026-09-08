# =====================================================================
# producer.py —— 制片人 Agent
#
# 职责：全局协调、质量把控、进度追踪
# 输入：所有 Agent 的产出
# 输出：质量报告 + 进度状态
#
# 制片人检查各阶段产出是否达标，给出改进建议。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from ..domain import SceneBreakdown, Script, Shot, StyleGuide
from ..llm import LLM
from .base import CrewAgent, CrewTaskResult

log = logging.getLogger(__name__)

PRODUCER_SYSTEM = """你是影视制片人，负责全局质量把控。

根据剧本、镜头方案、风格指南、视频 Prompt 的完成情况，给出综合质量评估。

评估维度（每项 1-10 分）：
1. 剧本完整性：场景、人物、冲突是否完整
2. 镜头设计：镜头类型和运镜是否丰富、节奏是否合理
3. 风格统一性：视觉风格是否统一、是否与剧本情绪匹配
4. Prompt 质量：视频 Prompt 是否具体、是否可执行
5. 整体可行性：方案是否可在目标预算/时间内完成

输出 JSON：
```json
{
  "scores": {
    "script": 8,
    "shots": 7,
    "style": 9,
    "prompts": 6,
    "feasibility": 8
  },
  "total": 7.6,
  "issues": ["第3场戏镜头过少，建议增加", "部分 Prompt 过于笼统"],
  "suggestions": ["增加特写镜头来强化情绪", "为环境描述添加更多光线细节"]
}
```
"""


class ProducerAgent(CrewAgent):
    """制片人 Agent：全局质量把控。"""

    name = "producer"
    label = "制片人"
    emoji = "🏢"

    def run(
        self,
        script: Script,
        *,
        breakdowns: list[SceneBreakdown] | None = None,
        style_guide: StyleGuide | None = None,
        shots: list[Shot] | None = None,
        **kwargs: Any,
    ) -> CrewTaskResult:
        """执行质量评估。

        Args:
            script: 当前剧本。
            breakdowns: 导演的场景拆解。
            style_guide: 美术指导的风格指南。
            shots: 含 video_prompt 的镜头列表。

        Returns:
            CrewTaskResult.data = {"scores": {...}, "total": float, "issues": [...], "suggestions": [...]}
        """
        if not self.llm.available:
            return self._fallback(breakdowns, style_guide, shots)

        user_prompt = self._build_prompt(script, breakdowns, style_guide, shots)

        try:
            raw = self._invoke_json(PRODUCER_SYSTEM, user_prompt)
            total = raw.get("total", 0)
            issues = raw.get("issues", [])
            return CrewTaskResult(
                data=raw,
                summary=f"制片人评分：{total}/10，{len(issues)} 项问题",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("制片人 Agent 失败：%s", e)
            return CrewTaskResult(success=False, summary=f"制片人评估失败：{e}", errors=[str(e)])

    def _build_prompt(
        self,
        script: Script,
        breakdowns: list[SceneBreakdown] | None,
        style_guide: StyleGuide | None,
        shots: list[Shot] | None,
    ) -> str:
        parts = [
            f"剧本：《{script.title}》",
            f"梗概：{script.logline}",
            f"场景数：{len(script.scenes)}",
            f"人物数：{len(script.characters)}",
            "",
        ]

        if breakdowns:
            total_shots = sum(len(b.shots) for b in breakdowns)
            parts.append(f"镜头方案：{len(breakdowns)} 个场景，{total_shots} 个镜头")
            for bd in breakdowns[:3]:
                parts.append(f"  {bd.scene_id}：{len(bd.shots)} 镜，节奏 {bd.pacing}")
            parts.append("")

        if style_guide:
            parts.append(f"风格指南：{style_guide.lighting_style} | {style_guide.camera_style}")
            parts.append(f"  色彩：{'、'.join(style_guide.color_palette[:5])}")
            parts.append(f"  角色造型：{len(style_guide.character_appearances)} 个")
            parts.append("")

        if shots:
            prompt_count = sum(1 for s in shots if s.video_prompt)
            parts.append(f"镜头数：{len(shots)}，已有 Prompt：{prompt_count}")
            parts.append("")

        return "\n".join(parts)

    def _fallback(
        self,
        breakdowns: list[SceneBreakdown] | None,
        style_guide: StyleGuide | None,
        shots: list[Shot] | None,
    ) -> CrewTaskResult:
        """无模型时的基础评估。"""
        scores = {
            "script": 5,
            "shots": 5 if breakdowns else 0,
            "style": 5 if style_guide else 0,
            "prompts": 5 if shots and any(s.video_prompt for s in shots) else 0,
            "feasibility": 5,
        }
        issues = []
        if not breakdowns:
            issues.append("未完成镜头拆解")
        if not style_guide:
            issues.append("未完成风格指南")
        if not shots:
            issues.append("未生成视频 Prompt")

        total = sum(scores.values()) / len(scores)
        return CrewTaskResult(
            data={"scores": scores, "total": total, "issues": issues, "suggestions": []},
            summary=f"（无模型）基础评估：{total:.1f}/10，{len(issues)} 项缺失",
        )


def run_producer(
    llm: LLM,
    script: Script,
    *,
    breakdowns: list[SceneBreakdown] | None = None,
    style_guide: StyleGuide | None = None,
    shots: list[Shot] | None = None,
) -> CrewTaskResult:
    """快捷入口：执行制片人质量评估。"""
    agent = ProducerAgent(llm)
    return agent.run(script, breakdowns=breakdowns, style_guide=style_guide, shots=shots)
