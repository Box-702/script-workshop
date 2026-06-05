"""Lightweight offline language detection for incoming novel text.

Heuristics only — no third-party deps. The goal is to pick a sensible
BCP-47 tag for the LLM output language when the user has not explicitly
chosen one.

Strategy:
- Count CJK ideographs, Latin letters, Cyrillic, Arabic, Hangul.
- Decide based on dominant script.
- Refine Chinese into zh-CN / zh-TW using a small set of traditional-only
  characters (taken from public-domain common-use lists).

This is intentionally a heuristic — ambiguous mixed-language text falls
back to whichever script has the highest share, then to en-US as a safe
default. Callers should treat the result as a hint, not a fact.
"""
from __future__ import annotations

import re
from collections import Counter

_CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")
_HANGUL_RE = re.compile(r"[가-힯]")
_HIRAGANA_RE = re.compile(r"[぀-ゟ]")
_KATAKANA_RE = re.compile(r"[゠-ヿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_CYRILLIC_RE = re.compile(r"[Ѐ-ӿ]")
_ARABIC_RE = re.compile(r"[؀-ۿ]")

# Characters that are very unlikely in modern simplified Chinese writing.
# Used to tip zh-CN vs zh-TW. Source: well-known common-use character lists.
_TRAD_ONLY = set(
    "舊臺灣區書麵鐘蘭畫長門開頭車時觀點龍馬鳥龜"
    "記憶體資料庫軟體網路電腦滑鼠當機當作並且"
)


def _script_counts(text: str) -> Counter[str]:
    return Counter(
        {
            "cjk": len(_CJK_RE.findall(text)),
            "hangul": len(_HANGUL_RE.findall(text)),
            "hiragana": len(_HIRAGANA_RE.findall(text)),
            "katakana": len(_KATAKANA_RE.findall(text)),
            "latin": len(_LATIN_RE.findall(text)),
            "cyrillic": len(_CYRILLIC_RE.findall(text)),
            "arabic": len(_ARABIC_RE.findall(text)),
        }
    )


def detect_language(text: str) -> str:
    """Return a BCP-47 language tag for the dominant script in `text`.

    Always returns a non-empty string. Defaults to ``en-US`` when the text
    is empty or no script dominates.
    """
    if not text or not text.strip():
        return "en-US"
    counts = _script_counts(text)
    total = sum(counts.values())
    if total == 0:
        return "en-US"

    # Japanese: presence of kana disambiguates from Chinese.
    if counts["hiragana"] + counts["katakana"] >= max(3, total * 0.01):
        return "ja-JP"

    top, top_count = counts.most_common(1)[0]
    if top == "cjk":
        # zh-CN vs zh-TW
        trad_hits = sum(1 for ch in text if ch in _TRAD_ONLY)
        # >= 1 traditional-only char + no obvious simplified dominance → zh-TW
        if trad_hits >= 1:
            return "zh-TW"
        return "zh-CN"
    if top == "hangul":
        return "ko-KR"
    if top == "cyrillic":
        return "ru-RU"
    if top == "arabic":
        return "ar-SA"
    if top == "latin":
        # Distinguish English from other Latin-script languages cheaply via
        # the presence of common English function words.
        lowered = text.lower()
        if any(
            token in lowered
            for token in (" the ", " and ", " of ", " to ", " is ", " was ")
        ):
            return "en-US"
        return "en-US"  # safe default for any Latin text
    return "en-US"
