# =====================================================================
# test_novel_map.py —— 长篇小说：章节地图 / 选段改编 / 前情提要
# =====================================================================

from __future__ import annotations

import pytest

from app.pipeline.chunking import chapter_spans, slice_by_chapter
from app.pipeline.novel_map import (
    arcs_context,
    build_novel_map,
    parse_arcs,
    previous_context,
)


class FakeLLM:
    """可编程假模型：available=True，按脚本回话。"""

    def __init__(self, replies: list[str] | None = None):
        self.available = True
        self.replies = list(replies or [])
        self.calls: list[list[dict]] = []

    class _Chat:
        def __init__(self, outer):
            self._outer = outer

        def invoke(self, msgs):
            self._outer.calls.append(msgs)
            reply = self._outer.replies.pop(0) if self._outer.replies else "剧情：无。\n人物：无"
            return type("R", (), {"content": reply})()

    def chat(self):
        return self._Chat(self)


def _novel() -> str:
    chapters = []
    for i in range(1, 6):
        chapters.append(f"第{'一二三四五'[i - 1]}章 试炼{i}\n" + f"林然在巷口遇上了红雨衣男人，交出了第{i}份情报。" * 8)
    return "\n".join(chapters)


# ---------- chunking：章节切片 ----------


def test_chapter_spans_and_slice():
    text = _novel()
    spans = chapter_spans(text)
    assert len(spans) == 5
    assert spans[0]["title"].startswith("第一章")
    part, label, end = slice_by_chapter(text, 2, 4)
    assert label == "第 2–4 章"
    assert end == 4
    assert "试炼2" in part and "试炼4" in part and "试炼1" not in part and "试炼5" not in part
    # 越界夹取 + 单章 + 非法区间
    assert slice_by_chapter(text, 4, 99)[2] == 5
    assert slice_by_chapter(text, 3, 3)[1] == "第 3 章"
    with pytest.raises(ValueError):
        slice_by_chapter(text, 4, 2)


def test_chapter_spans_without_headings():
    spans = chapter_spans("没有章节标题的一段文字。" * 50)
    assert len(spans) == 1 and spans[0]["index"] == 1


# ---------- 建图 / 前情提要 / 选弧解析 ----------


def test_build_novel_map_summarizes_chapters():
    replies = [f"剧情：第{i}章的转折。\n人物：林然、红雨衣男人" for i in range(1, 6)]
    m = build_novel_map(_novel(), FakeLLM(replies))
    assert len(m["chapters"]) == 5
    assert not m["pseudo"]
    assert m["chapters"][2]["summary"] == "第3章的转折。"
    assert "红雨衣男人" in m["chapters"][0]["characters"]
    assert m["total_chars"] == len(_novel())


def test_build_novel_map_pseudo_and_guard():
    # 没有章节标题 → 伪章节
    m = build_novel_map("雨夜巷口的对峙。" * 2000, FakeLLM())
    assert m["pseudo"] and len(m["chapters"]) > 1
    # 模型不可用 → 明确报错而不是硬跑
    class _No:
        available = False

    with pytest.raises(ValueError):
        build_novel_map(_novel(), _No())


def test_previous_context_and_arcs():
    m = {"chapters": [
        {"index": i, "title": f"第{i}章", "summary": f"事件{i}", "characters": [], "chars": 100}
        for i in range(1, 6)
    ]}
    ctx = previous_context(m, 3)
    assert "事件1" in ctx and "事件3" in ctx and "事件4" not in ctx
    assert "第2章" in arcs_context(m, 2, 5) and "第5章" in arcs_context(m, 2, 5)
    assert "第1章" not in arcs_context(m, 2, 5)


def test_parse_arcs_extracts_json_from_noise():
    raw = '好的，以下是我的建议：```json\n[{"title":"巷口对峙","from":1,"to":3,"hook":"情报交易","why":"冲突密集"}]\n```'
    arcs = parse_arcs(raw)
    assert arcs[0]["title"] == "巷口对峙" and arcs[0]["to"] == 3
    with pytest.raises(ValueError):
        parse_arcs("没有数组的内容")
