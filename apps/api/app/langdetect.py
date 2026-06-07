"""Lightweight offline language detection for incoming novel text.

Heuristics only — no third-party deps. The goal is to pick a sensible
BCP-47 tag for the LLM output language when the user has not explicitly
chosen one.

Strategy:
- Count CJK ideographs, Latin letters, Cyrillic, Arabic, Hangul.
- Decide based on dominant script.
- Refine Chinese into zh-CN / zh-TW using simplified-only and
  traditional-only character evidence. A single traditional-looking glyph
  should not flip a long simplified source to zh-TW.

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

# Characters that are very unlikely in modern simplified/traditional Chinese
# writing respectively. These lists are intentionally small and conservative:
# they are used as evidence, not as a full converter.
_TRAD_ONLY = set(
    "舊臺灣區書麵鐘蘭畫長門開頭車時觀點龍馬鳥龜"
    "記憶體資料庫軟體網路電腦滑鼠當機當作並與"
    "週總擠滿陳列發現後個場對說過進來沒為從"
    "聯號環軌站螢幕聲訊號語壓斷續繼續"
)
_SIMP_ONLY = set(
    "旧台区书面钟兰画长门开头车时观点龙马鸟龟"
    "记忆体数据库软体网络电脑鼠标当机当作并与"
    "周总挤满陈列发现后个场对说过进来没为从"
    "联号环轨站屏幕声讯号语压断续继续"
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
        simp_hits = sum(1 for ch in text if ch in _SIMP_ONLY)
        cjk_count = max(1, top_count)
        # Require sustained traditional evidence. Long simplified documents can
        # contain isolated traditional characters from names, quotes, or copied
        # metadata; those should still detect as zh-CN.
        if trad_hits >= max(3, int(cjk_count * 0.005)) and trad_hits > simp_hits:
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
