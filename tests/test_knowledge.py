# =====================================================================
# test_knowledge.py —— 改编知识 + 记忆系统测试（无 RAG 版）
#
# 覆盖：题材识别、作者风格提取、种子知识查询、用户记忆读写。
# =====================================================================

from app.pipeline.knowledge import (
    detect_genres,
    extract_author_style,
    format_genre_knowledge,
    get_all_genre_knowledge,
    get_genre_conventions,
)
from app.pipeline.memory import format_memories, recall_memories, save_memory


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


def test_get_genre_conventions():
    conv = get_genre_conventions("悬疑")
    assert "plot_direction" in conv
    assert "technique" in conv
    assert len(conv["plot_direction"]) > 0
    assert len(conv["technique"]) > 0


def test_get_genre_conventions_unknown():
    """未知题材回退到「通用」。"""
    conv = get_genre_conventions("不存在的题材")
    assert conv == get_genre_conventions("通用")


def test_get_all_genre_knowledge():
    knowledge = get_all_genre_knowledge(["悬疑", "情感"])
    assert "plot_direction" in knowledge
    assert "technique" in knowledge
    # 合并后应有去重
    assert len(knowledge["plot_direction"]) > 0


def test_format_genre_knowledge():
    text = format_genre_knowledge(["悬疑"])
    assert "悬疑" in text
    assert "可能走向" in text
    assert "写作手法" in text


def test_format_author_style(sample_text):
    from app.pipeline.knowledge import format_author_style
    text = format_author_style(sample_text)
    assert "作者语言风格" in text
    assert len(text) > 20


# ---------- 记忆系统 ----------


def test_save_and_recall_memory(store):
    p = store.create_project(title="测试", adaptation_type="short_drama", language="zh-CN", raw_text="原文")
    save_memory(store, kind="preference", content="用户偏好冷峻风格", scope="project", project_id=p.id)
    save_memory(store, kind="decision", content="第3场戏冻结不动", scope="project", project_id=p.id)

    memories = recall_memories(store, project_id=p.id)
    assert len(memories) >= 2
    contents = [m["content"] for m in memories]
    assert "用户偏好冷峻风格" in contents
    assert "第3场戏冻结不动" in contents


def test_memory_scope_isolation(store):
    """不同项目的记忆应隔离。"""
    p1 = store.create_project(title="A", adaptation_type="short_drama", language="zh-CN", raw_text="")
    p2 = store.create_project(title="B", adaptation_type="film", language="zh-CN", raw_text="")

    save_memory(store, kind="preference", content="项目A偏好", scope="project", project_id=p1.id)
    save_memory(store, kind="preference", content="项目B偏好", scope="project", project_id=p2.id)

    mem1 = recall_memories(store, project_id=p1.id)
    mem2 = recall_memories(store, project_id=p2.id)

    assert any("项目A偏好" in m["content"] for m in mem1)
    assert not any("项目B偏好" in m["content"] for m in mem1)
    assert any("项目B偏好" in m["content"] for m in mem2)


def test_global_memory_visible_everywhere(store):
    """全局记忆在所有项目中可见。"""
    save_memory(store, kind="preference", content="全局偏好", scope="global")
    p = store.create_project(title="测试", adaptation_type="short_drama", language="zh-CN", raw_text="")
    memories = recall_memories(store, project_id=p.id)
    assert any("全局偏好" in m["content"] for m in memories)


def test_format_memories():
    docs = [
        {"kind": "preference", "content": "喜欢冷峻风格"},
        {"kind": "decision", "content": "第3场冻结"},
    ]
    text = format_memories(docs)
    assert "用户偏好" in text
    assert "冷峻风格" in text
    assert "项目决策" in text


def test_format_memories_empty():
    assert format_memories([]) == ""
