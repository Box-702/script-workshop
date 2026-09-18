# =====================================================================
# test_knowledge.py —— 题材识别与作者风格测试
#
# 覆盖：题材识别（含兜底）、作者风格画像与格式化。
# =====================================================================

from app.pipeline.knowledge import (
    detect_genres,
    extract_author_style,
    format_author_style,
)


def test_detect_genres():
    text = "雨夜命案现场，侦探发现证据链断裂。凶手留下的照片藏着真相，案件调查陷入僵局，阴谋浮出水面。"
    genres = detect_genres(text)
    assert isinstance(genres, list) and genres
    assert "悬疑" in genres


def test_detect_genres_fallback():
    """无关键词命中时回退到「通用」。"""
    genres = detect_genres("今天天气真好")
    assert genres == ["通用"]


def test_extract_author_style(sample_text):
    profile = extract_author_style(sample_text)
    assert "summary" in profile
    assert "metrics" in profile
    m = profile["metrics"]
    assert m["avg_sentence_len"] > 0
    assert 0 <= m["dialogue_ratio"] <= 1
    assert profile["summary"].strip()


def test_format_author_style(sample_text):
    text = format_author_style(sample_text)
    assert "作者语言风格" in text
    assert len(text) > 20
