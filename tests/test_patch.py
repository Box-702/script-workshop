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


# ---------- 回归测试：白名单与对白保留 ----------


def _script_with_dialogue():
    """构造一个「动作 + 对白」混合节拍流的剧本（模拟真实生成产物）。"""
    script = _base_script()
    proposal = PatchProposal(
        changes=[
            SceneChange(
                scene_id="scene_001",
                beats=[
                    BeatChange(id="beat_001", type="action", text="林然推门而入"),
                    BeatChange(id="beat_002", type="dialogue", speaker="char_protagonist", line="你终于来了。"),
                ],
            )
        ]
    )
    _, ops = build_patch(proposal, script, selected_scene_ids=[], instruction="改编")
    return apply_patch(script, ops)


def test_action_only_change_preserves_dialogue_beats():
    """回归：提议只改 action、不带 beats/dialogue 时，既有对白节拍不能被冲掉。"""
    script = _script_with_dialogue()
    assert any(b.type == "dialogue" for b in script.scenes[0].beats)

    proposal = PatchProposal(changes=[SceneChange(scene_id="scene_001", action=["新的动作描写"])])
    _, ops = build_patch(proposal, script, selected_scene_ids=[], instruction="改动作")
    new_script = apply_patch(script, ops)
    dialogue_lines = [b.line for b in new_script.scenes[0].beats if b.type == "dialogue"]
    assert "你终于来了。" in dialogue_lines


def test_build_patch_respects_selected_scene_whitelist():
    """回归：模型提议修改未勾选的场景时，必须被白名单拦下。"""
    from copy import deepcopy

    from app.domain import Script

    script = _script_with_dialogue()
    data = script.model_dump(exclude_none=False)
    second = deepcopy(data["scenes"][0])
    second["id"] = "scene_002"
    second["title"] = "第二场"
    data["scenes"].append(second)
    script = Script.model_validate(data)

    proposal = PatchProposal(
        changes=[
            SceneChange(scene_id="scene_001", title="改第一场"),
            SceneChange(scene_id="scene_002", title="越权改第二场"),
        ]
    )
    _, ops = build_patch(proposal, script, selected_scene_ids=["scene_001"], instruction="改编")
    assert ops, "选中场景的改动不应被丢弃"
    assert all(op.scene_id == "scene_001" for op in ops)

    # 未勾选（空列表）时维持原语义：全部场景都可改。
    _, ops_all = build_patch(proposal, script, selected_scene_ids=[], instruction="改编")
    assert {op.scene_id for op in ops_all} == {"scene_001", "scene_002"}


def test_clean_beats_resolves_speaker_names():
    """回归：LLM 用人物名指代说话人时应解析为角色 id，而不是静默指给场景第一个角色。"""
    script = _base_script()  # 人物：主角（char_protagonist）
    proposal = PatchProposal(
        changes=[
            SceneChange(
                scene_id="scene_001",
                beats=[BeatChange(type="dialogue", speaker="主角", line="你终于来了。")],
            )
        ]
    )
    _, ops = build_patch(proposal, script, selected_scene_ids=[], instruction="改编")
    applied = apply_patch(script, ops)
    dlg = [b for b in applied.scenes[0].beats if b.type == "dialogue"]
    assert dlg and dlg[0].speaker == "char_protagonist"


def test_clean_beats_keeps_unknown_speaker_for_validation():
    """回归：说话人解析不了时保留原值交由校验回炉，而不是静默安到别的角色头上。"""
    script = _base_script()
    proposal = PatchProposal(
        changes=[
            SceneChange(
                scene_id="scene_001",
                beats=[BeatChange(type="dialogue", speaker="陌生人", line="把东西交出来。")],
            )
        ]
    )
    _, ops = build_patch(proposal, script, selected_scene_ids=[], instruction="改编")
    applied = apply_patch(script, ops)
    dlg = [b for b in applied.scenes[0].beats if b.type == "dialogue"]
    assert dlg and dlg[0].speaker != "char_protagonist"  # 不能错归给主角
    issues = [i for i in validate_script(applied) if i.severity == "error"]
    assert any("说话人" in i.message for i in issues), "未知说话人必须被校验拦下"
