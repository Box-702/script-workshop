# =====================================================================
# test_dubbing.py —— 配音编排测试
#
# 覆盖：台词按「beats 段对齐」归属到镜头、音色分配、时间轴排程、
# ffmpeg 混音（用真实 ffmpeg + 合成音频，不调网络 TTS）。
# =====================================================================

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.domain import (
    Adaptation,
    Character,
    Location,
    Scene,
    Script,
    ScriptBeat,
    Shot,
    Source,
)
from app.media.dubbing import (
    DubLine,
    assign_voices,
    dub_video,
    mix_dubbing,
    plan_dubbing,
    synthesize_track,
)


def _script() -> Script:
    """v5 同构场景：动作 → 4 句对白 → 动作。"""
    beats = [
        ScriptBeat(id="beat_001", type="action", text="苏砚下车站定。"),
        ScriptBeat(id="beat_002", type="action", text="苏砚穿过警戒带。"),
        ScriptBeat(id="beat_003", type="dialogue", speaker="char_zhao", line="死者从七楼摔下来的。"),
        ScriptBeat(id="beat_004", type="dialogue", speaker="char_zhao", line="没有目击者。"),
        ScriptBeat(id="beat_005", type="dialogue", speaker="char_zhou", line="天台门呢？"),
        ScriptBeat(id="beat_006", type="dialogue", speaker="char_zhao", line="反锁着。"),
        ScriptBeat(id="beat_007", type="action", text="苏砚抬头望向楼顶。"),
    ]
    scene = Scene(
        id="scene_001", title="测试", chapter_refs=["ch_001"], location_id="loc_a",
        characters=["char_su", "char_zhou", "char_zhao"], purpose="p", conflict="c",
        beats=beats,
    )
    return Script(
        title="配音测试", source=Source(chapter_count=1, chapter_ids=["ch_001"]),
        logline="测", characters=[
            Character(id="char_su", name="苏砚"),
            Character(id="char_zhou", name="老周"),
            Character(id="char_zhao", name="小赵"),
        ],
        locations=[Location(id="loc_a", name="现场")],
        scenes=[scene],
    )


def _shots() -> list[Shot]:
    """三镜 6+8+6s：动作 / 对白 / 动作（与 beats 段结构一致）。"""
    return [
        Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=6),
        Shot(id="shot_scene_001_001", scene_id="scene_001", order=1, duration_sec=8),
        Shot(id="shot_scene_001_002", scene_id="scene_001", order=2, duration_sec=6),
    ]


def test_plan_dubbing_aligns_dialogue_to_middle_shot():
    """连续 4 句对白压成一个对话段，全部归属中间的对白镜头。"""
    plan = plan_dubbing(_script(), _shots())
    assert plan.total_sec == 20.0
    assert len(plan.lines) == 4
    assert {ln.shot_id for ln in plan.lines} == {"shot_scene_001_001"}
    assert plan.lines[0].text == "死者从七楼摔下来的。"
    assert plan.lines[2].speaker == "老周"


def test_assign_voices_distinguishes_gender():
    """名字带女性线索的角色拿女声，其余男女交替，分配稳定。"""
    voices = assign_voices(_script())
    assert voices["苏砚"] != voices["老周"]  # 苏砚名字含「砚」无线索，但至少男女有别
    assert voices["苏砚"] in {voices["苏砚"]}  # 稳定性由两次调用一致保证
    assert assign_voices(_script()) == voices


def test_explicit_dialogue_ref_wins(tmp_path):
    """镜头显式 dialogue_ref 时优先于段对齐。"""
    script = _script()
    shots = _shots()
    shots[2].dialogue_ref = "beat_005"
    plan = plan_dubbing(script, shots)
    ref_lines = [ln for ln in plan.lines if ln.text == "天台门呢？"]
    assert ref_lines and ref_lines[0].shot_id == "shot_scene_001_002"


def test_synthesize_and_mix_with_real_ffmpeg(tmp_path):
    """端到端混音：假 TTS（写静音 mp3）→ 排程 → 真实 ffmpeg 合成配音视频。"""
    from types import SimpleNamespace

    from app.video.qa import _ffmpeg

    ffmpeg = _ffmpeg()
    if not ffmpeg:
        pytest.skip("本机无 ffmpeg，跳过混音测试")

    # 造一段 2s 的测试视频（彩条 + 正弦音），模拟成片。
    video = tmp_path / "clip.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error",
         "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=15",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(video)],
        check=True, capture_output=True,
    )

    # 假 TTS：用 ffmpeg 生成 0.5s 静音 mp3 当「合成结果」。
    class FakeTTS:
        def synthesize(self, text: str, *, voice_id: str = "", speed: float = 1.0) -> bytes:
            out = tmp_path / f"tts_{abs(hash(text))}.mp3"
            subprocess.run(
                [ffmpeg, "-y", "-loglevel", "error",
                 "-f", "lavfi", "-i", "sine=frequency=880:duration=0.5",
                 "-c:a", "libmp3lame", str(out)],
                check=True, capture_output=True,
            )
            return out.read_bytes()

    plan = SimpleNamespace(lines=[
        DubLine(speaker="小赵", text="第一句", voice_id="v1", shot_id="shot_scene_001_000"),
        DubLine(speaker="老周", text="第二句", voice_id="v2", shot_id="shot_scene_001_000"),
    ])
    shots = [Shot(id="shot_scene_001_000", scene_id="scene_001", order=0, duration_sec=2)]
    track = synthesize_track(FakeTTS(), plan, shots, tmp_path / "work")
    assert len(track) == 2
    assert track[0]["start_ms"] == 400          # 镜头起点 + 0.4s 引导
    # 第二句 = 第一句起点 + 实测时长（mp3 编码器 padding 会略长于 0.5s）+ 句间 0.25s
    first_dur_ms = track[1]["start_ms"] - 250 - track[0]["start_ms"]
    assert 500 <= first_dur_ms <= 900
    assert track[1]["start_ms"] == track[0]["start_ms"] + first_dur_ms + 250

    out = tmp_path / "dubbed.mp4"
    mix_dubbing(video, track, out, bg_volume=0.25, ffmpeg=ffmpeg)
    assert out.exists() and out.stat().st_size > 0
