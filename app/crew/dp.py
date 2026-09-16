# =====================================================================
# dp.py —— 摄影指导 Agent（模型感知的视频提示词构建）
#
# 职责：把「剧本 + 导演镜头方案 + 美术风格指南」组装成「直接喂给视频生成模型」
# 的提示词。这是链路里专门针对视频模型做提示词工程的那一步。
#
# 架构要点（提示词优先 + 单一事实来源）：
#   - 视觉锚的唯一来源是美术指导的 StyleGuide：
#       character_appearances（按人物名） + environment_descriptions（按地点名）
#     本模块【逐字复用】它们拼进每个镜头，杜绝同一角色/场景跨镜漂移。
#   - LLM 只负责本步骤独有的部分：每个镜头出场哪些人 + 这一镜的动作与运镜。
#   - 模型感知：按目标 provider 的方言输出（中文 / 英文）并遵守其时长约束。
#   - 若没有风格指南，退化为由本步骤自己产出环境/人物锚（保证链路仍可跑）。
# =====================================================================

from __future__ import annotations

import logging
import re
from typing import Any

from ..domain import SceneBreakdown, Script, Shot, StyleGuide
from ..llm import LLM
from .base import CrewAgent, CrewTaskResult

log = logging.getLogger(__name__)

# 原生支持中文提示词的模型（其余按英文处理）。
_ZH_PROVIDERS = {"cogvideo", "kling", "minimax"}

# 视觉风格兜底（未提供风格指南时使用）。
_DEFAULT_STYLE = "写实电影质感，色调统一，轻微胶片颗粒，画面稳定。"

# 每个镜头 prompt_body 的写作铁律。
#
# 这些规则解决的是同一类问题：视频模型只能照字面理解文本，凡是没写出来的，
# 它都会自己瞎猜——镜头会无理由漂移、光线会一直黏在脸上、人物之间没有距离感、
# 背景像复制粘贴。把「动作」之外的运镜、光影、空间、背景四类信息都写成文字，
# 生成结果才可控。（沿用导演方案里已经拆好的字段，不要在这里新造设定。）
_BODY_RULES_ZH = """**每个镜头的 prompt_body 要写什么**（这是给视频模型看的唯一文字依据，
没写出来的部分它就会自己乱猜，所以要写得像一份可执行的拍摄指令）：

1. **别只写画面里有什么——动作和运镜都要写**。画面里不只有人物的信息动机，摄影机的
   运动本身也是信息动机。把摄影机理解成一台贴近人物飞行的虚拟无人机，它是观众的
   眼睛：写清楚镜头怎么带观众进入现场，前进 / 后退 / 侧移 / 环绕 / 升降 / 偏航 / 俯仰
   分别怎么走，以及运动规律（起步、刹车、加减速、惯性如何体感）。按导演给的
   camera_path 与 camera_height 写，可以更具体，但不要改成另一种运镜，更不要加码：
   一镜只保留一种主要运动，摄影机保持在主体同一侧（不越轴），镜头结尾停在原景别上——
   结尾推近换构图这类二次变化要删掉。
2. **保留镜头的呼吸感**。真实拍摄时摄影师会略微提前或滞后于人物，允许镜头偶尔被
   前景的人物或物体短暂遮挡，快速运镜之后有短暂的失焦或重新合焦。可以写出这类
   不完美，但不要写"手持剧烈抖动""画面模糊"这种失控的描述。
3. **光影要写方向与相对关系**。写清光从哪个方向来、主光源是什么、人物和光源的相对
   位置，以及镜头运动过程中环境光和人物脸部光发生的变化。避免写成"光永远打在人物
   脸上"——那样人物怎么走光都跟着脸走，画面立刻失真。
4. **空间关系要写清楚**。给主要人物编上号（齐夏1号、人羊2号），写清人物与人物之间的
   相对距离、人物离镜头有多远、离地面有多高，以及运镜从起点到终点这些相对位置
   发生了怎样的变化。空间写实了，人物才不会漂浮在同一层纸面上。
5. **背景人物要有自己的事**。背景人物要有各自独立、不完全同步的生活化行为，写出
   谁在做什么；允许少数人短时间保持静止，不要求所有背景人物持续运动。避免出现
   "所有人都朝同一个方向移动"这类整齐划一的假背景。
6. **只写画面里看得见的东西**：不写旁白、心理活动或小说式描写，也不要写镜头编号、
   剪辑指令、"切到"这类剪辑语言。
7. **接触动作要写成物理过程，但预算只给主事件**。涉及手与道具接触的动作（掀警戒带、推门、
   掀帘子、递东西），只写"掀开带子走过去"这类结果式表述，模型一定会让手和道具互相穿透。
   每个镜头只挑**一个主事件**写物理过程，节拍最多两步（接触 → 完成，或试探 → 完成），
   写清接触点与让位关系（道具从手的哪一侧经过、人物哪个部位在道具的上方还是下方通过）；
   镜头里**其他人物不得再与同一道具发生第二次互动**——两个人先后操作同一道具，模型必然
   把两次互动搅在一起；其余接触动作一笔带过。
8. **只写正向描述，禁止否定句**。"手没有从带子里穿过去""没有碰到头"这类否定式防穿模
   表述，等于把「穿过身体」这个概念喂给模型，它反而会画出来。不想要的东西直接不提；
   必须交代的让位关系，改写成它应该怎样（如「带子从她头顶上方通过」）。
9. **台词不进提示词**。不要把角色说的话写成引用（「说道：『……』」「报告：『……』」）——
   视频模型会把台词渲染成含混的假说话，观众完全听不懂。对白段只写说话的**姿态与口型动机**：
   谁对谁说、语速与情绪、身体朝向与距离、手的动作；声音交给后期配音与对口型。

这一镜只讲一段连贯的动作或一段连贯的对话剧情，不要跨场景跳跃。"""

