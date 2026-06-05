"""Chapter splitting and text cleaning utilities."""
from __future__ import annotations

import re
from dataclasses import dataclass


# Common Chinese/English chapter heading patterns
# Order matters: more specific patterns (h2, "第一章") come first.
CHAPTER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^[\s>]*第\s*([0-9一二三四五六七八九十百千零〇两]+)\s*章[　\s]*(.*)$"),
    re.compile(r"^[\s>]*Chapter\s+([0-9]+|[IVXLCDM]+)[　\s:：\-]*(.*)$", re.IGNORECASE),
    re.compile(r"^[\s>]*CHAPTER\s+([0-9]+|[IVXLCDM]+)[　\s:：\-]*(.*)$"),
    # h2 (##) takes priority over h1 (#) so that "# Title" doesn't shadow "## 第一章"
    re.compile(r"^##\s+(.+)$"),
    re.compile(r"^#\s+(.+)$"),
)


@dataclass
class ChapterSplit:
    chapter_id: str
    title: str
    content: str


def clean_text(raw: str) -> str:
    """Normalize whitespace, drop nulls, collapse blank lines."""
    if not raw:
        return ""
    # strip BOM
    raw = raw.lstrip("﻿")
    # unify line endings
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    # collapse 3+ blank lines to 1
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    # collapse multiple spaces (but keep newlines)
    raw = re.sub(r"[ \t　]+", " ", raw)
    return raw.strip()


def split_chapters(raw_text: str, min_chapters: int = 3) -> list[ChapterSplit]:
    """Split text into chapters via heading detection.

    Falls back to length-based chunking if headings cannot be detected and
    fewer than `min_chapters` segments result.
    """
    text = clean_text(raw_text)
    if not text:
        raise ValueError("empty text")

    lines = text.split("\n")

    # First pass: collect candidate headings tagged with level.
    # level=0 → 第X章 / Chapter N, level=1 → ## (h2), level=2 → # (h1, treated as doc title)
    candidates: list[tuple[int, int, str]] = []  # (line_idx, level, title)
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if CHAPTER_PATTERNS[0].match(stripped) or CHAPTER_PATTERNS[1].match(stripped):
            m = CHAPTER_PATTERNS[0].match(stripped) or CHAPTER_PATTERNS[1].match(stripped)
            title = m.group(2).strip() if m and m.lastindex and m.lastindex >= 2 else stripped
            candidates.append((idx, 0, title or stripped))
        elif CHAPTER_PATTERNS[3].match(stripped):  # h2 ##
            title = stripped.lstrip("#").strip()
            candidates.append((idx, 1, title))
        elif CHAPTER_PATTERNS[4].match(stripped):  # h1 #
            title = stripped.lstrip("#").strip()
            candidates.append((idx, 2, title))

    # Prefer level<=1 headings; treat the first h1 as document title (skip it).
    h1_count = sum(1 for _, lvl, _ in candidates if lvl == 2)
    h2_or_chapter = [(i, t) for i, lvl, t in candidates if lvl <= 1]

    if not h2_or_chapter:
        # h1 only: treat each h1 as a chapter (no doc title separation)
        if h1_count:
            chapters = []
            for j, (line_idx, _, title) in enumerate([c for c in candidates if c[1] == 2]):
                end_line = (
                    [c[0] for c in candidates if c[1] == 2][j + 1]
                    if j + 1 < h1_count
                    else len(lines)
                )
                body = "\n".join(lines[line_idx + 1 : end_line]).strip()
                chapters.append(
                    ChapterSplit(chapter_id=f"chapter_{j + 1:03d}", title=title, content=body)
                )
            if len(chapters) >= min_chapters:
                return chapters
        return _split_by_length(text, min_chapters)

    # Drop a leading h1 (document title) if it appears before the first h2/chapter
    first_h1 = next((c for c in candidates if c[1] == 2), None)
    if first_h1 and h2_or_chapter and first_h1[0] < h2_or_chapter[0][0]:
        # skip it: do not include in headings
        pass

    chapters = []
    headings = h2_or_chapter
    for i, (line_idx, title) in enumerate(headings):
        end_line = headings[i + 1][0] if i + 1 < len(headings) else len(lines)
        body = "\n".join(lines[line_idx + 1 : end_line]).strip()
        chapters.append(
            ChapterSplit(
                chapter_id=f"chapter_{i + 1:03d}",
                title=title,
                content=body,
            )
        )

    if len(chapters) < min_chapters:
        return _split_by_length(text, min_chapters)

    return chapters


def _split_by_length(text: str, n: int) -> list[ChapterSplit]:
    """Fallback: split into roughly equal chunks by paragraphs."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        # last resort: hard split
        size = max(1, len(text) // n)
        return [
            ChapterSplit(
                chapter_id=f"chapter_{i + 1:03d}",
                title=f"第 {i + 1} 部分",
                content=text[i * size : (i + 1) * size].strip(),
            )
            for i in range(n)
        ]

    chunk_size = max(1, len(paragraphs) // n)
    remainder = len(paragraphs) % n
    chapters: list[ChapterSplit] = []
    cursor = 0
    for i in range(n):
        # distribute remainder into the first chunks
        take = chunk_size + (1 if i < remainder else 0)
        # ensure at least 1 paragraph per chunk
        take = max(1, take)
        chunk = paragraphs[cursor : cursor + take]
        cursor += take
        if not chunk:
            break
        chapters.append(
            ChapterSplit(
                chapter_id=f"chapter_{len(chapters) + 1:03d}",
                title=f"第 {len(chapters) + 1} 部分",
                content="\n\n".join(chunk),
            )
        )
    return chapters
