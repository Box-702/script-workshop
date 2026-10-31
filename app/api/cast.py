# =====================================================================
# cast.py —— 资产库 API（角色形象 / 声音 / 图片 / 场景 的唯一入口）
#
# 三个端点：
#   GET   /projects/{id}/library          读：角色 + 场景 + 音色选项 + 告警
#   PATCH /projects/{id}/library          改：性别 / 音色 / 外貌 / 场景描述 / 图
#   POST  /projects/{id}/library/preview  试听：用某个音色读一句样音
#
# 为什么要有「试听」：音色是一串 voice_id（male-qn-badao），用户没法凭名字
# 判断「磁性男声」到底像不像这个角色。让人先听一句，再决定，比事后在成片里
# 发现「男主是御姐音」便宜得多。
# =====================================================================

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

from . import common, deps
from ..media.library import apply_library_patch, build_library, voice_options
from ..media.casting import VOICE_LABELS

router = APIRouter()
log = logging.getLogger(__name__)

# 试听样音：拿角色自己的一句台词最好，没有台词时用这句占位。
SAMPLE_TEXT = "这句话，是用我的声音说的。"


class CharacterChange(BaseModel):
    gender: str | None = None
    voice_id: str | None = None
    appearance: str | None = None
    image: str | None = None


class LocationChange(BaseModel):
    description: str | None = None
    image: str | None = None


class LibraryPatch(BaseModel):
    characters: dict[str, CharacterChange] = Field(default_factory=dict)
    locations: dict[str, LocationChange] = Field(default_factory=dict)


class VoicePreview(BaseModel):
    voice_id: str = Field(min_length=1)
    text: str = ""
    gender: str | None = None


def _script_of(store: Any, project: Any, version_id: str | None = None) -> Any:
    vid = version_id or project.current_version_id
    sv = store.get_version(vid) if vid else None
    script = getattr(sv, "script", None) if sv else None
    if script is None:
        raise HTTPException(404, "该项目还没有可用的剧本版本，无法建立资产库")
    return script


@router.get("/projects/{project_id}/library")
def get_library(project_id: str, version_id: str | None = None) -> dict[str, Any]:
    """资产库总览：每个角色的形象锚、定妆图、性别与音色（含判定依据）。"""
    store = deps.store()
    project = common.get_project(project_id)
    script = _script_of(store, project, version_id)
    style = store.get_video_style(project_id) or {}
    return build_library(script, style, visual_style=style.get("visual_style"))


@router.patch("/projects/{project_id}/library")
def patch_library(project_id: str, payload: LibraryPatch) -> dict[str, Any]:
    """人工修正资产：指定性别/音色/外貌/图。返回修正后的整张资产库。"""
    store = deps.store()
    project = common.get_project(project_id)
    script = _script_of(store, project, None)

    patch = {
        "characters": {
            name: ch.model_dump(exclude_none=True)
            for name, ch in payload.characters.items()
        },
        "locations": {
            name: loc.model_dump(exclude_none=True)
            for name, loc in payload.locations.items()
        },
    }
    style = store.get_video_style(project_id) or {}
    merged = apply_library_patch(style, patch)
    store.set_video_style(project_id, merged)

    # 记一条给人看的日志：改了什么、改到哪个角色的声音上。
    for name, ch in payload.characters.items():
        if ch.voice_id:
            log.info("资产库：%s 的音色指定为 %s（%s）", name,
                     ch.voice_id, VOICE_LABELS.get(ch.voice_id, ch.voice_id))
    return build_library(script, merged, visual_style=merged.get("visual_style"))


@router.get("/projects/{project_id}/library/voices")
def list_voices(project_id: str) -> list[dict[str, str]]:
    """可选音色清单（按项目类型排序：漫剧把年轻音色排前面）。"""
    project = common.get_project(project_id)
    style = deps.store().get_video_style(project.id) or {}
    return voice_options(style.get("visual_style"))


@router.post("/projects/{project_id}/library/preview")
def preview_voice(project_id: str, payload: VoicePreview) -> Response:
    """试听：用指定音色读一句样音，返回 mp3 字节流。"""
    common.get_project(project_id)
    from ..llm.registry import resolve_tts
    from ..llm.tts import build_tts_client
    from ..config import get_settings

    client = build_tts_client(resolve_tts(get_settings()))
    if client is None or not client.available:
        raise HTTPException(503, "未配置 TTS（需要 MINIMAX_API_KEY），无法试听")

    text = (payload.text or "").strip()[:80] or SAMPLE_TEXT
    try:
        audio = client.synthesize(text, voice_id=payload.voice_id, speed=1.0)
    except Exception as e:  # noqa: BLE001
        log.warning("试听失败：%s", e)
        raise HTTPException(502, f"试听失败：{e}") from e
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "no-store"})