_BODY_RULES_EN = """**What each shot's prompt_body must contain** (this text is the only
thing the video model sees — anything you leave out, it will invent):

1. **Write the camera move, not just what is in frame.** Camera motion carries meaning
   on its own. Treat the camera as a virtual drone flying close to the subject — it is
   the audience's eyes: state how the move carries the viewer into the scene, how it
   travels (forward / backward / lateral / orbit / rise / descend / yaw / tilt) and its
   motion rules (start, stop, acceleration, inertia). Follow the camera_path and
   camera_height from the shot plan; you may be more specific, but never change the move
   and never escalate it: one primary move per shot, stay on one side of the subject
   (no axis crossing), and end on the original framing — no late push-in that changes
   the shot size.
2. **Keep the lens breathing.** Real operators lead or lag the subject slightly, the
   lens is occasionally blocked by foreground people or objects, and fast moves end with
   a brief loss and recovery of focus. Such imperfection is welcome; uncontrolled
   "violent handheld shake" or "blurry frame" is not.
3. **State light direction and relations.** Where the light comes from, what the key
   source is, how people are positioned relative to it, and how ambient light and facial
   light shift as the camera moves. Never let the light follow the face wherever it goes.
4. **State spatial relations.** Number the main characters (Qi Xia #1, Goat Man #2),
   give their distances from each other, from the camera and from the ground, and how
   those relations change from the start to the end of the move.
5. **Give background extras their own business.** Independent, unsynchronized everyday
   behavior — say who is doing what. A few may stay still for a while; not everyone has
   to keep moving. Avoid a uniformly synchronized background.
6. **Only what is visible on screen**: no narration, inner monologue, novelistic prose,
   shot numbers, cut instructions or editing language.
7. **Describe contact actions as a physical process — budget for the main event only.**
   A result-style phrase ("she lifts the tape and walks through") makes hands and props
   interpenetrate. Pick the ONE main event of the shot, give it at most two beats
   (contact → complete, or test → complete), and state the contact point plus the
   clearance relation (which side of the hand the prop passes, which body part goes
   above/below it). No other character may touch the same prop a second time in this
   shot; every other contact action gets one short clause.
8. **Positive phrasing only — never negations.** "Her hand does not pass through the
   tape" feeds the very concept into the model and it will draw it anyway. Leave out
   what you don't want; phrase clearance as what should happen ("the tape passes above
   her head").
9. **Never put spoken lines into the prompt.** Quoted dialogue gets rendered as mumbled
   fake speech nobody can understand. For dialogue beats, write the acting instead:
   who addresses whom, pace and emotion, body orientation and distance, what the hands
   do. Voice belongs to post-production dubbing and lip-sync.

One shot carries one continuous action or one continuous stretch of dialogue."""

