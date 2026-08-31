# =====================================================================
# profiles.py —— 改编类型（Adaptation Profile）配置
#
# 改编类型不只是下拉项，它会同时影响：生成提示词、Agent 的改写约束、
# 以及最终的导出呈现。每种类型给出了「场景规划」和「剧本节拍」两种
# 层面的写作指导，供 LLM 在生成和改写时遵循。
#
# 这样设计的好处：让 Agent 的改写不是套同一个通用模板，
# 而是知道自己在改「短剧 / 电影 / 剧集 / 舞台剧」里的哪一种。
# =====================================================================

from __future__ import annotations

import json
from typing import Any, Literal

# 支持的改编类型，与 domain.AdaptationType 对齐。
ProfileName = Literal["short_drama", "film", "series", "stage", "other"]


# ---------- 类型定义 ----------

PROFILES: dict[str, dict[str, Any]] = {
    "short_drama": {
        "label": "短剧",
        "target_format": "竖屏或横屏短剧，单场节奏紧凑",
        "tone": "high-tension",
        "scene_planning": [
            "优先保留强钩子、快速反转和高冲突场面。",
            "每场只服务一个清晰戏剧目标，减少解释性过场。",
            "场景结尾尽量形成追问、危险或情绪悬念。",
        ],
        "script_blocks": [
            "动作短、可拍、直接推动下一句对白。",
            "对白口语化，避免长段说明。",
            "前三个节拍尽快暴露压力、秘密或危险。",
        ],
    },
    "film": {
        "label": "电影",
        "target_format": "电影剧本，强调三幕推进和视觉叙事",
        "tone": "cinematic",
        "scene_planning": [
            "按电影场景组织，保留人物选择、视觉行动和因果推进。",
            "避免把小说心理描写直接改成解释性对白。",
            "让每场在人物状态、关系或外部局势上发生可见变化。",
        ],
        "script_blocks": [
            "动作具有镜头感，但不要写具体机位术语。",
            "对白克制、有潜台词，服务人物关系和冲突。",
            "场面调度优先通过行为、空间和道具体现。",
        ],
    },
    "series": {
        "label": "剧集",
        "target_format": "分集剧本，兼顾单集目标和长期人物弧",
        "tone": "serial",
        "scene_planning": [
            "保留 A/B 线索和人物长期弧光。",
            "每场服务本集推进，也埋下后续回收点。",
            "结尾适合留下关系变化、线索推进或集尾悬念。",
        ],
        "script_blocks": [
            "动作和对白兼顾当场冲突与后续伏笔。",
            "对白可承载关系变化，但避免信息堆砌。",
            "重要线索用 cue 或动作节拍标记，方便追踪。",
        ],
    },
    "stage": {
        "label": "舞台剧",
        "target_format": "舞台剧本，重视出入场、舞台动作、灯光音效和有限空间",
        "tone": "theatrical",
        "scene_planning": [
            "控制地点数量，优先选择可在舞台上持续成立的空间。",
            "明确角色出入场、站位关系和冲突焦点。",
            "用舞台动作、道具、灯光或音效承担小说中的心理变化。",
        ],
        "script_blocks": [
            "动作要能被演员执行，避免镜头语言。",
            "cue 可用于灯光、音效、道具或舞台提示。",
            "对白允许更有节奏和舞台张力，但仍贴合人物。",
        ],
    },
    "other": {
        "label": "自定义改编",
        "target_format": "自定义剧本格式",
        "tone": "adaptive",
        "scene_planning": [
            "优先保留原作核心冲突、人物关系和可改编场面。",
            "按素材自然选择场景密度，不强行套模板。",
        ],
        "script_blocks": [
            "动作与对白按时间顺序组织，方便人工继续改写。",
            "保留必要潜台词和改编说明。",
        ],
    },
}

# 默认类型名。
DEFAULT_PROFILE: ProfileName = "short_drama"


def profile_for(name: str) -> dict[str, Any]:
    """按名称取 profile；未知名称回退到 ``other``。"""
    key = normalize_name(name)
    return PROFILES.get(key, PROFILES["other"])


def normalize_name(name: str) -> str:
    """把外部传来的类型名规整到 ProfileName。"""
    from .domain import normalize_adaptation_type

    return normalize_adaptation_type(name)


def profile_type(name: str) -> ProfileName:
    """返回受约束的类型名（用于持久化 / 枚举）。"""
    return normalize_name(name)  # type: ignore[return-value]


def profile_prompt(profile: dict[str, Any], *, language: str) -> str:
    """把某个 profile 序列化成可读的 JSON 提示词片段。"""
    return json.dumps(
        {
            "adaptation_label": profile["label"],
            "target_format": profile["target_format"],
            "tone": profile["tone"],
            "scene_planning": profile["scene_planning"],
            "script_blocks": profile["script_blocks"],
            "output_language": language,
        },
        ensure_ascii=False,
        indent=2,
    )
