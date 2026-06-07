from __future__ import annotations

import json
from typing import Any

from ..adaptation_profiles import adaptation_profile_for


def script_to_json_text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _scene_heading(index: int, title: object) -> str:
    scene_title = str(title or "").strip()
    if scene_title.startswith("第") and "场" in scene_title[:8]:
        return f"### {scene_title}"
    if scene_title:
        return f"### 第 {index} 场：{scene_title}"
    return f"### 第 {index} 场"


def _script_adaptation(script: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    adaptation = script.get("adaptation") if isinstance(script.get("adaptation"), dict) else {}
    adaptation_type = str(adaptation.get("type") or "other")
    return adaptation_type, adaptation_profile_for(adaptation_type)


def _body_label(adaptation_type: str) -> str:
    return {
        "short_drama": "短剧节拍",
        "film": "剧本正文",
        "series": "分集场景流",
        "stage": "舞台正文",
    }.get(adaptation_type, "剧本流")


def _cue_label(adaptation_type: str) -> str:
    return {
        "film": "提示",
        "series": "提示",
        "stage": "舞台提示",
        "short_drama": "提示",
    }.get(adaptation_type, "提示")


def _format_dialogue_line(
    item: dict[str, Any], character_names: dict[Any, Any], *, stage_style: bool = False
) -> str:
    speaker = character_names.get(item.get("speaker"), item.get("speaker") or "Unknown")
    line = str(item.get("line") or "").strip()
    emotion = f" ({item['emotion']})" if item.get("emotion") else ""
    subtext = f"（潜台词：{item['subtext']}）" if item.get("subtext") else ""
    if stage_style:
        return f"{speaker}{emotion}：{line}{subtext}"
    return f"**{speaker}**{emotion}：{line}{subtext}"


def _append_beat_lines(
    lines: list[str],
    beats: list[Any],
    character_names: dict[Any, Any],
    adaptation_type: str,
) -> None:
    lines.append(f"**{_body_label(adaptation_type)}**")
    stage_style = adaptation_type == "stage"
    compact_style = adaptation_type in {"short_drama", "series"}
    for beat in beats:
        if not isinstance(beat, dict):
            continue
        beat_type = beat.get("type")
        if beat_type == "dialogue":
            line = str(beat.get("line") or "").strip()
            if not line:
                continue
            rendered = _format_dialogue_line(beat, character_names, stage_style=stage_style)
            lines.extend([f"- {rendered}" if compact_style else rendered, ""])
            continue

        text = str(beat.get("text") or "").strip()
        if not text:
            continue
        if beat_type == "cue":
            rendered = f"【{_cue_label(adaptation_type)}】{text}"
        elif stage_style:
            rendered = f"（动作）{text}"
        elif compact_style:
            rendered = f"【动作】{text}"
        else:
            rendered = text
        lines.extend([f"- {rendered}" if compact_style else rendered, ""])


def script_to_markdown(data: dict[str, Any]) -> str:
    script = data.get("script", {}) if isinstance(data.get("script"), dict) else {}
    title = str(script.get("title") or "未命名剧本")
    lines = [f"# {title}", ""]
    adaptation_type, profile = _script_adaptation(script)
    adaptation = script.get("adaptation") if isinstance(script.get("adaptation"), dict) else {}
    target_format = adaptation.get("target_format") or profile.get("target_format")
    if profile:
        lines.extend(
            [
                "## 改编规格",
                f"- 类型：{profile.get('label')}",
                f"- 格式：{target_format}",
                "",
            ]
        )

    logline = script.get("logline")
    if logline:
        lines.extend(["## 一句话梗概", str(logline), ""])

    themes = script.get("themes") or []
    if themes:
        lines.extend(["## 主题", *[f"- {theme}" for theme in themes if str(theme).strip()], ""])

    characters = script.get("characters") or []
    character_names = {
        item.get("id"): item.get("name")
        for item in characters
        if isinstance(item, dict) and item.get("id")
    }
    if characters:
        lines.append("## 角色")
        for character in characters:
            if not isinstance(character, dict):
                continue
            name = character.get("name") or character.get("id") or "未命名角色"
            role = f"（{character['role']}）" if character.get("role") else ""
            detail = character.get("goal") or character.get("motivation") or character.get("arc")
            suffix = f"：{detail}" if detail else ""
            lines.append(f"- **{name}**{role}{suffix}")
        lines.append("")

    locations = script.get("locations") or []
    location_names = {
        item.get("id"): item.get("name")
        for item in locations
        if isinstance(item, dict) and item.get("id")
    }
    if locations:
        lines.append("## 地点")
        for location in locations:
            if not isinstance(location, dict):
                continue
            name = location.get("name") or location.get("id") or "未命名地点"
            description = f"：{location['description']}" if location.get("description") else ""
            lines.append(f"- **{name}**{description}")
        lines.append("")

    scenes = script.get("scenes") or []
    if scenes:
        lines.append("## 场景")
        for index, scene in enumerate(scenes, start=1):
            if not isinstance(scene, dict):
                continue
            lines.extend([_scene_heading(index, scene.get("title")), ""])

            location_id = scene.get("location_id")
            location = location_names.get(location_id, location_id)
            time = scene.get("time")
            if location or time:
                meta = " / ".join(str(item) for item in (location, time) if item)
                lines.extend([f"**场景信息：** {meta}", ""])

            for label, key in (
                ("场景目的", "purpose"),
                ("核心冲突", "conflict"),
                ("入场状态", "entry_state"),
                ("离场状态", "exit_state"),
            ):
                if scene.get(key):
                    lines.append(f"**{label}：** {scene[key]}")
            if any(scene.get(key) for key in ("purpose", "conflict", "entry_state", "exit_state")):
                lines.append("")

            beats = scene.get("beats") or []
            if isinstance(beats, list) and beats:
                _append_beat_lines(lines, beats, character_names, adaptation_type)
            else:
                action = scene.get("action") or []
                action_lines = [str(item).strip() for item in action if str(item).strip()]
                if action_lines:
                    lines.append(f"**{_body_label(adaptation_type)}**")
                    for item in action_lines:
                        if adaptation_type == "stage":
                            lines.extend([f"（动作）{item}", ""])
                        elif adaptation_type in {"short_drama", "series"}:
                            lines.extend([f"- 【动作】{item}", ""])
                        else:
                            lines.extend([item, ""])

                dialogue = scene.get("dialogue") or []
                dialogue_lines: list[str] = []
                if isinstance(dialogue, list):
                    for item in dialogue:
                        if not isinstance(item, dict):
                            continue
                        line = str(item.get("line") or "").strip()
                        if not line:
                            continue
                        rendered = _format_dialogue_line(
                            item,
                            character_names,
                            stage_style=adaptation_type == "stage",
                        )
                        if adaptation_type in {"short_drama", "series"}:
                            rendered = f"- {rendered}"
                        dialogue_lines.append(rendered)
                if dialogue_lines:
                    lines.append("**对白**")
                    for item in dialogue_lines:
                        lines.extend([item, ""])

    return "\n".join(lines).rstrip() + "\n"
