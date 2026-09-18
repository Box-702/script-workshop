# =====================================================================
# dubbing.py —— 成片配音（台词 TTS + 时间轴混音）
#
# 解决什么：视频模型没有「文字→语音」通路（只会产出含混假说话），所以
# 台词不进视频提示词（DP 规则9），成片是「哑剧」；本模块把哑剧变成有声片：
#
#   剧本对白 → 按镜头归属（beats 段对齐）→ 逐句 TTS 合成（按角色音色）
#   → ffprobe 实测每句时长排时间轴 → ffmpeg 混音（环境音压低 + 台词叠加）
#
# 台词归属算法（按镜头对齐到秒级）：
#   把场景 beats 压缩成交替的「动作段 / 对话段」序列——导演正是按这个粒度
#   切镜的——再把段序列按比例均分给镜头。对话段里的对白就落在对应镜头的
#   时间区间内。显式 dialogue_ref 优先于段对齐。
#
# 局限（如实说明）：这是「台词在正确时刻出现」的配音，不是视觉级口型同步
# （lip-sync 需要专门的视觉模型，如 Wav2Lip / Latentsync 类）。人物在说话
# 镜头里有口型动作（视频模型按「报告姿态」生成的），配合后期配音观感自然。
# =====================================================================

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain import Script, Shot
from ..llm.tts import (
    TTSClient,
    VOICE_FEMALE_MATURE,
    VOICE_FEMALE_YOUNG,
    VOICE_MALE_MATURE,
    VOICE_MALE_YOUNG,
)

log = logging.getLogger(__name__)

# 台词排程参数。
LINE_LEAD_SEC = 0.4     # 镜头开始后多久说第一句
LINE_GAP_SEC = 0.25     # 句间停顿


# ---------- 音色分配 ----------

_FEMALE_HINTS = ("女", "姐", "妹", "母", "姨", "婆", "嫂", "她")


def assign_voices(script: Script) -> dict[str, str]:
    """给出场角色分配音色：名字/性别线索推断女声，其余按男女隔一交替。

    简单启发式够用——音色只要「全片一致 + 男女区分」即可，不需要精准人设。
    """
    voices: dict[str, str] = {}
    for c in script.characters:
        text = f"{c.name}{c.personality or ''}{c.role or ''}"
        if any(h in text for h in _FEMALE_HINTS):
            voices[c.name] = VOICE_FEMALE_MATURE
    # 没推断出女声的角色，按出场顺序男女交替兜底（保持分配稳定）。
    alternation = [VOICE_FEMALE_MATURE, VOICE_MALE_MATURE]
    i = 0
    for c in script.characters:
        if c.name not in voices:
            voices[c.name] = alternation[i % 2]
            i += 1
    return voices


# ---------- 台词归属 ----------


@dataclass
class DubLine:
    """一句待合成的台词。"""

    speaker: str
    text: str
    voice_id: str
    shot_id: str
    start_sec: float = 0.0  # 合成后排程填入（成片内绝对时刻）


@dataclass
class DubbingPlan:
    """整部片的配音计划：台词列表 + 总时长。"""

    lines: list[DubLine] = field(default_factory=list)
    total_sec: float = 0.0


def _scene_beat_map(script: Script) -> dict[str, list]:
    return {sc.id: sc.beats for sc in script.scenes}


def _segment_beats(beats: list) -> list[list]:
    """把 beats 压缩成连续同类型段：[动作段, 对话段, ...]。cue 段忽略。"""
    segments: list[list] = []
    for b in beats or []:
        if b.type == "cue":
            continue
        if segments and segments[-1][0].type == b.type:
            segments[-1].append(b)
        else:
            segments.append([b])
    return segments


