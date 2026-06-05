"""Deterministic offline mock provider.

Generates plausible, schema-valid structured output from input text without
calling any LLM. Used when no API key is set, or as a safety fallback.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

from .base import LLMProvider, Stage


def _slug(s: str, prefix: str = "x") -> str:
    h = hashlib.md5(s.encode("utf-8")).hexdigest()[:4]
    base = re.sub(r"[^a-z0-9_]+", "_", s.lower()).strip("_") or h
    return f"{prefix}_{base[:16]}_{h}"


def _first_sentences(text: str, n: int = 2, max_chars: int = 120) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    # split on Chinese & English sentence terminators
    parts = re.split(r"(?<=[。.!?！？\n])\s*", cleaned)
    parts = [p for p in parts if p]
    out = " ".join(parts[:n]) or cleaned[:max_chars]
    return out[:max_chars]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def _mock_summary(prompt: str) -> dict:
    # extract chapter block (after marker)
    m = re.search(r"CHAPTER CONTENT:\s*(.+?)(?:\n\n[A-Z#]|\Z)", prompt, re.DOTALL)
    text = (m.group(1) if m else prompt)[-2000:]
    paras = _paragraphs(text)
    events = [
        _first_sentences(p, 1, 60) for p in paras[:3]
    ] or ["情节推进"]
    return {
        "chapter_id": _chapter_id(prompt),
        "summary": _first_sentences(text, 2, 140),
        "major_events": events,
        "characters": _extract_names(text) or ["未知人物"],
        "locations": _extract_locations(text) or ["未指明地点"],
        "conflicts": ["人物面临未知威胁"],
        "turning_points": ["关键决定"],
    }


def _mock_bible(prompt: str) -> dict:
    text = prompt[-3000:]
    title = _first_sentences(text, 1, 30)
    chars = _extract_names(text) or ["主角", "对手"]
    locs = _extract_locations(text) or ["主要场景"]
    return {
        "title": title or "未命名故事",
        "logline": "在压力之下，主角面对隐藏的真相，作出无法回头的选择。",
        "genre": "suspense",
        "themes": ["信任", "身份", "自我救赎"],
        "setting": "当代城市",
        "central_conflict": "主角必须在保护自己与揭示真相之间做出抉择。",
        "characters": [
            {"id": _slug(c, "char"), "name": c, "role": "protagonist" if i == 0 else "supporting"}
            for i, c in enumerate(chars[:4])
        ],
        "locations": [
            {"id": _slug(loc, "loc"), "name": loc} for loc in locs[:3]
        ],
        "timeline": ["开端：事件触发", "中段：真相浮现", "结尾：抉择"],
    }


def _mock_characters(prompt: str) -> dict:
    names = _extract_names(prompt) or ["主角", "神秘来客", "协助者"]
    chars = []
    for i, n in enumerate(names[:4]):
        cid = _slug(n, "char")
        chars.append(
            {
                "id": cid,
                "name": n,
                "role": "protagonist" if i == 0 else "supporting",
                "goal": f"推动关于 {n} 的关键情节。",
                "motivation": "受过去事件影响。",
                "personality": "克制、敏锐",
                "arc": "从被动到主动",
                "speech_style": "简短、理性",
            }
        )
    return {"characters": chars}


def _mock_scene_plan(prompt: str) -> dict:
    # The pipeline passes a serialized context; pull chapter refs from header
    chap_ids = re.findall(r"chapter_\d{3,}", prompt)
    chap_refs = sorted(set(chap_ids)) or ["chapter_001"]
    # assume 1 scene per chapter as minimum
    scenes = []
    for i, cid in enumerate(chap_refs):
        sid = f"scene_{i + 1:03d}"
        scenes.append(
            {
                "id": sid,
                "chapter_refs": [cid],
                "location": "未指明地点",
                "time": "未指明时间",
                "characters": [],
                "purpose": f"推进 {cid} 的核心情节。",
                "conflict": "角色面对外部压力。",
                "entry_state": "进入场景前的状态。",
                "exit_state": "离开场景时的状态。",
            }
        )
    return {"scenes": scenes}


def _mock_dialogue(prompt: str) -> dict:
    # extract speakers from prompt (character ids)
    speakers = re.findall(r"char_[a-z0-9_]+", prompt)
    if not speakers:
        return {
            "dialogue": [
                {
                    "speaker": "char_unknown",
                    "line": "（占位对白：等待真实 LLM 接入。）",
                    "emotion": "neutral",
                    "subtext": "请配置 OPENAI_API_KEY 以生成真实对白。",
                }
            ]
        }
    primary = speakers[0]
    return {
        "action": [
            "环境描述占位：等待真实 LLM 接入。",
        ],
        "dialogue": [
            {
                "speaker": primary,
                "line": "（占位对白：等待真实 LLM 接入。）",
                "emotion": "neutral",
                "subtext": "配置 OPENAI_API_KEY 后可生成真实对白与潜台词。",
            }
        ],
    }


def _mock_repair(prompt: str, schema: dict) -> dict:
    # mock can't really repair; return the prompt as-is wrapped
    return {"repaired": prompt}


# -------- helpers --------


_NAME_RE = re.compile(
    r"([一-鿿]{2,4}(?:医生|老师|先生|女士|医生|队长|老板|老板)?)"
)
_LOC_RE = re.compile(r"([一-鿿]{2,8}(?:诊所|医院|学校|酒吧|街道|城市|办公室|房间|楼))")


def _extract_names(text: str) -> list[str]:
    seen: list[str] = []
    for m in _NAME_RE.finditer(text):
        n = m.group(1)
        if n not in seen and not n.endswith(("医生", "老师", "先生", "女士")):
            seen.append(n)
        if len(seen) >= 4:
            break
    return seen


def _extract_locations(text: str) -> list[str]:
    seen: list[str] = []
    for m in _LOC_RE.finditer(text):
        n = m.group(1)
        if n not in seen:
            seen.append(n)
        if len(seen) >= 3:
            break
    return seen


def _chapter_id(prompt: str) -> str:
    m = re.search(r"chapter_\d{3,}", prompt)
    return m.group(0) if m else "chapter_001"


class MockProvider:
    """Deterministic offline provider. Returns plain dicts, not coroutines."""

    def generate_structured(
        self, prompt: str, schema: dict, *, stage: Stage
    ) -> dict[str, Any]:
        if stage == Stage.SUMMARY:
            return _mock_summary(prompt)
        if stage == Stage.BIBLE:
            return _mock_bible(prompt)
        if stage == Stage.CHARACTERS:
            return _mock_characters(prompt)
        if stage == Stage.SCENE_PLAN:
            return _mock_scene_plan(prompt)
        if stage == Stage.DIALOGUE:
            return _mock_dialogue(prompt)
        if stage == Stage.REPAIR:
            return _mock_repair(prompt, schema)
        return {}
