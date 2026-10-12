# =====================================================================
# novel_map.py —— 长篇小说的章节地图与选段改编
#
# 解决的问题：剧本生成一次只吃得下约 1.4 万字原文，超长小说此前被
# 「静默砍头」。正确形态是「先选故事弧，再改编」：
#   build_novel_map()  map-reduce 建章节地图（每章一句摘要+出场人物）
#   arcs_context()     把地图喂给模型提候选故事弧
#   previous_context() 已改编章节的「前情提要」，注入下一次生成本衔接
# 全部走后台任务 + 对话工具，产物存 projects.novel_map_json。
# =====================================================================

from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

from .chunking import _CHAPTER_RE, chapter_spans

log = logging.getLogger(__name__)

# 地图章节上限：超过的按窗口硬切，防止失控（400 章 × 一次调用 ≈ 成本可控）。
MAX_MAP_CHAPTERS = 400
# 建图时每章最多喂给模型的字数（摘不需要全文）。
_CHAPTER_TEXT_CAP = 1600
# 伪章节（无标题长文）的窗口大小。
_PSEUDO_WINDOW = 4000

ProgressFn = Callable[[str], None]


def _fake_llm_available(llm: Any) -> bool:
    return bool(getattr(llm, "available", False))


def _pseudo_spans(text: str) -> list[dict[str, Any]]:
    """无章节标题的长文按固定窗口切成伪章节。"""
    spans = chapter_spans(text)
    if len(spans) > 1:
        return spans
    windows: list[dict[str, Any]] = []
    for i in range(0, len(text), _PSEUDO_WINDOW):
        windows.append({
            "index": len(windows) + 1,
            "title": f"片段 {len(windows) + 1}",
            "start": i,
            "end": min(i + _PSEUDO_WINDOW, len(text)),
            "chars": min(_PSEUDO_WINDOW, len(text) - i),
        })
    return windows or [{"index": 1, "title": "（全文）", "start": 0, "end": len(text), "chars": len(text)}]


_CHAPTER_PROMPT = (
    "你是小说编辑。用两行概括这一章：\n"
    "剧情：<一两句话，说清发生了什么、有什么转折>\n"
    "人物：<出场人物名，顿号分隔，最多 6 个>\n"
    "只输出这两行，不要评论。"
)


def _split_names(raw: str) -> list[str]:
    return [n.strip() for n in re.split(r"[、,，;；]", raw) if n.strip()][:6]


def _parse_chapter_reply(raw: str) -> tuple[str, list[str]]:
    """解析单章摘要回复。兼容两种格式：

    - 带前缀：「剧情：xxx」+「人物：xxx」（提示词要求的格式）；
    - 裸文本：模型没遵守格式时，首行是剧情、其余行里短的一行是人物名单。
      （deepseek 实测约一半调用会丢掉前缀，直接回两行纯文本。）
    """
    lines = [ln.strip() for ln in str(raw).splitlines() if ln.strip()]
    summary, characters = "", ""
    for line in lines:
        if line.startswith(("剧情", "情节")):
            summary = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        elif line.startswith("人物"):
            characters = line.split("：", 1)[-1].split(":", 1)[-1].strip()
    if not summary and lines:
        summary = lines[0]
        rest = [ln for ln in lines[1:] if not _CHAPTER_RE.match(ln)]
        if rest and len(rest[0]) <= 30 and not re.search(r"[。！？]", rest[0]):
            characters = rest[0]
    return summary, _split_names(characters)


def _fallback_summary(body: str) -> str:
    """回退摘要：跳过章节标题行，取正文第一句。"""
    for line in (body or "").strip().splitlines():
        stripped = line.strip()
        if not stripped or _CHAPTER_RE.match(stripped):
            continue
        first = re.split(r"[。！？]", stripped)[0][:60]
        if first:
            return first
    return "（摘要生成失败）"


def _summarize_chapter(llm: Any, title: str, body: str) -> tuple[str, list[str]]:
    """单章摘要。失败返回占位摘要，不中断整体建图。"""
    text = f"{title}\n{body[:_CHAPTER_TEXT_CAP]}"
    try:
        resp = llm.chat().invoke([
            {"role": "system", "content": _CHAPTER_PROMPT},
            {"role": "user", "content": text},
        ])
        raw = getattr(resp, "content", "") or ""
        if isinstance(raw, list):
            raw = " ".join(b.get("text", "") for b in raw if isinstance(b, dict) and b.get("type") == "text")
        summary, names = _parse_chapter_reply(str(raw))
        if summary:
            return summary, names
    except Exception as e:  # noqa: BLE001
        log.warning("章节摘要失败（%s）：%s", title, e)
    # 兜底：用正文第一句（跳过标题行），保证地图完整可用。
    return _fallback_summary(body), []


