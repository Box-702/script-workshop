# =====================================================================
# test_dramaturgy.py —— 「先戏剧，后语法」确定性审计核心测试
#
# 方法论落地的硬规则全部在本模块，这里固化每一类的判定与误伤边界：
#   - 占位词：检测 + 保守剥除（整段占位才删，混写句保留给审计告警）；
#   - 否定句：检测，但引号内的实体招牌（「禁止入内」）不误伤；
#   - 台词引用：说话动词后的引用要抓，招牌/字幕类引用不误伤；
#   - 细节律三细节、三工作 function、最终画面 final_frame、五锚点；
#   - 最终提示词审计：短 prompt / 占位词 / 否定句 / 台词 / 一镜多运镜。
# =====================================================================

from __future__ import annotations

from app.crew.dramaturgy import (
    audit_breakdowns,
    audit_video_prompt,
    find_negations,
    find_slop_words,
    find_spoken_quotes,
    refresh_prompt_audits,
    strip_slop,
    strip_spoken_quotes,
    three_details,
)
from app.domain import SceneAnchors, SceneBreakdown, Shot


# ---------- 占位词 ----------


def test_find_slop_words_zh_and_en():
    assert "电影感" in find_slop_words("夜景，电影感，雨")
    assert "cinematic" in find_slop_words("cinematic shot of a man")
    assert "high quality" in find_slop_words("A high quality portrait")
    assert find_slop_words("冰箱冷光熄灭在他脸上") == []
    assert find_slop_words("overcast daylight, chipped paint") == []


def test_strip_slop_drops_only_pure_segments():
    # 整段都是占位词 → 删
    assert strip_slop("夜景，电影感，雨") == "夜景，雨"
    assert strip_slop("epic, stunning, rainy street") == "rainy street"
    # 混写句保留（机械删词会破坏语法，交给审计告警）
    assert strip_slop("画面呈现电影感十足的夜景") == "画面呈现电影感十足的夜景"
    # 没有占位词时原样返回
    assert strip_slop(" fridge light dying on his face ") == " fridge light dying on his face "


# ---------- 否定句（含招牌误伤边界） ----------


def test_find_negations_detects_and_skips_sign_text():
    assert find_negations("她的手没有穿过带子") == ["没有"]
    assert find_negations("Do not let the hand pass through") == ["not"]
    # 实体招牌里的「禁止」不是给模型的否定指令
    assert find_negations("警戒带上写着「禁止入内」三个字") == []


# ---------- 台词引用 ----------


def test_strip_spoken_quotes_removes_dialogue_but_keeps_signs():
    body = "小赵快步迎上，开口报告：「死者从七楼摔下。」苏砚点头。"
    assert "死者从七楼摔下" not in strip_spoken_quotes(body)
    assert "苏砚点头" in strip_spoken_quotes(body)
    sign = "警戒带上写着「禁止入内」三个字，雨丝不断。"
    assert strip_spoken_quotes(sign) == sign


# ---------- 细节律 ----------


def test_three_details_counts_categories():
    # 三类齐全：环境压力（lighting 字段）+ 身体微动作 + 声音锚点
    count, missing = three_details(
        lighting="钨丝灯在画面左上方",
        action="他下颌锁死，手指抠住门框",
        background_action="秒针的滴答声持续",
    )
    assert count == 3 and missing == []
    # 零细节 = 废镜头
    count, missing = three_details(action="他走过去", lighting="", background_action="")
    assert count == 0
    assert set(missing) == {"环境压力", "身体微动作", "声音锚点/视觉母题"}


# ---------- 导演侧：戏剧结构审计 ----------


def _shot(oid: str, **kw) -> Shot:
    defaults = dict(
        id=oid, scene_id="scene_001", order=0, duration_sec=8.0,
        function="pressure", final_frame="冰箱冷光熄灭在他脸上",
        action="他下颌锁死，手指停在门把上",
        lighting="唯一的冷光来自冰箱",
    )
    defaults.update(kw)
    return Shot(**defaults)


def test_audit_breakdowns_passes_complete_plan():
    bd = SceneBreakdown(
        scene_id="scene_001",
        anchors=SceneAnchors(emotion="饥饿即孤独", motif="玻璃上的反射", object="最后一段香肠",
                             break_point="他发现架子是空的", final_image="冷光熄灭在他脸上"),
        shots=[_shot("shot_scene_001_000")],
    )
    assert audit_breakdowns([bd]) == []


def test_audit_breakdowns_flags_wallpaper_and_empty_anchors():
    bd = SceneBreakdown(scene_id="scene_001", shots=[
        _shot("shot_scene_001_000", function="", final_frame="",
              action="他走过去", lighting=None),
    ])
    issues = " ".join(audit_breakdowns([bd]))
    assert "五锚点全部空缺" in issues
    assert "没有写 function" in issues
    assert "没有写 final_frame" in issues
    assert "零细节 = 废镜头" in issues


def test_audit_breakdowns_flags_thin_shot():
    bd = SceneBreakdown(scene_id="scene_001", shots=[
        # 只有环境压力一类细节
        _shot("shot_scene_001_000", action="他慢慢走过去"),
    ])
    issues = " ".join(audit_breakdowns([bd]))
    assert "一类细节" in issues


# ---------- 摄影指导侧：最终提示词审计 ----------


def test_audit_video_prompt_flags_all_killers():
    issues = audit_video_prompt({"video_prompt": "齐夏站在门口，开口说道：「你终于来了。」"})
    joined = " ".join(issues)
    assert "引用台词" in joined


def test_audit_video_prompt_flags_slop_negation_and_multi_move():
    prompt = "电影感十足的走廊，他推近又环绕地看，手没有碰到门。epic, masterpiece"
    issues = audit_video_prompt({"video_prompt": prompt})
    joined = " ".join(issues)
    assert "占位词" in joined
    assert "否定式描述" in joined
    assert "一镜多运镜" in joined


def test_audit_video_prompt_clean_prompt_passes():
    prompt = (
        "密闭的方形房间，钨丝灯从长桌正上方打下亮斑。人物：齐夏：黑色短发、深灰卫衣。"
        "镜头从后墙沿中轴缓慢推进，齐夏的下颌慢慢锁死，指节抵在桌沿，秒针的滴答声持续。"
        "冷光熄灭在他脸上。"
    )
    assert audit_video_prompt({"video_prompt": prompt}) == []


def test_refresh_prompt_audits_updates_shot_dicts_in_place():
    shots = [
        {"id": "a", "video_prompt": "他说：「进来。」"},
        {"id": "b", "video_prompt": ""},
    ]
    refresh_prompt_audits(shots)
    assert any("引用台词" in i for i in shots[0]["prompt_audit"])
    assert shots[1]["prompt_audit"] == []
