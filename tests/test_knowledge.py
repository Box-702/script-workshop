# =====================================================================
# test_knowledge.py —— 项目级改编知识 RAG 测试
#
# 覆盖：题材识别、作者风格提取、知识索引/检索、按 kind 过滤、
# 项目间隔离、对话记忆写入。
# =====================================================================

from app.knowledge import (
    detect_genres,
    extract_author_style,
    index_project_knowledge,
    remember_knowledge,
    retrieve_knowledge,
)
from app.vector import HashingEmbedder


def _embedder():
    return HashingEmbedder(dim=768)


def test_detect_genres():
    text = "雨夜命案现场，侦探发现证据链断裂。凶手留下的照片藏着真相，案件调查陷入僵局，阴谋浮出水面。"
    genres = detect_genres(text)
    assert isinstance(genres, list) and genres
    assert "悬疑" in genres


def test_extract_author_style(sample_text):
    profile = extract_author_style(sample_text)
    assert "summary" in profile
    assert "metrics" in profile
    m = profile["metrics"]
    assert m["avg_sentence_len"] > 0
    assert 0 <= m["dialogue_ratio"] <= 1
    assert profile["summary"].strip()


def test_index_and_retrieve_knowledge(store, vector_store, sample_text):
    p = store.create_project(title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text=sample_text)
    counts = index_project_knowledge(
        vector_store, _embedder(), project_id=p.id, raw_text=p.raw_text, title=p.title
    )
    assert counts["knowledge_docs"] > 0
    assert counts["source_chunks"] > 0

    hits = retrieve_knowledge(
        vector_store, _embedder(), project_id=p.id,
        query="悬疑短剧的反转怎么设计", k=2, kinds=["plot_direction"],
    )
    assert hits, "应能检索到同类剧本走向"
    assert all(h["kind"] == "plot_direction" for h in hits)

    style_hits = retrieve_knowledge(
        vector_store, _embedder(), project_id=p.id, query="作者写作风格", k=1, kinds=["author_style"]
    )
    assert style_hits and style_hits[0]["kind"] == "author_style"


def test_project_isolation(store, vector_store, sample_text):
    p1 = store.create_project(title="A", adaptation_type="short_drama", language="zh-CN", raw_text=sample_text)
    p2 = store.create_project(title="B", adaptation_type="film", language="zh-CN", raw_text="都市职场 爱情")
    index_project_knowledge(vector_store, _embedder(), project_id=p1.id, raw_text=p1.raw_text, title=p1.title)
    index_project_knowledge(vector_store, _embedder(), project_id=p2.id, raw_text=p2.raw_text, title=p2.title)

    hits = retrieve_knowledge(vector_store, _embedder(), project_id=p1.id, query="反转", k=5)
    for h in hits:
        assert h.get("source") != "genre:都市", "项目 A 不应检索到项目 B 的题材知识"


def test_remember_knowledge(store, vector_store, sample_text):
    p = store.create_project(title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text=sample_text)
    index_project_knowledge(vector_store, _embedder(), project_id=p.id, raw_text=p.raw_text, title=p.title)
    ok = remember_knowledge(
        vector_store, _embedder(), project_id=p.id,
        kind="author_style", content="作者偏好冷峻、留白，不喜欢说教。",
    )
    assert ok
    hits = retrieve_knowledge(vector_store, _embedder(), project_id=p.id, query="作者偏好", k=2, kinds=["author_style"])
    assert any("留白" in h["text"] or "冷峻" in h["text"] for h in hits)

    bad = remember_knowledge(vector_store, _embedder(), project_id=p.id, kind="unknown", content="x")
    assert not bad


def test_list_project_rows(store, vector_store, sample_text):
    p = store.create_project(title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text=sample_text)
    index_project_knowledge(vector_store, _embedder(), project_id=p.id, raw_text=p.raw_text, title=p.title)
    rows = vector_store.list_project(p.id)
    kinds = {r.get("kind") for r in rows}
    assert {"source", "plot_direction", "technique", "author_style"} <= kinds


def test_hybrid_retrieve_rejects_gibberish_query(store, vector_store, sample_text):
    """回归：无关查询不应因 min-max 归一化而必然拿到「高相关」结果。"""
    from app.vector import hybrid_retrieve

    p = store.create_project(title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text=sample_text)
    index_project_knowledge(vector_store, _embedder(), project_id=p.id, raw_text=sample_text, title=p.title)

    gibberish = "zzz qqq xyzzy plugh wubble"
    hits = hybrid_retrieve(vector_store, _embedder(), project_id=p.id, query=gibberish, k=4)
    assert hits == [], f"无关查询不应返回噪声，实际返回 {len(hits)} 条"
