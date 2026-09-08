# =====================================================================
# editor.py —— 剪辑师 Agent
#
# 职责：视频片段 → 成片
# 输入：生成的视频片段列表 + 镜头顺序
# 输出：拼接后的完整视频
#
# 剪辑师负责按镜头顺序拼接视频，处理转场，输出成片。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from ..domain import Script, Shot
from ..llm import LLM
from .base import CrewAgent, CrewTaskResult

log = logging.getLogger(__name__)


class EditorAgent(CrewAgent):
    """剪辑师 Agent：视频片段拼接成片。"""

    name = "editor"
    label = "剪辑师"
    emoji = "✂️"

    def run(
        self,
        script: Script,
        *,
        shots: list[Shot] | None = None,
        output_path: str = "",
        **kwargs: Any,
    ) -> CrewTaskResult:
        """将视频片段拼接成完整短剧。

        Args:
            script: 当前剧本。
            shots: 含 video_url 的镜头列表。
            output_path: 输出视频路径。

        Returns:
            CrewTaskResult.data = {"output_path": str, "duration": float}
        """
        if not shots:
            return CrewTaskResult(success=False, summary="没有镜头数据")

        # 过滤有视频的镜头
        shots_with_video = [s for s in shots if s.video_url]
        if not shots_with_video:
            return CrewTaskResult(success=False, summary="没有已生成的视频片段")

        if not output_path:
            import tempfile
            output_path = tempfile.mktemp(suffix=".mp4", prefix="drama_")

        try:
            from ..video.assemble import download_and_assemble

            video_urls = [s.video_url for s in shots_with_video]
            result = download_and_assemble(video_urls, output_path)

            if result.get("ok"):
                return CrewTaskResult(
                    data={
                        "output_path": result["output"],
                        "duration": result.get("duration", 0),
                        "clip_count": len(video_urls),
                    },
                    summary=f"剪辑完成：{len(video_urls)} 个片段拼接为 {result.get('duration', 0):.1f} 秒的成片",
                )
            else:
                return CrewTaskResult(
                    success=False,
                    summary=f"拼接失败：{result.get('error', '未知错误')}",
                    errors=[result.get("error", "")],
                )
        except Exception as e:  # noqa: BLE001
            log.warning("剪辑师 Agent 失败：%s", e)
            return CrewTaskResult(success=False, summary=f"剪辑失败：{e}", errors=[str(e)])


def run_editor(
    llm: LLM,
    script: Script,
    *,
    shots: list[Shot] | None = None,
    output_path: str = "",
) -> CrewTaskResult:
    """快捷入口：执行视频拼接。"""
    agent = EditorAgent(llm)
    return agent.run(script, shots=shots, output_path=output_path)
