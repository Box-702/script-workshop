# =====================================================================
# vector.py —— 文本切片工具（仅保留 chunk_text）
#
# 原有的 RAG 向量检索层已移除。本文件仅保留文本结构化切片功能，
# 供 generation.py 在组装 LLM prompt 时使用。
# =====================================================================

from __future__ import annotations

import re
from dataclasses import dataclass

# 中文章节标题模式。
_CHAPTER_RE = re.compile(
    r"^\s*(第[零一二三四五六七八九十百千万0-9]+[章节卷回部集]|"
    r"Chapter\s*\d+|序章|楔子|尾声|番外|引子|后记|前言)[^\n]{0,30}$"
)

# 句子边界。
_SENT_RE = re.compile(r"[^。！？!?；;…]+[。！？!?；;…]*")


@dataclass
class Chunk:
    """一个结构化的原文切片。"""

    text: str
    chapter: str = ""
    chapter_index: int = 0
    start: int = 0


def _split_sentences(line: str) -> list[str]:
    parts = [p.strip() for p in _SENT_RE.findall(line or "") if p.strip()]
    return parts or ([line.strip()] if line.strip() else [])


def _make_chunk(sents: list[str], chapter: str, chapter_index: int, start: int) -> Chunk:
    text = "".join(sents).strip()
    return Chunk(text=text, chapter=chapter, chapter_index=chapter_index, start=start)


def split_chunks(
    text: str,
    *,
    target_size: int = 500,
    max_size: int = 800,
    overlap_sentences: int = 1,
) -> list[Chunk]:
    """结构化切片：章节感知 + 句子边界 + 语义完整。"""
    if not text:
        return []
    segments: list[tuple[str, int, list[str]]] = []
    cur_chapter, cur_ci, cur_sents = "", 0, []

    def _flush() -> None:
        nonlocal cur_sents
        if cur_sents:
            segments.append((cur_chapter, cur_ci, cur_sents))
            cur_sents = []

    for line in text.split("\n"):
        stripped = line.strip()
        if _CHAPTER_RE.match(stripped) and len(stripped) <= 40:
            _flush()
            cur_chapter = stripped
            cur_ci += 1
            continue
        cur_sents.extend(_split_sentences(line))
    _flush()

    chunks: list[Chunk] = []
    offset = 0
    for chap, ci, sents in segments:
        buf: list[str] = []
        buf_len = 0
        for sent in sents:
            if buf_len + len(sent) > max_size and buf:
                chunks.append(_make_chunk(buf, chap, ci, offset))
                offset += buf_len
                keep = buf[-overlap_sentences:] if overlap_sentences > 0 else []
                buf = keep[:]
                buf_len = sum(len(s) for s in buf)
            buf.append(sent)
            buf_len += len(sent)
            if buf_len >= target_size:
                chunks.append(_make_chunk(buf, chap, ci, offset))
                offset += buf_len
                keep = buf[-overlap_sentences:] if overlap_sentences > 0 else []
                buf = keep[:]
                buf_len = sum(len(s) for s in buf)
        if buf:
            chunks.append(_make_chunk(buf, chap, ci, offset))
            offset += buf_len
    return chunks


def chunk_text(text: str, *, chunk_size: int = 800, overlap: int = 120) -> list[str]:
    """兼容旧接口：返回纯文本块列表。"""
    target = max(200, chunk_size - overlap) if chunk_size > 200 else 400
    return [c.text for c in split_chunks(text, target_size=target, max_size=chunk_size, overlap_sentences=1)]