def plan_dubbing(script: Script, shots: list[Shot], voices: dict[str, str] | None = None) -> DubbingPlan:
    """把剧本对白归属到镜头，产出配音计划。

    - 显式 dialogue_ref 优先：镜头指向哪个 beat，台词就归哪一镜；
    - 否则按「段对齐」：场景 beats 压缩成交替段序列后按比例均分给镜头。
    """
    voices = voices or assign_voices(script)
    char_map = {c.id: c.name for c in script.characters}
    beat_map = _scene_beat_map(script)
    scene_of = {sc.id: sc for sc in script.scenes}

    ordered = sorted(shots, key=lambda s: s.order)
    plan = DubbingPlan(total_sec=sum(max(1.0, s.duration_sec) for s in ordered))

    # 每个场景单独对齐（导演按场景拆镜，order 已全局编号但场景内连续）。
    by_scene: dict[str, list[Shot]] = {}
    for s in ordered:
        by_scene.setdefault(s.scene_id, []).append(s)

    for scene_id, scene_shots in by_scene.items():
        beats = beat_map.get(scene_id) or []
        dialogue_beats = [b for b in beats if b.type == "dialogue" and (b.line or "").strip()]
        if not dialogue_beats or not scene_shots:
            continue

        # 1) 显式 dialogue_ref
        ref_to_shot: dict[str, Shot] = {}
        for s in scene_shots:
            if s.dialogue_ref:
                ref_to_shot[s.dialogue_ref] = s
        if ref_to_shot:
            fallback_shot = next(iter(ref_to_shot.values()))
            for b in dialogue_beats:
                shot = ref_to_shot.get(b.id, fallback_shot)  # 未引用的对白落到最近的引用镜
                speaker = char_map.get(b.speaker or "", b.speaker or "")
                plan.lines.append(DubLine(
                    speaker=speaker, text=(b.line or "").strip(),
                    voice_id=voices.get(speaker, VOICE_MALE_MATURE), shot_id=shot.id,
                ))
            continue

        # 2) 段对齐：镜头 k 对应第 k 个段（导演正是按「动作段/对话段」切镜的）；
        #    段数与镜头数不等时按比例映射。对话段里的全部对白归该镜。
        segments = _segment_beats(beats)
        n = len(scene_shots)
        for si, seg in enumerate(segments):
            if seg[0].type != "dialogue":
                continue
            shot = scene_shots[min(n - 1, si * n // len(segments))]
            for b in seg:
                if not (b.line or "").strip():
                    continue
                speaker = char_map.get(b.speaker or "", b.speaker or "")
                plan.lines.append(DubLine(
                    speaker=speaker, text=(b.line or "").strip(),
                    voice_id=voices.get(speaker, VOICE_MALE_MATURE), shot_id=shot.id,
                ))
    return plan


# ---------- 合成 + 排程 ----------


def _audio_duration_sec(path: Path, ffprobe: str | None) -> float:
    """实测音频时长：优先 ffprobe；便携版常缺 ffprobe，回退用 ffmpeg -i 解析。"""
    if ffprobe:
        r = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        try:
            return max(0.5, float(r.stdout.strip()))
        except ValueError:
            pass
    ffmpeg = _ffmpeg_exe()
    if ffmpeg:
        r = subprocess.run(
            [ffmpeg, "-i", str(path)], capture_output=True, text=True, timeout=30,
        )
        import re

        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", r.stderr or "")
        if m:
            h, mi, s = (float(x) for x in m.groups())
            return max(0.5, h * 3600 + mi * 60 + s)
    return 2.0  # 全部探不到时的保守估计


def _find_ffprobe() -> str | None:
    from ..video.qa import _ffprobe

    return _ffprobe()


def _ffmpeg_exe() -> str | None:
    """ffmpeg 查找：FFMPEG_PATH 配置优先，其次 PATH。"""
    from ..video.qa import _ffmpeg

    return _ffmpeg()


def synthesize_track(
    tts: TTSClient,
    plan: DubbingPlan,
    shots: list[Shot],
    work_dir: Path,
    *,
    on_progress: Any = None,
) -> list[dict[str, Any]]:
    """逐句合成台词，按镜头起点 + 实测句长排时间轴。

    预算感知：台词常常挤不进所属镜头（导演按戏剧节奏切镜，不知道 TTS 实长）。
    首轮按常速合成，若最后一句的结束时刻超出片尾预算，则整批以 1.2 倍速
    重合成一次再排——宁可语速稍快，不让台词被片尾截掉。

    返回 [{"path": mp3路径, "start_ms": int}, ...]（按时间排序）。
    """
    def _emit(msg: str) -> None:
        log.info(msg)
        if on_progress:
            on_progress(msg)

    def _attempt(speed: float) -> list[dict[str, Any]]:
        shot_start: dict[str, float] = {}
        t = 0.0
        for s in sorted(shots, key=lambda x: x.order):
            shot_start[s.id] = t
            t += max(1.0, s.duration_sec)
        total = t

        ffprobe = _find_ffprobe()
        work_dir.mkdir(parents=True, exist_ok=True)
        track: list[dict[str, Any]] = []
        next_free: dict[str, float] = {}
        for i, line in enumerate(plan.lines):
            mp3 = work_dir / f"line_{i:03d}.mp3"
            try:
                mp3.write_bytes(tts.synthesize(line.text, voice_id=line.voice_id, speed=speed))
            except Exception as e:  # noqa: BLE001
                _emit(f"[配音] 「{line.text[:12]}…」合成失败，跳过：{e}")
                continue
            dur = _audio_duration_sec(mp3, ffprobe)
            base = shot_start.get(line.shot_id, 0.0)
            start = max(base + LINE_LEAD_SEC, next_free.get(line.shot_id, 0.0) or base + LINE_LEAD_SEC)
            next_free[line.shot_id] = start + dur + LINE_GAP_SEC
            track.append({"path": str(mp3), "start_ms": int(start * 1000), "text": line.text})
            _emit(f"[配音] {line.speaker}（{start:.1f}s 起，{dur:.1f}s）：{line.text}")
        track.sort(key=lambda x: x["start_ms"])
        return track, total

    track, total = _attempt(1.0)
    if track and len(track) > 1:
        # 超预算 → 按实测「内容跨度比」自适应提速（上限 1.6，再快就失真了）。
        # 根源在对白密度：上游分镜应给对白镜头排足时长（导演规则有此约束），
        # 配音层提速只是兜底。跨度比 + 5% 安全余量，抵消 TTS speed 参数的抖动。
        first_start = track[0]["start_ms"] / 1000
        span = track[-1]["start_ms"] / 1000 + _audio_duration_sec(Path(track[-1]["path"]), _find_ffprobe()) - first_start
        span_budget = total - 0.2 - first_start
        if span > span_budget and span_budget > 1:
            speed = min(1.6, round(1.05 * span / span_budget, 2))
            _emit(f"[配音] 台词超出片长预算（{first_start + span:.1f}s > {total:.0f}s），按 {speed} 倍速重合成")
            track, _ = _attempt(speed)
    return track


# ---------- 混音 ----------


def mix_dubbing(
    video_path: Path,
    track: list[dict[str, Any]],
    out_path: Path,
    *,
    bg_volume: float = 0.25,
    ffmpeg: str | None = None,
) -> Path:
    """把台词轨混进成片：环境音压低、台词按 start_ms 延迟叠加。

    视频流直拷（-c:v copy），只重编码音频。amix normalize=0 需要 ffmpeg 4.4+，
    不支持时回退为各路预放大补偿。
    """
    ffmpeg = ffmpeg or _ffmpeg_exe()
    if not ffmpeg:
        raise RuntimeError("找不到 ffmpeg，无法混音（可配置 FFMPEG_PATH）")

    inputs = ["-i", str(video_path)]
    for item in track:
        inputs += ["-i", item["path"]]

    def build_filter(normalize: bool) -> str:
        parts: list[str] = []
        mix_labels: list[str] = []
        if track:
            parts.append(f"[0:a]volume={bg_volume}[bg]")
            mix_labels.append("[bg]")
        for i, item in enumerate(track, start=1):
            delay = int(item["start_ms"])
            gain = ""
            if not normalize and track:
                # 老版 amix 会把音量除以路数，给台词路预放大补偿。
                gain = f"volume={len(track) + 1},"
            parts.append(f"[{i}:a]{gain}adelay={delay}|{delay}[d{i}]")
            mix_labels.append(f"[d{i}]")
        if not track:
            return None
        norm = ":normalize=0" if normalize else ""
        parts.append(f"{''.join(mix_labels)}amix=inputs={len(mix_labels)}:duration=first{norm}[out]")
        return ";".join(parts)

    for normalize in (True, False):
        flt = build_filter(normalize)
        if flt is None:
            # 没有成功合成的台词：原样拷贝
            cmd = [ffmpeg, "-y", "-loglevel", "error", "-i", str(video_path), "-c", "copy", str(out_path)]
            break
        cmd = (
            [ffmpeg, "-y", "-loglevel", "error", *inputs,
             "-filter_complex", flt, "-map", "0:v", "-map", "[out]",
             "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path)]
        )
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            break
        log.debug("混音（normalize=%s）失败，尝试回退：%s", normalize, r.stderr[-300:])
    else:
        raise RuntimeError(f"混音失败：{r.stderr[-300:]}")
    return out_path


def dub_video(
    video_path: Path,
    script: Script,
    shots: list[Shot],
    tts: TTSClient,
    out_path: Path,
    *,
    work_dir: Path | None = None,
    bg_volume: float = 0.25,
    on_progress: Any = None,
) -> Path | None:
    """一站式配音：计划 → 合成 → 混音。没有台词或 TTS 不可用时返回 None。"""
    plan = plan_dubbing(script, shots)
    if not plan.lines:
        log.info("本片没有对白，跳过配音")
        return None

    def _emit(msg: str) -> None:
        log.info(msg)
        if on_progress:
            on_progress(msg)

    _emit(f"[配音] 共 {len(plan.lines)} 句台词，总时长 {plan.total_sec:.0f}s")
    tmp = Path(tempfile.mkdtemp(prefix="dub_")) if work_dir is None else work_dir
    try:
        track = synthesize_track(tts, plan, shots, tmp, on_progress=on_progress)
        if not track:
            return None
        return mix_dubbing(video_path, track, out_path, bg_volume=bg_volume)
    finally:
        if work_dir is None:
            shutil.rmtree(tmp, ignore_errors=True)
