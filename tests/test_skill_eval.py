# =====================================================================
# test_skill_eval.py —— 技能加载 eval 的 harness 自检
#
# 这个 eval 测的是「Agent 的行为」，如果 harness 本身有 bug，结论就是假的。
# 下面锁住三件容易错的事：
#   1. 「尝试加载」不等于「加载成功」——消融组里 load_skill 工具不存在，
#      模型照样会尝试调用（系统提示写着「先 load_skill」），那次尝试必须不算成功；
#   2. 消融开关真的把工具摘掉了；
#   3. 判定逻辑本身（触发/串味/顺序/前置）。
# =====================================================================

from __future__ import annotations

from evals.skill_cases import (
    ALL_SKILL_CASES,
    SkillCase,
    called_tools,
    loaded_skills,
)
from evals.skill_eval import evaluate


def _tool_call(name: str, args: str = "{}") -> dict:
    return {"type": "tool_call", "name": name, "args": args}


def _tool_result(name: str, summary: str) -> dict:
    return {"type": "tool_result", "name": name, "summary": summary}


def test_attempted_load_is_not_counted_as_loaded():
    """模型在工具不存在时仍会尝试调用 —— 那次尝试不算「加载成功」。"""
    events = [
        _tool_call("load_skill", '{"name": "crew-pipeline"}'),
        _tool_result("load_skill", "未知工具：load_skill。可用工具：a、b。"),
    ]
    assert loaded_skills(events) == [], "工具不存在时的尝试被误判成加载成功了"


def test_failed_load_is_not_counted():
    events = [
        _tool_call("load_skill", '{"name": "crew-pipeline"}'),
        _tool_result("load_skill", "没有这个技能：crew-pipeline。可加载：x。"),
    ]
    assert loaded_skills(events) == []


def test_successful_load_is_counted():
    events = [
        _tool_call("load_skill", '{"name": "crew-pipeline"}'),
        _tool_result("load_skill", "依赖关系是硬的，不是建议……"),
    ]
    assert loaded_skills(events) == ["crew-pipeline"]


def test_load_result_without_matching_call_is_ignored():
    events = [_tool_result("load_skill", "正文")]
    assert loaded_skills(events) == []


def test_called_tools_keeps_order():
    events = [
        _tool_call("get_status"),
        _tool_call("load_skill", '{"name": "x"}'),
        _tool_call("breakdown_scenes"),
    ]
    assert called_tools(events) == ["get_status", "load_skill", "breakdown_scenes"]


def test_evaluate_detects_correct_skill_and_order():
    case = SkillCase(
        id="t", name="t", request="r",
        expect_skill="crew-pipeline",
        forbid_skills=["novel-serial"],
        expect_tools=["breakdown_scenes", "generate_style_guide"],
        expect_order=["breakdown_scenes", "generate_style_guide"],
    )
    events = [
        _tool_call("load_skill", '{"name": "crew-pipeline"}'),
        _tool_result("load_skill", "细则正文"),
        _tool_call("breakdown_scenes"),
        _tool_call("generate_style_guide"),
    ]
    checks = evaluate(case, events, "回复")
    assert all(ok for _, ok, _ in checks), [c for c in checks if not c[1]]


def test_evaluate_detects_wrong_order():
    case = SkillCase(
        id="t", name="t", request="r",
        expect_skill="crew-pipeline",
        expect_tools=["breakdown_scenes", "generate_style_guide"],
        expect_order=["breakdown_scenes", "generate_style_guide"],
    )
    events = [
        _tool_call("load_skill", '{"name": "crew-pipeline"}'),
        _tool_result("load_skill", "细则正文"),
        _tool_call("generate_style_guide"),
        _tool_call("breakdown_scenes"),
    ]
    checks = evaluate(case, events, "回复")
    order_check = [c for c in checks if "依赖顺序" in c[0]]
    assert order_check and not order_check[0][1], "乱序没有被抓出来"


def test_evaluate_detects_cross_contamination():
    case = SkillCase(
        id="t", name="t", request="r",
        expect_skill="crew-pipeline",
        forbid_skills=["novel-serial"],
    )
    events = [
        _tool_call("load_skill", '{"name": "novel-serial"}'),
        _tool_result("load_skill", "细则"),
    ]
    checks = evaluate(case, events, "回复")
    contam = [c for c in checks if "不相关" in c[0]]
    assert contam and not contam[0][1], "串味没有被抓出来"


def test_evaluate_flags_over_trigger():
    case = SkillCase(id="t", name="t", request="r", expect_skill=None)
    events = [
        _tool_call("load_skill", '{"name": "crew-pipeline"}'),
        _tool_result("load_skill", "细则"),
    ]
    checks = evaluate(case, events, "回复")
    over = [c for c in checks if "过度触发" in c[0]]
    assert over and not over[0][1], "过度触发没有被抓出来"


def test_evaluate_flags_missing_precondition():
    """该拦的没拦（比如没批准就提交出片）必须被抓出来。"""
    case = SkillCase(
        id="t", name="t", request="r",
        expect_skill="production-delivery",
        forbid_tools=["submit_videos"],
    )
    events = [_tool_call("submit_videos")]
    checks = evaluate(case, events, "回复")
    bad = [c for c in checks if "submit_videos" in c[0]]
    assert bad and not bad[0][1]


def test_all_cases_have_expectations():
    """每条用例都要有可判定的期望，否则它只是跑了个热闹。

    注意反向用例（expect_skill=None）本身就是期望：「不该加载任何技能」。
    """
    for case in ALL_SKILL_CASES:
        assert case.expect_skill or case.forbid_skills, f"{case.id} 没有任何技能期望"
        has_behavior = (
            case.expect_tools or case.forbid_tools or case.expect_reply_contains
            or case.expect_order
        )
        # 反向用例靠「不加载」这一条判定，不需要工具期望
        if case.expect_skill is None:
            assert case.forbid_skills, f"{case.id} 是反向用例，却没有列出不该加载的技能"
        else:
            assert has_behavior, f"{case.id} 没有可判定的行为期望"
        assert case.why.strip(), f"{case.id} 没写验证目的"
