# =====================================================================
# tts.py —— 语音合成客户端（TTS）
#
# 用途：给成片配音——视频模型没有「文字→语音」通路（只会产出含混的
# 假说话），台词的语音必须由 TTS 单独合成，再按时间轴混到成片上
# （见 app/media/dubbing.py）。
#
# 与 image.py / vision.py 同构：一个客户端抽象 + 厂商实现 + 工厂函数，
# 上层只依赖 TTSClient 接口。
#
# MiniMax T2A v2 实测约定：
#   POST {base}/v1/t2a_v2
#   body: {model, text, voice_setting:{voice_id, speed}, audio_setting:{format:"mp3"}}
#   响应: {"data": {"audio": "<hex 编码的 mp3 字节>"}}；错误走 base_resp。
# =====================================================================

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .base import ModelConfig

log = logging.getLogger(__name__)


class TTSClient(ABC):
    """语音合成客户端抽象。"""

    def __init__(self, config: ModelConfig) -> None:
        self.config = config

    @property
    def available(self) -> bool:
        return bool(self.config.api_key and self.config.model)

    @property
    def label(self) -> str:
        return self.config.label or self.config.provider

    @abstractmethod
    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "male-qn-qingse",
        speed: float = 1.0,
        timeout: float = 120.0,
    ) -> bytes:
        """合成一段语音，返回音频字节（mp3）。失败抛异常。"""
        ...


class MiniMaxTTSClient(TTSClient):
    """MiniMax T2A v2 语音合成。"""

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str = "male-qn-qingse",
        speed: float = 1.0,
        timeout: float = 120.0,
    ) -> bytes:
        body: dict[str, Any] = {
            "model": self.config.model,
            "text": text,
            "stream": False,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": max(0.5, min(2.0, speed)),
                "vol": 1.0,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": 32000,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }
        with httpx.Client(trust_env=False, timeout=timeout) as client:
            resp = client.post(
                self.config.endpoint("v1/t2a_v2"),
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        # 错误形态：{"base_resp": {"status": 1xxx, "status_msg": "..."}}
        base_resp = data.get("base_resp") or {}
        if base_resp.get("status") not in (0, None):
            raise RuntimeError(f"MiniMax TTS 失败：{base_resp.get('status_msg')}")
        audio_hex = (data.get("data") or {}).get("audio") or ""
        if not audio_hex:
            raise RuntimeError(f"MiniMax TTS 响应中没有音频：{str(data)[:200]}")
        return bytes.fromhex(audio_hex)


def build_tts_client(config: ModelConfig | None) -> TTSClient | None:
    """按 provider 标识构建 TTS 客户端；未知厂商返回 None。"""
    if config is None or not config.api_key:
        return None
    if config.provider == "minimax":
        return MiniMaxTTSClient(config)
    log.warning("未知的 TTS provider：%s", config.provider)
    return None


# 常用中文音色（MiniMax 系统音色）。
VOICE_FEMALE_YOUNG = "female-shaonv"    # 少女
VOICE_FEMALE_MATURE = "female-yujie"    # 御姐
VOICE_MALE_YOUNG = "male-qn-qingse"     # 青涩青年
VOICE_MALE_MATURE = "male-qn-badao"     # 磁性男声