# 导演方案里缺某类调度信息时的补位提示：空值不阻断生成，但要让 LLM 知道
# 「这里确实没写，你可以按剧情补足」，而不是默默漏掉这类信息。
# body 里是否提到了摄影机/镜头——用来判断 LLM 有没有把运镜写进去。
_CAMERA_WORDS = ("镜头", "摄影机", "摄像机", "运镜", "机位", "camera", "lens", "shot")


def _mentions_camera(text: str) -> bool:
    low = text.lower()
    return any(w in low for w in _CAMERA_WORDS)


# 说话动词：紧跟其后的引用几乎一定是台词（招牌/字幕类引用前面的动词是「写着」等）。
_SPEECH_VERBS = ("说", "问", "答", "喊", "叫", "念", "读", "道", "开口", "报告", "低声", "大声", "嘀咕", "嘟囔")
_QUOTE_SPAN = re.compile(r"[「『“\"]([^」』”\"]*)[」』”\"]")


def _strip_spoken_quotes(text: str) -> str:
    """把「跟在说话动词后面的引用台词」从提示词里剥掉。

    视频模型会把被引用的台词渲染成含混的假说话（叽里咕噜），语音应交给后期
    配音；对白信息只保留姿态与口型动机。招牌/字幕类引用（前面是「写着」等）
    不受影响。模型偶尔仍会把台词写进 body，这是提示词规则之外的机械兜底。
    """
    if not text:
        return text
    out: list[str] = []
    last = 0
    for m in _QUOTE_SPAN.finditer(text):
        head = text[max(0, m.start() - 6):m.start()]
        if not any(v in head for v in _SPEECH_VERBS):
            continue
        out.append(text[last:m.start()])
        last = m.end()
    if not out:
        return text
    out.append(text[last:])
    return "".join(out)


_MISSING_HINTS: dict[str, dict[str, str]] = {
    "zh": {
        "camera_path": "（未给镜头轨迹：请按景别与速度补出合理的起点→终点与机位高度）",
        "spatial": "（未给空间关系：请按剧情补足人物间的相对距离、离镜头的远近与离地高度）",
        "background": "（未给背景人物：公共场所请补少量各自独立活动的背景人物，允许有人静止）",
    },
    "en": {
        "camera_path": "(no path given: infer a plausible start → end move and camera height)",
        "spatial": "(no spatial data: infer distances between characters, camera and ground)",
        "background": "(no extras given: add a few independently behaving background people)",
    },
}


def language_for(provider: str, script_language: str) -> str:
    """推断提示词语言：优先看目标模型方言，其次看剧本语言。"""
    p = (provider or "").strip().lower()
    if p in _ZH_PROVIDERS:
        return "zh"
    if p:
        return "en"
    return "zh" if str(script_language or "").lower().startswith("zh") else "en"


