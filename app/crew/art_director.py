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
from ..skills import render_skill
from .base import CrewAgent, CrewTaskResult

log = logging.getLogger(__name__)


def art_system(language: str = "zh") -> str:
    """美术指导的系统提示词（内容在 app/skills/style-guide/SKILL.md）。"""
    lang_note = (
        "所有描述用简体中文写（目标视频模型原生支持中文）"
        if language == "zh"
        else "Write every description in English"
    )
    return render_skill("style-guide", lang_note=lang_note)
    return (
        "你是影视美术指导，负责为整部作品建立统一的视觉语言。\n\n"
        "你要产出五样东西：\n"
        "1. **色彩方案**：3-5 个主色调（hex 格式），与剧本情绪匹配。\n"
        "2. **光线风格**：整体光线基调（如「低调暖光」「高对比冷光」）。\n"
        "3. **摄影风格** `camera_style`：全片的摄影**身份**，写清不会与具体镜头打架的那些部分——\n"
        "   · 视点（**取景语法全片统一为客观机位**，禁止写「以某人主观视点为主、偶尔退为旁观者」"
        "这类自相矛盾的视点切换，视点摇摆会让每个镜头的取景都不稳定）；\n"
        "   · 机位高度的总体倾向（如「大致在坐姿视线齐平，偶尔略高俯看」）；\n"
        "   · 运动质感（**必须保留真实拍摄的呼吸感**：细微的手持浮动、镜头偶尔被前景的人或物"
        "短暂遮挡、快速运镜后有短暂的失焦再合焦；不要写成零瑕疵的机械运动）。\n"
        "   **⚠️ 绝对不要列举具体运镜方式**（不要写「跟随/横移/推近/环绕/摇移/升降」这类清单，"
        "也不要写「以缓慢横移、推近、推拉为主」）。原因：这段描述会**逐字拼进每一个镜头**，"
        "列举运镜等于给每个镜头同时下三四种运动的指令——而每个镜头本来就只有一种运镜，"
        "模型收到的是互相打架的指令。\n"
        "   · ✅ 正例：「客观旁观视点，机位高度大致与坐姿视线齐平，运动克制，"
        "保留细微的手持浮动与偶发的前景遮挡与短暂失焦」\n"
        "   · ❌ 反例：「以固定机位和极缓慢的横移、推近为主，跟随人物时轻微提前或滞后半拍」\n"
        "   本片每个镜头具体怎么动，由导演与摄影指导按镜头内容决定，不由你在这里规定。\n"

        "4. **角色造型** `character_appearances`：【以人物名称为键】，给出每个角色的固定外貌与服装描述。\n"
        "   这份描述会被逐字复用到每一个出现该角色的镜头，所以必须稳定、具体、可复用"
        "（年龄、性别、发型、服装、体态、辨识特征），不要写成剧情或性格。\n"
        "   **按写实人物公式写，防止塑料 AI 脸**：[年龄/性别] + [肤色肤质（真实毛孔与皮肤纹理，"
        "可带雀斑/瑕疵）] + [3-4 个具体面部细节（眼型、眉骨、鼻梁、下颌线）] + [视线/神态] + "
        "[发型发色] + [衣着面料] + [体型气质]。面部细节要具体到五官，不要只写气质词——"
        "气质词渲染不出来，五官细节才渲染得出来。\n"
        "   服装只写**纯视觉细节**（颜色 / 款式 / 材质 / 配件），**禁止出现身份与职业词**"
        "（如「刑警夹克」「警服」「白大褂」）——视频模型会把身份词直接执行成制服形象，"
        "让便装人物穿上整套制服；要体现职业感就写具体单品（深藏青色立领夹克、腰间挂对讲机），"
        "不点名职业。\n"
        "5. **环境描述** `environment_descriptions`：【以地点名称为键】，给出每个场景的固定环境描述。\n"
        "   同样会被逐字复用，要写地点、空间特征、材质、光线来源、关键道具。\n"
        "   **关键光源必须写清方向与相对位置**（光从哪儿来、打在什么地方、人物站在光里还是背光），"
        "下游每个镜头的光影描述都以此为准，避免出现「光永远跟着人脸走」的假光。\n"
        "   **环境会表演**：每个地点挑一个能承载本场情绪的「环境压力」细节写进描述"
        "（如雨痕、闪烁的顶灯、湿沥青、水壶蒸汽、空调嗡鸣）——天气和环境是角色，"
        "它们放大人物状态，比任何情绪形容词都有效。\n"
        "   若该地点是公共场所，再补一句这里**常驻的背景人群构成**"
        "（有哪些身份的人、大致在做什么），供各镜头的背景人物描述复用。\n\n"
        "6. **五样产出里一律不写否定句**（不要出现「没有」「不」「避免」「禁止」「不是」"
        "这类词）。视频模型会把被否定的内容照画出来——「避免均匀平光」会被画成平光，"
        "「眼睛没有看任何地方」会被画成在注视。这五样产出都会被**逐字复制进每一个镜头**，"
        "一处否定会污染全片。不想要的效果用正向写法表达：「低调侧光，脸部一侧沉进阴影」"
        "而不是「避免均匀平光」；「目光涣散，焦点落在虚空处」而不是「眼睛没有看任何地方」。"
        "不需要出现的东西直接不提。\n\n"
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

    def run(
        self,
        script: Script,
        *,
        director_notes: str = "",
        language: str = "zh",
        visual_style: str | None = None,
        **kwargs: Any,
    ) -> CrewTaskResult:
        """生成视觉风格指南。

        Args:
            script: 完整剧本。
            director_notes: 导演的额外创意意图。
            language: 描述语言（zh / en），与目标视频模型对齐。
            visual_style: 项目画风（realistic/anime/3d/ink）。画风决定角色造型
                该怎么写——实拍写服装材质与年代感，二次元写发色、瞳色、描边与
                上色方式；同一段「外貌描述」在两种画风下不能通用。

        Returns:
            CrewTaskResult.data = StyleGuide
        """
        if not self.llm.available:
            return self._fallback(script, visual_style)

        user_prompt = self._build_prompt(script, director_notes, visual_style)
        try:
            raw = self._invoke_json(art_system(language), user_prompt)
            guide = self._parse_guide(raw, visual_style)
            summary = (
                f"美术指导完成风格指南：{len(guide.color_palette)} 色、"
                f"{len(guide.character_appearances)} 角色造型、{len(guide.environment_descriptions)} 场景"
            )
            return CrewTaskResult(data=guide, summary=summary)
        except Exception as e:  # noqa: BLE001
            log.warning("美术指导 Agent 失败：%s", e)
            return CrewTaskResult(success=False, summary=f"美术指导工作失败：{e}", errors=[str(e)])

    def _build_prompt(self, script: Script, director_notes: str, visual_style: str | None = None) -> str:
        from ..pipeline.visual_styles import get_visual_style

        spec = get_visual_style(visual_style)
        parts = [
            f"剧本：《{script.title}》",
            f"梗概：{script.logline}",
            f"类型：{script.adaptation.type if script.adaptation else '未定'}",
            f"主题：{'、'.join(script.themes)}",
            f"画风：{spec['label']}——{spec['render_note']}",
            "角色造型必须按这个画风来写（"
            + ("写实时写服装材质、年代感、面部细节；"
               if spec["voice_pool"] == "realistic"
               else "二次元/动画时写发色、瞳色、发型轮廓、服装配色与描边风格；")
            + "不要写成另一种画风的描述）。",
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
    def _parse_guide(raw: dict[str, Any], visual_style: str | None = None) -> StyleGuide:
        chars = raw.get("character_appearances") or {}
        envs = raw.get("environment_descriptions") or {}
        return StyleGuide(
            color_palette=raw.get("color_palette", []) or [],
            lighting_style=str(raw.get("lighting_style") or ""),
            camera_style=str(raw.get("camera_style") or ""),
            # 画风以项目设定为准；模型给的只作兜底（它常把 anime 写成 "动漫风"）。
            visual_style=visual_style or raw.get("visual_style") or "realistic",
            visual_references=raw.get("visual_references", []) or [],
            character_appearances={str(k): str(v) for k, v in chars.items() if v} if isinstance(chars, dict) else {},
            environment_descriptions={str(k): str(v) for k, v in envs.items() if v} if isinstance(envs, dict) else {},
        )

    @staticmethod
    def _fallback(script: Script, visual_style: str | None = None) -> CrewTaskResult:
        guide = StyleGuide(
            color_palette=["#1a1a2e", "#16213e", "#0f3460", "#e94560"],
            lighting_style="自然光为主",
            camera_style="稳定拍摄",
            visual_style=visual_style or "realistic",
        )
        return CrewTaskResult(data=guide, summary="（无模型回退）生成默认风格指南")


def run_art_director(
    llm: LLM,
    script: Script,
    *,
    director_notes: str = "",
    language: str = "zh",
    visual_style: str | None = None,
) -> CrewTaskResult:
    """快捷入口：执行美术指导风格指南生成。"""
    agent = ArtDirectorAgent(llm)
    return agent.run(script, director_notes=director_notes, language=language,
                     visual_style=visual_style)