def build_novel_map(raw_text: str, llm: Any, *, on_progress: ProgressFn | None = None) -> dict[str, Any]:
    """建立章节地图：逐章摘要 + 出场人物。

    返回 {"chapters": [{index,title,summary,characters,chars}], "total_chars",
    "pseudo": 是否为伪章节切分}。需要可用的对话模型；不可用时抛 ValueError。
    """
    if not _fake_llm_available(llm):
        raise ValueError("章节地图需要对话模型（当前未配置或不可用）")
    text = raw_text or ""
    spans = _pseudo_spans(text)[:MAX_MAP_CHAPTERS]
    total = len(spans)
    chapters: list[dict[str, Any]] = []
    for i, span in enumerate(spans):
        body = text[span["start"]:span["end"]]
        summary, names = _summarize_chapter(llm, span["title"], body)
        chapters.append({
            "index": i + 1,
            "title": span["title"],
            "summary": summary,
            "characters": names,
            "chars": span["chars"],
        })
        if on_progress and (i + 1) % 5 == 0:
            on_progress(f"已摘要 {i + 1}/{total} 章")
    return {"chapters": chapters, "total_chars": len(text), "pseudo": len(chapters) > 0 and spans[0]["title"].startswith("片段")}


def arcs_context(novel_map: dict[str, Any], from_chapter: int = 1, to_chapter: int | None = None,
                 max_chapters: int = 120) -> str:
    """把章节地图压成供选段模型阅读的清单（章号+标题+字数+摘要）。"""
    chapters = novel_map.get("chapters") or []
    a = max(1, from_chapter)
    b = min(len(chapters), to_chapter or len(chapters))
    lines = []
    for c in chapters[a - 1:b][:max_chapters]:
        chars = "、".join(c.get("characters") or [])
        suffix = f"（人物：{chars}）" if chars else ""
        n = c.get("chars")
        size = f"（约{int(n)}字）" if n else ""
        lines.append(f"第{c['index']}章 {c.get('title', '')}{size}：{c.get('summary', '')}{suffix}")
    if b - a + 1 > max_chapters:
        lines.append(f"（仅列出前 {max_chapters} 章，共 {b - a + 1} 章）")
    return "\n".join(lines)


# 一次剧本生成的原文容量上限（12 切片 × 约 1000 字，留余量）。选弧提示词据此约束弧大小。
ARC_CHAR_BUDGET = 12000

ARCS_PROMPT = (
    "你是短剧策划。下面的清单是一部小说的章节地图（每章含字数）。请从指定范围里挑出 2-3 个"
    "最适合改编成短剧的「故事弧」——一个弧=一段有完整起承转合、能独立成片的连续章节。\n"
    "硬约束：一个弧的章节字数总和不要超过 12000 字（单次剧本生成的容量），"
    "大的故事阶段请拆成上下几个弧（如「虎妞逼婚(上)」）。\n"
    "只输出 JSON 数组，每项：{\"title\": \"弧名\", \"from\": 起始章号, \"to\": 结束章号, "
    "\"hook\": \"一句话戏剧钩子\", \"why\": \"为什么适合（20字内）\"}。"
    "弧与弧不重叠，覆盖你觉得最有戏的部分即可，不必覆盖全部。"
)


def parse_arcs(raw: str) -> list[dict[str, Any]]:
    """从模型输出中提取故事弧 JSON 数组；解析失败抛 ValueError。"""
    text = str(raw or "")
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON 数组")
    arcs = json.loads(text[start:end + 1])
    result = []
    for arc in arcs if isinstance(arcs, list) else []:
        if not isinstance(arc, dict):
            continue
        a, b = int(arc.get("from") or 0), int(arc.get("to") or 0)
        if a < 1 or b < a:
            continue
        result.append({
            "title": str(arc.get("title") or f"故事弧 {len(result) + 1}"),
            "from": a,
            "to": b,
            "hook": str(arc.get("hook") or "").strip(),
            "why": str(arc.get("why") or "").strip(),
        })
    if not result:
        raise ValueError("没有可用的故事弧")
    return result


def previous_context(novel_map: dict[str, Any], until_chapter: int, *, max_chars: int = 1200) -> str:
    """汇总已改编章节的摘要作为「前情提要」（注入下一次生成本衔接连续性）。"""
    chapters = novel_map.get("chapters") or []
    lines = [
        f"第{c['index']}章：{c.get('summary', '')}"
        for c in chapters[:max(0, int(until_chapter))]
        if c.get("summary")
    ]
    text = "\n".join(lines)
    return text[-max_chars:] if len(text) > max_chars else text


def next_to_chapter(novel_map: dict[str, Any], from_chapter: int, budget: int = ARC_CHAR_BUDGET) -> int:
    """连载续接的默认终点：从 from_chapter 起按字数预算装章，至少一章、不超预算。"""
    chapters = novel_map.get("chapters") or []
    a = max(1, int(from_chapter))
    if not chapters:
        return a
    acc, to = 0, a
    for c in chapters[a - 1:]:
        size = int(c.get("chars") or 0)
        if to > a and acc + size > budget:
            break
        acc += size
        to = int(c["index"])
    return min(to, len(chapters))
