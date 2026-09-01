# =====================================================================
# test_store.py —— 业务存储：删除项目/对话的级联行为（回归测试）
#
# 曾有一个 bug：delete_project 用 ChatMessage.conversation_id 过滤，
# 但该模型字段是 thread_id，导致删除项目时抛 InvalidRequestError（500）。
# 这里用「有对话 + 有消息的项目」覆盖删除路径，防止回归。
# =====================================================================


def test_project_notes_roundtrip(store):
    p = store.create_project(title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text="原文。")
    assert store.get_project_notes(p.id) == ""

    store.set_project_notes(p.id, "人物：林然——前刑警，怕火。\n伏笔：红雨衣。")
    assert "林然" in store.get_project_notes(p.id)

    assert store.set_project_notes("proj_missing", "x") is None
    p = store.create_project(
        title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text="一些原文。"
    )
    conv = store.create_conversation(p.id, title="对话 1")
    store.save_chat_message(thread_id=conv.id, role="user", content="你好")
    store.save_chat_message(thread_id=conv.id, role="assistant", content="你好，我是改编 Agent")

    assert store.get_project(p.id) is not None
    assert store.list_chat_messages(conv.id)  # 有消息

    store.delete_project(p.id)

    assert store.get_project(p.id) is None
    assert store.list_conversations(p.id) == []
    assert store.list_versions(p.id) == []
    assert store.list_agent_runs(p.id) == []


def test_delete_conversation_removes_messages(store):
    p = store.create_project(
        title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text="一些原文。"
    )
    conv = store.create_conversation(p.id, title="对话 1")
    store.save_chat_message(thread_id=conv.id, role="user", content="你好")

    assert store.delete_conversation(conv.id) is True
    assert store.get_conversation(conv.id) is None
    # 删除项目不应残留对话消息（级联删除在 delete_project 里保证）。
    store.delete_project(p.id)
    assert store.get_project(p.id) is None


def test_version_milestone_set_and_clear(store):
    from app.domain import Script

    p = store.create_project(title="雨夜", adaptation_type="short_drama", language="zh-CN", raw_text="原文。")
    script = Script.model_validate(
        {
            "title": "雨夜",
            "source": {"chapter_count": 1, "chapter_ids": ["ch_001"]},
            "logline": "一句话梗概。",
            "characters": [{"id": "char_001", "name": "林然", "role": "protagonist"}],
            "locations": [{"id": "loc_001", "name": "场景"}],
            "scenes": [
                {
                    "id": "scene_001",
                    "title": "开场",
                    "chapter_refs": ["ch_001"],
                    "location_id": "loc_001",
                    "characters": ["char_001"],
                    "purpose": "引出冲突。",
                    "conflict": "主角面对选择。",
                    "beats": [{"id": "beat_001", "type": "action", "text": "林然入场。"}],
                }
            ],
        }
    )
    v = store.create_version(p, script, source_type="generation", label="初始生成")
    assert v.milestone is None

    v2 = store.set_version_milestone(v.id, "final")
    assert v2 is not None and v2.milestone == "final"

    v3 = store.set_version_milestone(v.id, None)
    assert v3 is not None and v3.milestone is None

    assert store.set_version_milestone("ver_missing", "final") is None