def dp_system(*, language: str, provider_label: str, max_duration: float, has_anchors: bool) -> str:
    """按目标模型生成摄影指导的系统提示词。"""
    if language == "zh":
        lang_rule = "用简体中文写（目标模型原生支持中文，中文描述更贴合画面）"
        json_note = "JSON 里的文本字段用中文"
    else:
        lang_rule = "Write the prompt in English"
        json_note = "JSON text fields in English"
    duration_note = f"单个镜头时长上限约 {max_duration:.0f} 秒" if max_duration else "单镜时长遵守镜头方案"

    anchor_rule = (
        "**已提供统一的美术风格指南（环境/人物锚已固定）**：\n"
        "- 环境描述与人物造型由美术指导统一下发，本步骤不要改写它们；\n"
        "- 你只需为每个镜头产出 `characters`（本镜出场人物名）与 `prompt_body`"
        "（本镜画面调度 + 运镜，写法见下面九条）。\n"
        if has_anchors
        else
        "**未提供美术风格指南**：请额外为每个场景产出 `environment`（固定环境描述）"
        "与 `characters`（人物名 -> 固定外貌描述），供本场所有镜头复用。\n"
    )
    body_rules = _BODY_RULES_ZH if language == "zh" else _BODY_RULES_EN
    return (
        "你是影视摄影指导（DP），负责把镜头方案构建成「直接喂给视频生成模型」的提示词。\n\n"
        f"目标模型：{provider_label}\n"
        f"输出语言：{lang_rule}\n"
        f"时长约束：{duration_note}\n\n"
        f"{anchor_rule}\n"
        f"{body_rules}\n\n"
        "**硬性要求**：\n"
        f"- {lang_rule}；{json_note}。\n"
        "- characters 必须是本场人物的子集，只列这一镜画面里真正出现的人。\n"
        "- 不要输出额外说明或 Markdown，只输出 JSON。\n\n"
        "输出 JSON：\n"
        "```json\n"
        '{"scenes": [{"scene_id": "scene_001", '
        '"environment": "（仅有需要时填）", "characters": {"人物名": "（仅有需要时填）"}, '
        '"shots": [{"shot_id": "shot_scene_001_000", "characters": ["人物名"], "prompt_body": "（本镜画面调度 + 运镜）"}]}]}\n'
        "```"
    )


