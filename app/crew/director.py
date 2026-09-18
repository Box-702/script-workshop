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

DIRECTOR_SYSTEM = """你是影视导演，擅长把文字剧本转化为视觉叙事，尤其懂得「镜头连续性」的取舍。

你的任务是为每场戏设计镜头方案，遵循以下核心原则：

**镜头粒度：一个分镜 = 一段连贯的「角色动作」，或一段连贯的「角色对话剧情」**：
- 连续的动作过程（某个人物从开始到完成一件事）算**一个**镜头，不要拆碎。
- 连续的一段对话交锋（多个人来回说话、一次完整的争执/问答）算**一个**镜头，不要一句一切、不要正反打。
- 只有当「动作单元」或「对话单元」本身发生切换时才允许切镜：换了主体、换了事件、换了焦点，或时间/地点跳变。
- **具体做法**：把本场的 beats 节拍流按类型切成连续的「动作段」和「对话段」，每一段合成一个镜头——动作段连着的动作归为一镜，对话段连着的一段对话归为一镜。
- 数量由内容决定，不设固定数字；默认宁少勿多（镜头越少越连贯、成本越低）。

**重要：这是给 AI 视频生成用的分镜，不是真人拍摄**：
- 每一个镜头都是一次「独立的 AI 生成」：镜头越多，画面漂移越大、一致性越差、成本越高。
- **禁止真人影视的「覆盖式拍摄」思路**——不要一人一切、不要正反打、不要「谁说话就切谁」。同一段连续对话，用一个镜头内的场面调度讲完，把人物与动作写进这个镜头的描述里。
- 每个镜头必须填 `cut_reason`（为什么必须在这里切）。只有「动作单元/对话单元发生切换、时间跳变、地点切换」才算理由；写不出理由的，就合并进上一个镜头。
- 单镜时长必须落在目标模型的单次生成区间内（默认 **4–10 秒**），禁止出现 2 秒、20 秒这类无法执行的时长。
- **对白镜头要给台词留足时间**：一段对话的朗读时长约等于「总字数 ÷ 每秒 4 字」，
  该镜头的 duration_sec 不得低于这个估算——时长不够，配音就会被压着说或者被片尾截断。
- 同一场景内不要反复出现「同一个人的面部特写」——这是 AI 视频里最伤的重复切镜。

**每个镜头都要给出「连续性计划」两个字段**：
- `reference_group`：共享环境参考图的分组键。同一场景、同一空间的镜头必须用同一个分组键（如 "room_01"），这样它们能共用同一张环境参考图锁住场景；硬切到新地点时另起新分组键。
- `chain_from`：首尾帧接力。若本镜头在时间/空间上紧接上一个镜头，填上一个镜头的 `order`，表示「本镜首帧 = 上一个镜头尾帧」；若是全新序列起点或硬切，填 null。

**画面调度必须写进字段：视频模型看不到你脑子里的画面，只有你写下来的文字**：
不要只写「画面里有什么」。下面五件事必须在每个镜头里写明，否则模型会自己乱猜，
拍出来的运动、光影和空间关系都跟你想的不是一回事。

1. **运镜轨迹**（`camera_path` + `camera_height`）：把摄影机想成一台贴近人物飞行的
   虚拟无人机——它是观众的眼睛，负责带着观众进入现场。所以要写清**起点 → 终点**：
   往哪个方向移动（前进 / 后退 / 侧移 / 环绕 / 升降 / 偏航 / 俯仰）、相对主体的距离
   怎么变、机位高度是多少（齐胸 / 过顶 / 贴地）、以及运动规律（起步与刹车、惯性、
   中途的加减速）。`camera_path` 写轨迹，`camera_height` 写高度。
   固定机位（static）可以留空，但只要 camera_type 不是 static 就必须写。
   **运镜三禁（违反任何一条，人物与场景的位置对应必崩）**：
   ① 一镜只允许**一种**连续机位运动——不要把环绕、推近、横移组合进同一镜；
   ② **禁止越轴**：摄影机保持在主要人物运动方向的同一侧，从人物一侧绕到另一侧
   （含 180 度环绕）是大忌——无参考图的文生视频，机位角度每大变一次，背景就被
   重新想象一次，位置对应就崩一次；
   ③ **结尾不改景别**：镜头结尾停在原构图意图上，不要在末段推近/拉远换成另一种
   景别——要换景别就另起一镜，让 cut_reason 去承担。
2. **光线的关系**（`lighting`）：写清光**从哪个方向来**、**主光源是什么**、人物与光源的
   **相对位置**，以及镜头运动过程中环境光与人物脸部光**怎么变**。不要写成「光总是
   打在脸上」——那样人物怎么走光都跟着脸走，画面会假。
3. **空间关系**（`spatial`）：给主要人物编号（齐夏1号、人羊2号），写清人物之间的相对
   距离、他们离镜头多远、离地面多高，以及运镜从起点到终点这些相对位置**发生了什么
   变化**。
4. **背景人物**（`background_action`）：背景人物要有各自独立、不完全同步的生活化行为，
   写明谁在做什么（例如：制服警察在维持边界偶尔回头；蓝色工装的人一个半蹲拍照、
   一个在调整标记牌；记者压低声音交谈，有人拿着带塑料盖的外带咖啡；居民在警戒带外
   探头低语，偶尔举起手机）。**允许少数人短时间保持静止**，不要要求所有背景人物
   持续运动，也不必所有人都同步做同一件事。没有背景人物的镜头留空。
5. **动作的物理过程**（`action`）：模型只看得懂「身体怎么动」，看不懂「意图」。凡是人和
   道具发生接触的动作（掀警戒带、推门、掀帘子、拿杯子、递东西、拉抽屉），不能只写结果式的
   「掀开带子走过去」——那必然拍成手和道具互相穿透。要按三件事写：
   **接触点与受力方向**（哪只手、捏住道具的哪一段、往哪个方向使劲）；
   **先后节拍**（先试探一下 / 再完全完成，写成两步，不要一步到位）；
   **身体姿态的变化**（道具抬到多高、上身是前倾还是后仰、头低到什么程度、从下面钻过去时
   哪个部位在最前面）。同时写明不穿模的让位关系：道具从人物手的哪一侧经过、从身体哪一侧
   让过去，人物的哪个部位在道具的上方还是下方通过。让位关系**只能用正向描述**
   （如「带子从她头顶上方通过」），禁止写「没有穿过/没有碰到」这类否定句——
   视频模型会把被否定的动作本身画出来。
   **物理过程的预算只给主事件**：一镜里只有一个「主事件」值得写物理过程，节拍最多两步
   （接触 → 完成，或试探 → 完成）；镜头里**其他人物不得再与同一道具发生第二次互动**
   （两个人先后掀同一条带子，模型必然把两次互动搅在一起）；次要接触动作一笔带过。
   12 秒的镜头塞进 6 个物理节拍，模型只会丢节拍、挪时序，人物就会出现在不该在的位置。

**其余要求**：
- 分析每场戏的戏剧目标、情绪弧线、节奏需求
- 决定镜头类型（远景/中景/近景/特写等）与运镜方式（固定/推/拉/摇/移/跟/环绕等）
- 标注关键时刻（情绪转折、冲突爆发、悬念设置）
- 整体节奏：开场紧凑、中段有张有弛、高潮密集

输出 JSON 数组（每个元素是一场戏的拆解）：
```json
[
  {
    "scene_id": "scene_001",
    "director_notes": "这场戏是开场，在一个密闭房间内，无需切太多镜头……",
    "visual_approach": "缓慢推近建立空间感，保持同一盏钨丝灯的连续性……",
    "pacing": "slow",
    "key_moments": ["众人苏醒", "发现无门"],
    "shots": [
      {
        "order": 0,
        "shot_type": "wide",
        "camera_type": "dolly",
        "camera_direction": "in",
        "camera_speed": "slow",
        "camera_path": "从房间后墙处起步，沿中轴向长桌缓慢前进约四米，越过最外侧沉睡者后减速停住",
        "camera_height": "离地约 1.6 米，与站立者胸口齐平，全程保持水平",
        "subject": "昏暗的密闭房间全景",
        "action": "十个沉睡者伏在桌上，山羊头面具男人立于长桌尽头",
        "dialogue_ref": null,
        "duration_sec": 8.0,
        "lighting": "唯一主光来自长桌正上方那盏钨丝灯，向下打在桌面形成亮斑，四周迅速衰减入暗；镜头前进时桌面的亮斑始终不动，人物面部只在进入光锥时才被照亮",
        "mood": "压抑、不安",
        "spatial": "众人1号在最里侧，逐个向镜头方向排开，彼此相隔约半米；山羊头男人2号站在长桌尽头、离镜头最远；镜头与最近的人约 3 米，终点推进到 1.5 米",
        "background_action": "靠墙处两名守卫各自倚墙，一人低头看鞋、一人偏头望向门口；角落有人无意识地搓着手指；这些动作彼此不同步，可有短暂静止",
        "reference_group": "room_01",
        "chain_from": null,
        "cut_reason": "开场建立空间，之前的序列起点"
      },
      {
        "order": 1,
        "shot_type": "close_up",
        "camera_type": "static",
        "camera_direction": null,
        "camera_speed": "medium",
        "camera_path": "",
        "camera_height": "略低于座钟钟面，仰角约 15 度",
        "subject": "座钟指针与苏醒的众人",
        "action": "座钟指向十二，众人陆续苏醒抬头",
        "dialogue_ref": null,
        "duration_sec": 8.0,
        "lighting": "钨丝灯在画面左上方，钟面被侧光扫过留下一条高光，右侧人脸落在阴影里",
        "mood": "压抑",
        "spatial": "钟面1号占画面左侧三分之一，位于前景；苏醒的人2号在后方约两米处、焦外",
        "background_action": "有人缓慢撑起身体，有人仍趴着不动，动作前后错开",
        "reference_group": "room_01",
        "chain_from": 0,
        "cut_reason": "视点从全景转向座钟，建立时间悬念"
      }
    ]
  }
]
```

枚举：
- shot_type：extreme_wide / wide / medium / close_up / extreme_close_up / over_shoulder / pov
- camera_type：static / pan / tilt / dolly / tracking / crane / handheld / zoom / steady / orbit
- camera_speed：slow / medium / fast
- pacing：slow / medium / fast / variable

注意：
- camera_type 不是 static 时，camera_path 必填（写不出轨迹就说明这一镜其实是固定机位）。
- 同一场景内多个镜头必须统一 reference_group（除非中间硬切到新地点）。
- 时间/空间连续的前后镜头用 chain_from 接力，链到紧邻的前序镜头。
- 所有对白引用使用 beat_xxx 格式 id。
"""


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
                raw = self._invoke_json(DIRECTOR_SYSTEM, user_prompt)
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
        """确定性校验分镜（不靠固定镜头数，只查结构自洽与生成器可行性）。

        检查项：
          1. 同场景多镜必须指定 reference_group，才能共享环境参考图；
          2. chain_from 只能接力到更早的镜头（不悬空、不自指、不向后指）；
          3. 单镜时长必须落在目标模型单次生成的可行区间（默认 4–15 秒）；
          4. 非首镜必须填写 cut_reason（写不出切镜理由就该合并）；
          5. 相邻镜头不应是同一个人的重复面部特写（AI 视频里最伤的重复切镜）；
          6. 运动镜头必须写 camera_path——写不出轨迹，模型就会自己乱动。
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
                    reference_group=str(s.get("reference_group") or ""),
                    chain_from=chain,
                )
                shots.append(shot)

            breakdown = SceneBreakdown(
                scene_id=scene_id,
                director_notes=item.get("director_notes", ""),
                visual_approach=item.get("visual_approach", ""),
                pacing=_pick_enum(item.get("pacing"), _PACINGS, {}, "medium"),
                key_moments=item.get("key_moments", []),
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
