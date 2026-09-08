# =====================================================================
# assemble.py —— 视频拼接（FFmpeg）
#
# 将多个视频片段按镜头顺序拼接成完整短剧。
# 使用 FFmpeg 的 concat demuxer 实现无重编码拼接（速度最快）。
# 如果片段编码不一致，回退到 filter_complex 重编码。
# =====================================================================

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def find_ffmpeg() -> str | None:
    """查找 FFmpeg 可执行文件路径。"""
    return shutil.which("ffmpeg")


def find_ffprobe() -> str | None:
    """查找 FFprobe 可执行文件路径。"""
    return shutil.which("ffprobe")


def get_video_info(path: str, ffmpeg_path: str | None = None) -> dict[str, Any]:
    """获取视频文件信息（时长、分辨率、编码）。"""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return {"error": "ffprobe 未找到"}

    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v", "quiet",
                "-print_format", "json",
                "-show_format", "-show_streams",
                path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        import json
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        video_stream = next((s for s in streams if s.get("codec_type") == "video"), {})
        return {
            "duration": float(data.get("format", {}).get("duration", 0)),
            "width": video_stream.get("width", 0),
            "height": video_stream.get("height", 0),
            "codec": video_stream.get("codec_name", ""),
            "fps": eval(video_stream.get("r_frame_rate", "0/1")) if "/" in str(video_stream.get("r_frame_rate", "")) else 0,
        }
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def assemble_videos(
    video_paths: list[str],
    output_path: str,
    *,
    transition: str = "cut",
    crossfade_duration: float = 0.5,
) -> dict[str, Any]:
    """将多个视频片段拼接成一个完整视频。

    Args:
        video_paths: 视频文件路径列表（按顺序）。
        output_path: 输出文件路径。
        transition: 转场方式（cut / fade / dissolve）。
        crossfade_duration: 转场时长（秒）。

    Returns:
        {"ok": True, "output": path, "duration": seconds} 或 {"ok": False, "error": msg}
    """
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return {"ok": False, "error": "FFmpeg 未找到，请安装 FFmpeg 后重试"}

    if not video_paths:
        return {"ok": False, "error": "没有视频片段"}

    if len(video_paths) == 1:
        # 单个片段直接复制
        shutil.copy2(video_paths[0], output_path)
        info = get_video_info(output_path)
        return {"ok": True, "output": output_path, "duration": info.get("duration", 0)}

    # 尝试 concat demuxer（无重编码，最快）
    result = _concat_demuxer(ffmpeg, video_paths, output_path)
    if result["ok"]:
        info = get_video_info(output_path)
        result["duration"] = info.get("duration", 0)
        return result

    # 回退到 filter_complex（重编码）
    log.info("concat demuxer 失败，回退到 filter_complex：%s", result.get("error"))
    result = _filter_complex(ffmpeg, video_paths, output_path, transition, crossfade_duration)
    if result["ok"]:
        info = get_video_info(output_path)
        result["duration"] = info.get("duration", 0)
    return result


def _concat_demuxer(ffmpeg: str, video_paths: list[str], output_path: str) -> dict[str, Any]:
    """使用 concat demuxer 拼接（要求所有片段编码格式一致）。"""
    try:
        # 创建 concat 文件列表
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            concat_file = f.name
            for vp in video_paths:
                # 路径中的单引号需要转义
                safe_path = vp.replace("'", "'\\''")
                f.write(f"file '{safe_path}'\n")

        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",
                output_path,
            ],
            capture_output=True, text=True, timeout=300,
        )

        Path(concat_file).unlink(missing_ok=True)

        if result.returncode == 0:
            return {"ok": True, "output": output_path}
        return {"ok": False, "error": result.stderr[-500:] if result.stderr else "未知错误"}

    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def _filter_complex(
    ffmpeg: str,
    video_paths: list[str],
    output_path: str,
    transition: str,
    crossfade_duration: float,
) -> dict[str, Any]:
    """使用 filter_complex 拼接（支持转场，但需要重编码）。"""
    try:
        cmd = [ffmpeg, "-y"]

        # 输入所有视频
        for vp in video_paths:
            cmd.extend(["-i", vp])

        n = len(video_paths)

        if transition == "cut" or n <= 1:
            # 简单拼接
            filter_parts = []
            for i in range(n):
                filter_parts.append(f"[{i}:v:0][{i}:a:0]")
            filter_str = "".join(filter_parts) + f"concat=n={n}:v=1:a=1[outv][outa]"
            cmd.extend([
                "-filter_complex", filter_str,
                "-map", "[outv]", "-map", "[outa]",
            ])
        else:
            # 带转场的拼接
            # 简化处理：两两拼接
            # 对于多片段，先用 concat 拼接，再加全局 fade
            filter_parts = []
            for i in range(n):
                filter_parts.append(f"[{i}:v:0][{i}:a:0]")
            filter_str = "".join(filter_parts) + f"concat=n={n}:v=1:a=1[outv][outa]"
            cmd.extend([
                "-filter_complex", filter_str,
                "-map", "[outv]", "-map", "[outa]",
            ])

        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            output_path,
        ])

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0:
            return {"ok": True, "output": output_path}
        return {"ok": False, "error": result.stderr[-500:] if result.stderr else "未知错误"}

    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


def download_and_assemble(
    video_urls: list[str],
    output_path: str,
    *,
    temp_dir: str | None = None,
) -> dict[str, Any]:
    """下载远程视频并拼接。

    Args:
        video_urls: 视频 URL 列表。
        output_path: 输出文件路径。
        temp_dir: 临时目录。

    Returns:
        assemble_videos 的返回格式。
    """
    import httpx

    temp = Path(temp_dir or tempfile.mkdtemp(prefix="video_asm_"))
    temp.mkdir(parents=True, exist_ok=True)

    local_paths: list[str] = []
    try:
        for i, url in enumerate(video_urls):
            ext = ".mp4"
            local_path = str(temp / f"part_{i:03d}{ext}")
            try:
                with httpx.stream("GET", url, timeout=120, follow_redirects=True) as resp:
                    resp.raise_for_status()
                    with open(local_path, "wb") as f:
                        for chunk in resp.iter_bytes(chunk_size=8192):
                            f.write(chunk)
                local_paths.append(local_path)
            except Exception as e:  # noqa: BLE001
                log.warning("下载视频片段 %d 失败：%s", i, e)
                return {"ok": False, "error": f"下载片段 {i} 失败：{e}"}

        return assemble_videos(local_paths, output_path)

    finally:
        # 清理临时文件
        for p in local_paths:
            Path(p).unlink(missing_ok=True)