class DPAgent(CrewAgent):
    """摄影指导 Agent：构建模型感知的视频提示词。"""

    name = "dp"
    label = "摄影指导"
    emoji = "📹"

    def run(
        self,
        script: Script,
        *,
        breakdowns: list[SceneBreakdown] | None = None,
        style_guide: StyleGuide | None = None,
        target_provider: str = "",
        provider_label: str = "",
        prompt_language: str = "",
        max_duration: float = 0.0,
        **kwargs: Any,
    ) -> CrewTaskResult:
        """构建视频提示词。"""
        if not breakdowns:
            return CrewTaskResult(success=False, summary="没有收到导演的镜头方案")
        all_shots: list[Shot] = [s for bd in breakdowns for s in bd.shots]
        if not all_shots:
            return CrewTaskResult(success=False, summary="镜头方案中没有镜头")

        language = prompt_language or language_for(target_provider, script.language)
        label = provider_label or (target_provider or "通用模型")
        style = self._style_text(style_guide)
        has_anchors = bool(
            style_guide and (style_guide.character_appearances or style_guide.environment_descriptions)
        )

        if not self.llm.available:
            return self._fallback(all_shots, script, style, language, style_guide)

        user_prompt = self._build_prompt(script, breakdowns, style_guide, language, has_anchors)
        system = dp_system(
            language=language, provider_label=label,
            max_duration=max_duration, has_anchors=has_anchors,
        )
        try:
            raw = self._invoke_json(system, user_prompt)
            updated = self._apply(all_shots, raw, script, style, style_guide, language)
            n = sum(1 for s in updated if s.video_prompt)
            lang_cn = "中文" if language == "zh" else "英文"
            return CrewTaskResult(
                data=updated,
                summary=f"摄影指导为 {n}/{len(updated)} 个镜头构建了{lang_cn}视频提示词（目标模型：{label}）",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("摄影指导 Agent 失败：%s", e)
            return CrewTaskResult(success=False, summary=f"摄影指导工作失败：{e}", errors=[str(e)])

    # ---- 组装 ----

    @staticmethod
    def _style_text(style_guide: StyleGuide | None) -> str:
        """把风格指南压成一句可拼进提示词的话。

        各段先去掉自带的句末标点再拼接，否则会出现「……呼吸感。，#3a4a5a」这种
        句号逗号叠在一起的碎片，拼在每个镜头末尾很难看。
        """
        if not style_guide:
            return _DEFAULT_STYLE

        def _clean(text: str) -> str:
            return str(text).strip().rstrip("。，；;,.")

        bits: list[str] = []
        if style_guide.lighting_style:
            bits.append(_clean(style_guide.lighting_style))
        if style_guide.camera_style:
            bits.append(_clean(style_guide.camera_style))
        if style_guide.color_palette:
            bits.append("主色调 " + "、".join(style_guide.color_palette[:4]))
        return "，".join(b for b in bits if b) or _DEFAULT_STYLE

    def _build_prompt(
        self,
        script: Script,
        breakdowns: list[SceneBreakdown],
        style_guide: StyleGuide | None,
        language: str,
        has_anchors: bool,
    ) -> str:
        """把剧本场景的戏剧上下文 + 镜头方案 + 已有视觉锚交给 LLM。"""
        char_map = {c.id: c.name for c in script.characters}
        loc_map = {loc.id: loc.name for loc in script.locations}
        scene_map = {sc.id: sc for sc in script.scenes}

        parts = [f"剧本：《{script.title}》", f"梗概：{script.logline}", ""]
        if has_anchors and style_guide:
            parts.append("【已固定的视觉锚（不要改写，仅供你写动作时对齐）】")
            if style_guide.environment_descriptions:
                for name, desc in list(style_guide.environment_descriptions.items())[:8]:
                    parts.append(f"  环境·{name}：{desc}")
            if style_guide.character_appearances:
                for name, desc in list(style_guide.character_appearances.items())[:12]:
                    parts.append(f"  人物·{name}：{desc}")
            parts.append("")

        for bd in breakdowns:
            sc = scene_map.get(bd.scene_id)
            parts.append(f"===== 场景 {bd.scene_id} =====")
            if sc:
                parts.append(f"标题：{sc.title}")
                parts.append(f"地点：{loc_map.get(sc.location_id, sc.location_id)}　时间：{sc.time or '未定'}")
                parts.append(f"戏剧目标：{sc.purpose}")
                parts.append(f"冲突：{sc.conflict}")
                names = "、".join(char_map.get(cid, cid) for cid in sc.characters)
                parts.append(f"在场人物：{names}")
                beat_lines: list[str] = []
                for b in sc.beats[:24]:
                    if b.type == "dialogue":
                        beat_lines.append(f"  [对白] {char_map.get(b.speaker or '', b.speaker or '?')}：{b.line}")
                    elif b.type == "action":
                        beat_lines.append(f"  [动作] {b.text}")
                if beat_lines:
                    parts.append("本场节拍：")
                    parts.extend(beat_lines)
            parts.append("")
            hints = _MISSING_HINTS.get(language, _MISSING_HINTS["zh"])
            parts.append("本场镜头方案：")
            for s in sorted(bd.shots, key=lambda x: x.order):
                parts.append(
                    f"  - {s.id} | {s.shot_type} | 运镜 {s.camera.type}"
                    + (f"/{s.camera.direction}" if s.camera.direction else "")
                    + f"/{s.camera.speed}"
                    + f" | 时长 {s.duration_sec:.0f}s"
                )
                parts.append(f"      主体：{s.subject}")
                parts.append(f"      动作：{s.action}")
                # 摄影机轨迹是视频模型能否「跟着走」的关键，缺了就显式点出来。
                if s.camera.type != "static":
                    parts.append(f"      运镜轨迹：{s.camera.path or hints['camera_path']}")
                # 机位高度对固定机位同样重要（仰角/贴地决定了画面心理感受）。
                if s.camera.height:
                    parts.append(f"      机位高度：{s.camera.height}")
                if s.lighting:
                    parts.append(f"      光线：{s.lighting}")
                parts.append(f"      空间关系：{s.spatial or hints['spatial']}")
                if s.background_action:
                    parts.append(f"      背景人物：{s.background_action}")
                elif s.spatial:
                    parts.append(f"      背景人物：{hints['background']}")
                if s.mood:
                    parts.append(f"      情绪：{s.mood}")
            parts.append("")

        if has_anchors:
            parts.append("环境与人物锚已固定：请只输出每个镜头的 characters 与 prompt_body。")
        else:
            parts.append("请按 JSON 输出：每场一份 environment 与 characters，每个镜头一段 prompt_body。")
        parts.append(
            "写 prompt_body 时按上面九条规则：动作与运镜并重（一种主要运动、不越轴、结尾不改景别）、"
            "保留呼吸感、光影写方向与相对关系、空间写人物编号与距离、背景人物各有各的事、"
            "只写看得见的东西、接触动作物理过程只给主事件（节拍≤两步、他人不再碰同一道具）、"
            "全篇正向描述无否定句、台词不进提示词（对白只写姿态与口型动机）。"
        )
        return "\n".join(parts)

    def _apply(
        self,
        shots: list[Shot],
        raw: Any,
        script: Script,
        style: str,
        style_guide: StyleGuide | None,
        language: str = "zh",
    ) -> list[Shot]:
        """组装最终 video_prompt。

        环境/人物锚优先取美术风格指南（单一事实来源），逐字复用；缺失时退回
        本步骤 LLM 产出的锚。
        """
        scenes_raw = raw.get("scenes") if isinstance(raw, dict) else raw
        if isinstance(scenes_raw, dict):
            scenes_raw = [scenes_raw]
        if not isinstance(scenes_raw, list):
            raise ValueError(f"期望 scenes 数组，得到 {type(scenes_raw)}")

        env_by_scene: dict[str, str] = {}
        cast_by_scene: dict[str, dict[str, str]] = {}
        shot_meta: dict[str, dict[str, Any]] = {}
        for item in scenes_raw:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("scene_id") or "")
            env_by_scene[sid] = str(item.get("environment") or "")
            chars = item.get("characters") or {}
            if isinstance(chars, dict):
                cast_by_scene[sid] = {str(k): str(v) for k, v in chars.items() if v}
            for sh in item.get("shots") or []:
                if isinstance(sh, dict) and sh.get("shot_id"):
                    shot_meta[str(sh["shot_id"])] = sh

        # 规范锚（风格指南 = 单一事实来源）
        canon_chars: dict[str, str] = dict(style_guide.character_appearances) if style_guide else {}
        canon_envs: dict[str, str] = dict(style_guide.environment_descriptions) if style_guide else {}
        loc_map = {loc.id: loc.name for loc in script.locations}
        scene_loc = {sc.id: loc_map.get(sc.location_id, "") for sc in script.scenes}
        char_map = {c.id: c.name for c in script.characters}
        scene_map = {sc.id: sc for sc in script.scenes}

        updated: list[Shot] = []
        for shot in shots:
            meta = shot_meta.get(shot.id) or {}
            body = str(meta.get("prompt_body") or meta.get("video_prompt") or "")
            # 台词兜底：模型偶尔仍把台词写进 body，机械剥掉（语音交给后期配音）。
            body = _strip_spoken_quotes(body)

            # 环境锚：风格指南（按地点名）优先，其次本步骤 LLM 产出；
            # 短片常全片同一场景，若只有一个环境锚就直接用它兜底。
            env = canon_envs.get(scene_loc.get(shot.scene_id, ""), "") or env_by_scene.get(shot.scene_id, "")
            if not env and len(canon_envs) == 1:
                env = next(iter(canon_envs.values()))

            # 本镜出场人物名：优先取 LLM 的该镜 characters，否则退化为本场人物
            names = meta.get("characters")
            if not (isinstance(names, list) and names):
                sc = scene_map.get(shot.scene_id)
                names = [char_map.get(cid, cid) for cid in (sc.characters if sc else [])]

            # 人物锚：风格指南（按名）优先，其次本步骤 LLM 产出
            llm_cast = cast_by_scene.get(shot.scene_id, {})
            cast: list[str] = []
            for n in names:
                desc = canon_chars.get(str(n)) or llm_cast.get(str(n))
                cast.append(f"{n}：{desc}" if desc else str(n))

            # LLM 偶尔整段漏掉运镜：导演方案里本来就有，这里兜底补上。
            # 判据是「body 里有没有提到摄影机」而不是逐字比对——模型通常会把
            # 轨迹用自己的话复述一遍，逐字比对会把同一段运动写两遍。
            if shot.camera.path and not _mentions_camera(body):
                label = "运镜轨迹：" if language == "zh" else "Camera path: "
                body = f"{body.strip().rstrip('。')}。{label}{shot.camera.path}".strip("。")

            pieces: list[str] = []
            if env:
                pieces.append(env.strip().rstrip("。"))
            if cast:
                shift = "人物：" if language == "zh" else "Characters: "
                pieces.append(shift + "；".join(c.strip().rstrip("。") for c in cast))
            if body:
                pieces.append(body.strip().rstrip("。"))
            if style:
                pieces.append(style.strip().rstrip("。"))
            prompt = "。".join(p for p in pieces if p) + "。" if pieces else ""
            if prompt:
                shot.video_prompt = prompt
            updated.append(shot)
        return updated

    def _fallback(
        self,
        shots: list[Shot],
        script: Script,
        style: str,
        language: str,
        style_guide: StyleGuide | None,
    ) -> CrewTaskResult:
        """无模型时的回退：把风格指南的锚 + 镜头字段拼成基础提示词。"""
        loc_map = {loc.id: loc.name for loc in script.locations}
        scene_map = {sc.id: sc for sc in script.scenes}
        char_map = {c.id: c.name for c in script.characters}
        canon_chars = dict(style_guide.character_appearances) if style_guide else {}
        canon_envs = dict(style_guide.environment_descriptions) if style_guide else {}

        for shot in shots:
            sc = scene_map.get(shot.scene_id)
            env = canon_envs.get(loc_map.get(sc.location_id, ""), "") if sc else ""
            names = [char_map.get(cid, cid) for cid in (sc.characters if sc else [])]
            cast = [f"{n}：{canon_chars[n]}" if n in canon_chars else n for n in names]
            zh = language == "zh"
            head = f"{shot.shot_type}，{shot.camera.type} 运镜" if zh else f"{shot.shot_type} shot, {shot.camera.type}"
            pieces = [env, head, f"{shot.subject}。{shot.action}".strip("。")]
            if cast:
                pieces.append(("人物：" if zh else "Characters: ") + "、".join(cast))
            # 没有模型时也要把运镜/空间/背景这几类信息带上，否则提示词退化成一句话。
            if shot.camera.path:
                pieces.append(f"运镜轨迹：{shot.camera.path}" if zh else f"Camera path: {shot.camera.path}")
            if shot.camera.height:
                pieces.append(f"机位高度：{shot.camera.height}" if zh else f"Camera height: {shot.camera.height}")
            if shot.lighting:
                pieces.append(shot.lighting)
            if shot.spatial:
                pieces.append(f"空间关系：{shot.spatial}" if zh else f"Spatial: {shot.spatial}")
            if shot.background_action:
                pieces.append(
                    f"背景人物：{shot.background_action}" if zh else f"Background: {shot.background_action}"
                )
            if shot.mood:
                pieces.append(f"{shot.mood}氛围" if zh else f"{shot.mood} mood")
            pieces.append(style)
            shot.video_prompt = _strip_spoken_quotes("。".join(p.strip().rstrip("。") for p in pieces if p) + "。")
        return CrewTaskResult(data=shots, summary=f"（无模型回退）为 {len(shots)} 个镜头拼装基础提示词")


def run_dp(
    llm: LLM,
    script: Script,
    *,
    breakdowns: list[SceneBreakdown] | None = None,
    style_guide: StyleGuide | None = None,
    target_provider: str = "",
    provider_label: str = "",
    prompt_language: str = "",
    max_duration: float = 0.0,
) -> CrewTaskResult:
    """快捷入口：构建模型感知的视频提示词。"""
    agent = DPAgent(llm)
    return agent.run(
        script,
        breakdowns=breakdowns,
        style_guide=style_guide,
        target_provider=target_provider,
        provider_label=provider_label,
        prompt_language=prompt_language,
        max_duration=max_duration,
    )
