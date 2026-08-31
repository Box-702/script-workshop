# =====================================================================
# test_patch.py —— patch 引擎单元测试
#
# 验证：结构化提议 -> 操作清单 -> 应用 -> 校验/回退，这一核心领域逻辑
# 在不依赖模型、数据库、向量库的情况下正确且稳定。
# =====================================================================

from app.patch import (
    PatchProposal,
    SceneChange,
    BeatChange,
    DialogueChange,
    apply_patch,
    build_patch,
    fallback_patch,
    make_source_script,
    validate_script,
)


def _base_script():
    return make_source_script("雨夜", "这里有一段原著文本，用来生成场景。", adaptation_type="short_drama")


def test_make_source_script_is_valid():
    script = _base_script()
    assert script.title == "雨夜"
    assert len(script.scenes) == 1
    assert not [i for i in validate_script(script) if i.severity == "error"]


def test_build_patch_title_and_beats():
    script = _base_script()
    proposal = PatchProposal(
        plan=["把标题改得更抓人", "重构节拍"],
        changes=[
            SceneChange(
                scene_id="scene_001",
                title="雨夜对峙",
                beats=[
                    BeatChange(id="beat_001", type="action", text="林然推门而入"),
                    BeatChange(type="dialogue", speaker="char_protagonist", line="你终于来了。"),
                ],
            )
        ],
    )
    plan, ops = build_patch(proposal, script, selected_scene_ids=[], instruction="改编")
    assert any(op.field == "title" for op in ops)
    assert any(op.field == "beats" for op in ops)
    # 应用后应当仍然合法。
    new_script = apply_patch(script, ops)
    assert new_script.scenes[0].title == "雨夜对峙"
    # 改回的标题可被校验通过。
    assert not [i for i in validate_script(new_script) if i.severity == "error"]


def test_apply_patch_produces_valid_version():
    script = _base_script()
    ops = [
        {"op": "set", "path": "/script/scenes/0/title", "value": "雨夜"},
    ]
    from app.patch import PatchOp

    new_script = apply_patch(script, [PatchOp.model_validate(o) for o in ops])
    assert new_script.scenes[0].title == "雨夜"


def test_validate_catches_missing_character_ref():
    script = _base_script()
    # 人为往场景里塞一个不存在的角色引用。
    script.scenes[0].characters.append("char_ghost")
    issues = [i for i in validate_script(script) if i.severity == "error"]
    assert any("char_ghost" in i.message for i in issues)


def test_fallback_patch_writes_notes():
    script = _base_script()
    plan, ops = fallback_patch(script, "把节奏改紧凑", [])
    assert ops, "无模型时也应产出可接受的说明性 patch"
    new_script = apply_patch(script, ops)
    # 生成的版本仍应合法。
    assert not [i for i in validate_script(new_script) if i.severity == "error"]
