# =====================================================================
# test_director_guard.py —— 导演分镜的确定性硬约束
#
# 《孔乙己》首版真跑暴露的两类问题，都是「规则写在技能里、但模型不照做」：
#   1. 一镜塞 5 个连续动作 → 视频模型演不完，动作糊成一团、手部穿模；
#   2. 一镜挤进两三个人说话 → 观众不知道是谁在说。
# 这里把它们变成断言：不满足就打回重拆，而不是祈祷模型听话。
# =====================================================================

from __future__ import annotations

from app.crew.director import DirectorAgent, action_budget, count_action_units
from app.domain import (
    Character,
    Location,
    Scene,
    SceneBreakdown,
    Script,
    ScriptBeat,
    Shot,
    Source,
)


def _script(beats: list[ScriptBeat]) -> Script:
    scene = Scene(
        id="scene_001", title="测试场", chapter_refs=["ch_001"], location_id="loc_a",
        characters=["char_a", "char_b", "char_c"], purpose="p", conflict="c", beats=beats,
    )
    return Script(
        title="测试", source=Source(chapter_count=1, chapter_ids=["ch_001"]),
        logline="测", characters=[
            Character(id="char_a", name="甲"), Character(id="char_b", name="乙"),
            Character(id="char_c", name="丙"),
        ],
        locations=[Location(id="loc_a", name="屋")], scenes=[scene],
    )


def _check(shots: list[Shot], beats: list[ScriptBeat] | None = None) -> list[str]:
    agent = DirectorAgent.__new__(DirectorAgent)
    bd = SceneBreakdown(scene_id="scene_001", shots=shots)
    return agent._validate_continuity([bd], _script(beats or []))


def test_动作预算按时长算() -> None:
    assert action_budget(5.0) == 3      # 一个动作 + 两笔细节是常见写法
    assert action_budget(8.0) == 3
    assert action_budget(12.0) == 4
    assert count_action_units("甲推开门走进来；乙抬头看他；甲走到桌前站住") == 3


def test_一镜动作超载被打回() -> None:
    """《孔乙己》九镜全部超标（8–10 秒写 3–6 段动作），一个都没逃掉。"""
    shots = [Shot(
        id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8,
        action="甲推开门走进来；乙抬头看他；甲走到桌前站住；乙把碗放下",
    )]
    issues = _check(shots)
    assert any("段身体动作" in i for i in issues)


def test_动作密度合规时不再唠叨() -> None:
    shots = [Shot(
        id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8,
        action="甲推开门走进来，手指在门框上搭了一下；乙抬头看他",
    )]
    issues = _check(shots)
    assert not any("段身体动作" in i for i in issues)


def test_同段多人对话拆开后各自单说话人() -> None:
    """一段甲乙来回的对话按说话人拆成两镜：两个镜头都不该被判「多说话人」。"""
    beats = [
        ScriptBeat(id="beat_001", type="dialogue", speaker="char_a", line="你来了。"),
        ScriptBeat(id="beat_002", type="dialogue", speaker="char_b", line="我来了。"),
    ]
    shots = [
        Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8,
             action="甲坐在桌边，手指敲着碗沿；他抬眼看门口", dialogue_ref="beat_001"),
        Shot(id="shot_scene_001_001", scene_id="scene_001", order=1, duration_sec=8,
             action="乙站在门口，手扶着门框；他朝桌边点头", dialogue_ref="beat_002",
             cut_reason="换说话人"),
    ]
    issues = _check(shots, beats)
    assert not any("个说话人" in i for i in issues)
    assert not any("没有任何镜头认领" in i for i in issues)


def test_一镜一说话人合规() -> None:
    beats = [
        ScriptBeat(id="beat_001", type="dialogue", speaker="char_a", line="你来了。"),
        ScriptBeat(id="beat_002", type="dialogue", speaker="char_a", line="坐罢。"),
    ]
    shots = [Shot(
        id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8,
        action="甲坐在桌边，手指敲着碗沿；他抬眼看门口", dialogue_ref="beat_001",
    )]
    issues = _check(shots, beats)
    assert not any("个说话人" in i for i in issues)
    assert not any("没有任何镜头认领" in i for i in issues)
    assert not any("念得完" in i for i in issues)


def test_对话没有镜头认领被打回() -> None:
    """没有 dialogue_ref 认领的对话，配音时无处安放，会落到画面无关的镜头上。"""
    beats = [
        ScriptBeat(id="beat_001", type="action", text="甲推门进来。"),
        ScriptBeat(id="beat_002", type="dialogue", speaker="char_a", line="温两碗酒。"),
    ]
    shots = [Shot(
        id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8,
        action="甲推门进来，手在门框上搭了一下；他抬头看柜台",
    )]
    issues = _check(shots, beats)
    assert any("没有任何镜头认领" in i for i in issues)


def test_台词念不完被打回() -> None:
    """10 秒镜头塞 60 字台词：每秒 4 字念不完，配音只能赶语速。"""
    long_line = "温两碗酒要一碟茴香豆这一段话一共六十字用来测试朗读时长是否够用真的挺长的啊"
    beats = [ScriptBeat(id="beat_001", type="dialogue", speaker="char_a", line=long_line)]
    shots = [Shot(
        id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=8,
        action="甲站在柜台前，手撑着台面；他抬眼看掌柜", dialogue_ref="beat_001",
    )]
    issues = _check(shots, beats)
    assert any("念得完" in i for i in issues)


def test_台词归属按说话人切断() -> None:
    """同一人连说的几句归同一镜，换人就断开——否则台词会从一个人嘴里念完。"""
    beats = [
        ScriptBeat(id="beat_001", type="dialogue", speaker="char_a", line="第一句。"),
        ScriptBeat(id="beat_002", type="dialogue", speaker="char_a", line="第二句。"),
        ScriptBeat(id="beat_003", type="dialogue", speaker="char_b", line="第三句。"),
    ]
    shots = [
        Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, dialogue_ref="beat_001"),
        Shot(id="shot_scene_001_001", scene_id="scene_001", order=1, dialogue_ref="beat_003"),
    ]
    from app.domain import assign_dialogue_ranges

    ranges = assign_dialogue_ranges(shots, beats)
    assert [b.id for b in ranges["shot_scene_001_000"]] == ["beat_001", "beat_002"]
    assert [b.id for b in ranges["shot_scene_001_001"]] == ["beat_003"]


def test_一镜一人多笔细节不误伤() -> None:
    """同一个人一个动作写三笔细节（搁碗→抬下巴→指点）是正常写法，不该打回。"""
    shots = [Shot(
        id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=5,
        action="甲把空碗往柜台上一搁，碗底磕出脆响；他下巴一抬，嘴角咧开；手指点向对面",
    )]
    issues = _check(shots)
    assert not any("段身体动作" in i for i in issues)
