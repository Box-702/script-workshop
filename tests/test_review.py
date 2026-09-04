# =====================================================================
# test_review.py —— 审阅 / 一致性保障 / 评审打分 模块测试
#
# 测试在没有模型 key 时也能跑（conftest 保证 llm.available=False），
# 从而验证：
#   - PatchReview / ReviewDimension / ReviewIssue 的模型校验；
#   - review_patch 在无模型时安全返回 None（上层走纯规则校验）；
#   - _build_review_context 能组装出「人物设定 + 改动场景 + 知识」的审阅输入。
# =====================================================================

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.patch import make_source_script
from app.review import (
    DIMENSION_LABELS,
    PatchReview,
    ReviewDimension,
    ReviewIssue,
    _build_review_context,
    review_patch,
)


def _base() -> object:
    return make_source_script("测试剧", "主角推门进入房间。\n他看见了桌上的信。", adaptation_type="short_drama")


def test_review_models_validate():
    r = PatchReview(
        overall_score=88,
        passed=True,
        summary="整体不错",
        dimensions=[ReviewDimension(name="consistency", score=90, note="角色一致")],
        issues=[ReviewIssue(severity="warning", category="style", message="节奏可再打磨")],
    )
    assert r.overall_score == 88
    assert r.passed is True
    assert r.dimensions[0].score == 90
    assert r.issues[0].severity == "warning"


def test_review_models_reject_invalid():
    with pytest.raises(ValidationError):
        PatchReview(overall_score=150)  # 超出 0-100
    with pytest.raises(ValidationError):
        ReviewIssue(severity="fatal", category="consistency", message="x")  # 非法 severity


def test_review_patch_returns_none_without_model(llm):
    # no model -> 上层走纯规则校验（确定性），不触发 LLM 审阅。
    base = _base()
    assert review_patch(llm, base=base, applied=base, instruction="把节奏改紧凑") is None


def test_build_review_context_contains_instruction_and_details():
    base = _base()
    # 让 applied 与 base 存在一处改动，保证评审输入包含「被改动场景」。
    applied = base.model_copy(deep=True)
    applied.scenes[0].purpose = "改过的场景目的"
    ctx = _build_review_context(base, applied, "把对白改口语一点", None, "zh-CN")
    assert "把对白改口语一点" in ctx
    assert "人物设定" in ctx
    assert "场景" in ctx
    assert "改过的场景目的" in ctx


def test_dimension_labels_complete():
    for key in ("fidelity", "consistency", "conflict", "style", "structure"):
        assert key in DIMENSION_LABELS
