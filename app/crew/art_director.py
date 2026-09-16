# =====================================================================
# art_director.py —— 美术指导 Agent（视觉锚的唯一来源）
#
# 职责：产出全局视觉指南，其中的「角色造型」与「环境描述」是全片视觉一致性的
# **单一事实来源**（single source of truth）——下游提示词构建会逐字复用它，
# 不再各写各的，从根上避免同一角色/同一场景在不同镜头里长得不一样。
#
# 键约定：
#   - character_appearances：以【人物名】为键（不是 id），方便提示词直接查表；
#   - environment_descriptions：以【地点名】为键。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from ..domain import Script, StyleGuide
from ..llm import LLM
from .base import CrewAgent, CrewTaskResult

log = logging.getLogger(__name__)


def art_system(language: str = "zh") -> str:
    lang_note = (
        "所有描述用简体中文写（目标视频模型原生支持中文）"
        if language == "zh"
        else "Write every description in English"
    )
    return (
        "你是影视美术指导，负责为整部作品建立统一的视觉语言。\n\n"
        "你要产出五样东西：\n"
        "1. **色彩方案**：3-5 个主色调（hex 格式），与剧本情绪匹配。\n"
        "2. **光线风格**：整体光线基调（如「低调暖光」「高对比冷光」）。\n"
        "3. **摄影风格** `camera_style`：整体摄影手法（如「手持纪实」「稳定推拉」），并写清本片的运镜语法——"
        "摄影机当作观众的眼睛，机位高度大致在哪儿、习惯怎么移动（跟随/环绕/升降）、运动节奏如何。"
        "**必须保留真实拍摄的呼吸感**：跟随人物时略微提前或滞后、镜头偶尔被前景的人或物短暂遮挡、"
        "快速运镜后有短暂的失焦再合焦；这些是质感，不要写成零瑕疵的机械运动。这段描述会拼进每个镜头。"
        "**取景语法全片统一为客观机位**，禁止写「以某人主观视点为主、偶尔退为旁观者」这类"
        "自相矛盾的视点切换——视点摇摆会让每个镜头的取景都不稳定。\n"
        "4. **角色造型** `character_appearances`：【以人物名称为键】，给出每个角色的固定外貌与服装描述。\n"
        "   这份描述会被逐字复用到每一个出现该角色的镜头，所以必须稳定、具体、可复用"
        "（年龄、性别、发型、服装、体态、辨识特征），不要写成剧情或性格。\n"
        "   服装只写**纯视觉细节**（颜色 / 款式 / 材质 / 配件），**禁止出现身份与职业词**"
        "（如「刑警夹克」「警服」「白大褂」）——视频模型会把身份词直接执行成制服形象，"
        "让便装人物穿上整套制服；要体现职业感就写具体单品（深藏青色立领夹克、腰间挂对讲机），"
        "不点名职业。\n"
        "5. **环境描述** `environment_descriptions`：【以地点名称为键】，给出每个场景的固定环境描述。\n"
        "   同样会被逐字复用，要写地点、空间特征、材质、光线来源、关键道具。\n"
        "   **关键光源必须写清方向与相对位置**（光从哪儿来、打在什么地方、人物站在光里还是背光），"
        "下游每个镜头的光影描述都以此为准，避免出现「光永远跟着人脸走」的假光。\n"
        "   若该地点是公共场所，再补一句这里**常驻的背景人群构成**"
        "（有哪些身份的人、大致在做什么），供各镜头的背景人物描述复用。\n\n"
        f"注意：{lang_note}；键必须用剧本里出现的人物名 / 地点名；风格要统一，不能各场割裂。\n\n"
        "输出 JSON：\n"
        "```json\n"
        "{\n"
        '  "color_palette": ["#1a1a2e", "#16213e", "#e94560"],\n'
        '  "lighting_style": "低调暖光为主，关键场景冷暖对比",\n'
        '  "camera_style": "稳定为主，关键处缓慢推近",\n'
        '  "visual_references": ["film noir aesthetic"],\n'
        '  "character_appearances": {"齐夏": "……固定外貌描述……", "人羊": "……"},\n'
        '  "environment_descriptions": {"密闭房间": "……固定环境描述……"}\n'
        "}\n"
        "```"
    )


class ArtDirectorAgent(CrewAgent):
    """美术指导 Agent：产出风格指南（视觉锚的唯一来源）。"""

    name = "art_director"
    label = "美术指导"
    emoji = "🎨"

    def run(self, script: Script, *, director_notes: str = "", language: str = "zh", **kwargs: Any) -> CrewTaskResult:
        """生成视觉风格指南。

        Args:
            script: 完整剧本。
            director_notes: 导演的额外创意意图。
            language: 描述语言（zh / en），与目标视频模型对齐。

        Returns:
            CrewTaskResult.data = StyleGuide
        """
        if not self.llm.available:
            return self._fallback(script)

        user_prompt = self._build_prompt(script, director_notes)
        try:
            raw = self._invoke_json(art_system(language), user_prompt)
            guide = self._parse_guide(raw)
            summary = (
                f"美术指导完成风格指南：{len(guide.color_palette)} 色、"
                f"{len(guide.character_appearances)} 角色造型、{len(guide.environment_descriptions)} 场景"
            )
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
            "人物（请以这些名字为键写角色造型）：",
        ]
        for c in script.characters:
            parts.append(f"  - {c.name}（{c.role or '未定'}）：{c.personality or c.goal or '无描述'}")
        parts.append("\n地点（请以这些名字为键写环境描述）：")
        for loc in script.locations:
            parts.append(f"  - {loc.name}：{loc.description or '无描述'}")
        if director_notes:
            parts.append(f"\n导演意图：{director_notes}")
        return "\n".join(parts)

    @staticmethod
    def _parse_guide(raw: dict[str, Any]) -> StyleGuide:
        chars = raw.get("character_appearances") or {}
        envs = raw.get("environment_descriptions") or {}
        return StyleGuide(
            color_palette=raw.get("color_palette", []) or [],
            lighting_style=str(raw.get("lighting_style") or ""),
            camera_style=str(raw.get("camera_style") or ""),
            visual_references=raw.get("visual_references", []) or [],
            character_appearances={str(k): str(v) for k, v in chars.items() if v} if isinstance(chars, dict) else {},
            environment_descriptions={str(k): str(v) for k, v in envs.items() if v} if isinstance(envs, dict) else {},
        )

    @staticmethod
    def _fallback(script: Script) -> CrewTaskResult:
        guide = StyleGuide(
            color_palette=["#1a1a2e", "#16213e", "#0f3460", "#e94560"],
            lighting_style="自然光为主",
            camera_style="稳定拍摄",
        )
        return CrewTaskResult(data=guide, summary="（无模型回退）生成默认风格指南")


def run_art_director(llm: LLM, script: Script, *, director_notes: str = "", language: str = "zh") -> CrewTaskResult:
    """快捷入口：执行美术指导风格指南生成。"""
    agent = ArtDirectorAgent(llm)
    return agent.run(script, director_notes=director_notes, language=language)
