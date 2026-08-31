# =====================================================================
# test_chat.py —— 对话式 Agent 测试
#
# 无模型 key 环境下验证：
#   1. 对话工具层：create_project -> generate_script -> run_adaptation
#      -> resume(accept) 全链路闭环（底层仍是 LangGraph 工作流）；
#   2. 审阅确定性路径：reject / 已处理防重；
#   3. chat_once 无模型回退：消息持久化 + 历史读取。
# =====================================================================

from app.chat import _handle_resume, build_chat_tools, chat_once, load_history
from app.vector import HashingEmbedder


def _embedder():
    return HashingEmbedder(dim=768)


def _make_tools(store, llm, settings, vector_store):
    collector = {"project_id": None, "payloads": []}
    tools = {t.name: t for t in build_chat_tools(store, llm, settings, vector_store, _embedder(), collector)}
    return tools, collector


def test_chat_tool_flow_closed_loop(store, llm, settings, vector_store, sample_text):
    tools, collector = _make_tools(store, llm, settings, vector_store)

    # 1) 对话式「新建剧本」
    r = tools["create_project"].invoke({"title": "雨夜", "adaptation_type": "短剧", "raw_text": sample_text})
    assert "已创建剧本项目《雨夜》" in r
    pid = collector["project_id"]
    assert pid and store.get_project(pid)

    # 2) 生成初稿
    r = tools["generate_script"].invoke({"project_id": pid})
    assert "已生成初稿" in r
    version = store.latest_version(store.get_project(pid))
    assert version is not None and version.source_type == "generation"

    # 3) 改编（底层工作流跑到 review 中断）
    r = tools["run_adaptation"].invoke({"project_id": pid, "instruction": "把对白改口语一点"})
    assert "改动建议" in r
    assert collector["payloads"], "应产生 patch_review 载荷"
    review = collector["payloads"][0]
    assert review["type"] == "patch_review" and review["run_id"]
    assert review["patch"], "无模型回退也应产出可审阅 patch"
    assert store.get_agent_run(review["run_id"]).status == "reviewing"

    # 4) 审阅：接受全部 -> 生成新版本
    res = _handle_resume(
        store, llm, settings, vector_store, _embedder(),
        run_id=review["run_id"], action="accept", patch_indexes=None, feedback=None, patch=None,
    )
    assert res["payloads"][0]["type"] == "version_applied", res
    new_vid = res["payloads"][0]["version_id"]
    new_version = store.get_version(new_vid)
    assert new_version.source_type == "agent_adaptation"


def test_chat_tool_reject(store, llm, settings, vector_store, sample_text):
    tools, collector = _make_tools(store, llm, settings, vector_store)
    tools["create_project"].invoke({"title": "雨夜", "adaptation_type": "short_drama", "raw_text": sample_text})
    pid = collector["project_id"]
    tools["generate_script"].invoke({"project_id": pid})
    tools["run_adaptation"].invoke({"project_id": pid, "instruction": "改紧凑"})
    run_id = collector["payloads"][0]["run_id"]

    res = _handle_resume(
        store, llm, settings, vector_store, _embedder(),
        run_id=run_id, action="reject", patch_indexes=None, feedback=None, patch=None,
    )
    assert "拒绝" in res["reply"]
    assert store.get_agent_run(run_id).status == "rejected"

    # 防重：再次操作应提示已处理
    res2 = _handle_resume(
        store, llm, settings, vector_store, _embedder(),
        run_id=run_id, action="accept", patch_indexes=None, feedback=None, patch=None,
    )
    assert "已处理过" in res2["reply"]


def test_chat_once_persists_history(store, llm, settings, vector_store, sample_text):
    tools, collector = _make_tools(store, llm, settings, vector_store)
    tools["create_project"].invoke({"title": "雨夜", "adaptation_type": "short_drama", "raw_text": sample_text})
    pid = collector["project_id"]
    conv = store.ensure_default_conversation(pid)
    assert conv.project_id == pid

    # 无模型：conductor 回退提示，但消息应持久化、历史可读。
    out = chat_once(store, llm, settings, vector_store, _embedder(),
                    conversation_id=conv.id, project_id=pid, message="你好", meta=None)
    assert out["thread_id"] == conv.id
    assert "没有配置对话模型" in out["reply"]

    hist = load_history(store, conv.id)
    assert len(hist) == 2
    assert hist[0]["role"] == "user" and hist[0]["content"] == "你好"
    assert hist[1]["role"] == "assistant"

    # 全局线程（新建剧本会话）与项目对话隔离。
    assert load_history(store, None) == []


def test_project_multiple_conversations_isolated(store, llm, settings, vector_store, sample_text):
    """一个项目下多个对话：上下文与历史彼此隔离。"""
    tools, collector = _make_tools(store, llm, settings, vector_store)
    tools["create_project"].invoke({"title": "雨夜", "adaptation_type": "short_drama", "raw_text": sample_text})
    pid = collector["project_id"]

    conv_a = store.create_conversation(pid, title="对话A")
    conv_b = store.create_conversation(pid, title="对话B")
    assert len(store.list_conversations(pid)) >= 2

    chat_once(store, llm, settings, vector_store, _embedder(),
              conversation_id=conv_a.id, project_id=pid, message="在A里说", meta=None)
    assert len(load_history(store, conv_a.id)) == 2
    assert len(load_history(store, conv_b.id)) == 0, "B 对话不应看到 A 的消息"

    # 重命名 / 删除
    renamed = store.rename_conversation(conv_b.id, "对话B-改名")
    assert renamed.title == "对话B-改名"
    assert store.delete_conversation(conv_b.id)
    assert store.get_conversation(conv_b.id) is None


def test_chat_resume_via_meta(store, llm, settings, vector_store, sample_text):
    """前端审阅按钮走后端 chat 接口（meta.intent=resume）也应闭环。"""
    tools, collector = _make_tools(store, llm, settings, vector_store)
    tools["create_project"].invoke({"title": "雨夜", "adaptation_type": "short_drama", "raw_text": sample_text})
    pid = collector["project_id"]
    conv = store.ensure_default_conversation(pid)
    tools["generate_script"].invoke({"project_id": pid})
    tools["run_adaptation"].invoke({"project_id": pid, "instruction": "改节奏"})
    run_id = collector["payloads"][0]["run_id"]

    out = chat_once(
        store, llm, settings, vector_store, _embedder(),
        conversation_id=conv.id, project_id=pid, message="",
        meta={"intent": "resume", "run_id": run_id, "action": "accept", "patch_indexes": None},
    )
    assert out["payloads"][0]["type"] == "version_applied", out
    assert "已接受" in out["reply"]
    hist = load_history(store, conv.id)
    assert any(m["role"] == "user" and "接受" in m["content"] for m in hist)
