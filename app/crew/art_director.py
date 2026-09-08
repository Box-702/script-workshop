# =====================================================================
# art_director.py —— 美术指导 Agent
#
# 职责：生成视觉风格指南
# 输入：Script（剧本）+ 导演意图
# 输出：StyleGuide（色彩、光线、摄影风格、角色造型、环境描述）
#
# 美术指导根据剧本的类型、时代、情绪，设计统一的视觉语言。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from ..domain import Script, StyleGuide
from ..llm import LLM
from .base import CrewAgent, CrewTaskResult

log = logging.getLogger(__name__)

ART_SYSTEM = """你是影视美术指导，擅长为影视作品设计统一的视觉风格。

你的任务是根据剧本内容，生成一份视觉风格指南，包括：

1. **色彩方案**：3-5 个主色调（hex 格式），与剧本情绪匹配
2. **光线风格**：整体光线基调（如 "低调暖光"、"高对比冷光"）
3. **摄影风格**：整体摄影手法（如 "手持纪实"、"稳定推拉"、"航拍大气"）
4. **角色造型**：每个主要角色的外貌/服装描述（英文，用于 AI 生成）
5. **环境描述**：每个主要场景的环境细节（英文，用于 AI 生成）

输出 JSON：
```json
{
  "color_palette": ["#1a1a2e", "#16213e", "#e94560", "#f5e6cc"],
  "lighting_style": "低调暖光为主，关键场景用冷暖对比",
  "camera_style": "手持为主，关键场景稳定推拉",
  "visual_references": ["film noir aesthetic", "Wong Kar-wai color grading"],
  "character_appearances": {
    "char_zhang": "A middle-aged man with graying temples, wearing a worn leather jacket over a dark shirt, tired but determined eyes",
    "char_li": "A young woman in her 20s, long black hair, simple white blouse, carries a worn canvas bag"
  },
  "environment_descriptions": {
    "loc_office": "A cramped office cubicle with fluorescent overhead lighting, stacks of papers, a half-empty coffee cup, rain visible through the window",
    "loc_alley": "A narrow back alley at night, wet cobblestones reflecting neon signs, steam rising from a vent, dim yellow streetlight"
  }
}
```

注意：
- 角色外貌和环境描述必须用英文（直接用于 AI 图片/视频生成）
- 色彩要与剧本情绪匹配（悬疑用冷暗色调、爱情用暖粉色调等）
- 风格要统一，不能各场戏风格割裂
"""


class ArtDirectorAgent(CrewAgent):
    """美术指导 Agent：生成视觉风格指南。"""

    name = "art_director"
    label = "美术指导"
    emoji = "🎨"

    def run(self, script: Script, *, director_notes: str = "", **kwargs: Any) -> CrewTaskResult:
        """生成视觉风格指南。

        Args:
            script: 完整剧本。
            director_notes: 导演的额外创意意图。

        Returns:
            CrewTaskResult.data = StyleGuide
        """
        if not self.llm.available:
            return self._fallback(script)

        user_prompt = self._build_prompt(script, director_notes)

        try:
            raw = self._invoke_json(ART_SYSTEM, user_prompt)
            guide = self._parse_guide(raw)
            summary = f"美术指导完成风格指南：{len(guide.color_palette)} 色、{len(guide.character_appearances)} 角色造型、{len(guide.environment_descriptions)} 场景"
            return CrewTaskResult(data=guide, summary=summary)
        except Exception as e:  # noqa: BLE001
            log.warning("美术指导 Agent 失败：%s", e)
            return CrewTaskResult(success=False, summary=f"美术指导工作失败：{e}", errors=[str(e)])

    def _build_prompt(self, script: Script, director_notes: str) -> str:
        parts = [
            f"剧本：《{script.title}》",
            f"梗概：{script.logline}",
            f"类型：{script.adaptation.type if script.adaptation else '未定'}",
            f"主题：{'、'.join(script.themes)}",
            "",
            "人物列表：",
        ]
        for c in script.characters:
            parts.append(f"  - {c.name}（{c.role or '未定'}）：{c.personality or c.goal or '无描述'}")

        parts.append("\n场景列表：")
        for sc in script.scenes[:10]:  # 最多 10 个场景避免 token 过多
            parts.append(f"  - {sc.title}：{sc.purpose}")

        if director_notes:
            parts.append(f"\n导演意图：{director_notes}")

        return "\n".join(parts)

    def _parse_guide(self, raw: dict[str, Any]) -> StyleGuide:
        return StyleGuide(
            color_palette=raw.get("color_palette", []),
            lighting_style=raw.get("lighting_style", ""),
            camera_style=raw.get("camera_style", ""),
            visual_references=raw.get("visual_references", []),
            character_appearances=raw.get("character_appearances", {}),
            environment_descriptions=raw.get("environment_descriptions", {}),
        )

    def _fallback(self, script: Script) -> CrewTaskResult:
        """无模型时的回退：生成基础默认风格。"""
        guide = StyleGuide(
            color_palette=["#1a1a2e", "#16213e", "#0f3460", "#e94560"],
            lighting_style="自然光为主",
            camera_style="稳定拍摄",
        )
        return CrewTaskResult(
            data=guide,
            summary="（无模型回退）生成默认风格指南",
        )


def run_art_director(llm: LLM, script: Script, *, director_notes: str = "") -> CrewTaskResult:
    """快捷入口：执行美术指导风格指南生成。"""
    agent = ArtDirectorAgent(llm)
    return agent.run(script, director_notes=director_notes)
