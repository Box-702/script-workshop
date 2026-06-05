from __future__ import annotations

import json
from typing import Any


def script_to_json_text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _scene_heading(index: int, title: object) -> str:
    scene_title = str(title or "").strip()
    if scene_title.startswith("第") and "场" in scene_title[:8]:
        return f"### {scene_title}"
    if scene_title:
        return f"### 第 {index} 场：{scene_title}"
    return f"### 第 {index} 场"


def script_to_markdown(data: dict[str, Any]) -> str:
    script = data.get("script", {}) if isinstance(data.get("script"), dict) else {}
    title = str(script.get("title") or "未命名剧本")
    lines = [f"# {title}", ""]

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

            action = scene.get("action") or []
            action_lines = [str(item).strip() for item in action if str(item).strip()]
            if action_lines:
                lines.append("**动作**")
                for item in action_lines:
                    lines.extend([item, ""])

            dialogue = scene.get("dialogue") or []
            dialogue_lines: list[str] = []
            if isinstance(dialogue, list):
                for item in dialogue:
                    if not isinstance(item, dict):
                        continue
                    speaker = character_names.get(
                        item.get("speaker"), item.get("speaker") or "Unknown"
                    )
                    line = str(item.get("line") or "").strip()
                    if not line:
                        continue
                    emotion = f" ({item['emotion']})" if item.get("emotion") else ""
                    subtext = f"（潜台词：{item['subtext']}）" if item.get("subtext") else ""
                    dialogue_lines.append(f"**{speaker}**{emotion}：{line}{subtext}")
            if dialogue_lines:
                lines.append("**对白**")
                for item in dialogue_lines:
                    lines.extend([item, ""])

    return "\n".join(lines).rstrip() + "\n"
