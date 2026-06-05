from __future__ import annotations

import json
from typing import Any


def script_to_json_text(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def script_to_markdown(data: dict[str, Any]) -> str:
    script = data.get("script", {}) if isinstance(data.get("script"), dict) else {}
    title = str(script.get("title") or "Untitled Script")
    lines = [f"# {title}", ""]

    logline = script.get("logline")
    if logline:
        lines.extend(["## Logline", str(logline), ""])

    themes = script.get("themes") or []
    if themes:
        lines.extend(["## Themes", *[f"- {theme}" for theme in themes], ""])

    characters = script.get("characters") or []
    character_names = {
        item.get("id"): item.get("name")
        for item in characters
        if isinstance(item, dict) and item.get("id")
    }
    if characters:
        lines.append("## Characters")
        for character in characters:
            if not isinstance(character, dict):
                continue
            name = character.get("name") or character.get("id") or "Unnamed"
            role = f" ({character['role']})" if character.get("role") else ""
            detail = character.get("goal") or character.get("motivation") or character.get("arc")
            suffix = f": {detail}" if detail else ""
            lines.append(f"- **{name}**{role}{suffix}")
        lines.append("")

    locations = script.get("locations") or []
    if locations:
        lines.append("## Locations")
        for location in locations:
            if not isinstance(location, dict):
                continue
            name = location.get("name") or location.get("id") or "Unnamed"
            description = f": {location['description']}" if location.get("description") else ""
            lines.append(f"- **{name}**{description}")
        lines.append("")

    scenes = script.get("scenes") or []
    if scenes:
        lines.append("## Scenes")
        for scene in scenes:
            if not isinstance(scene, dict):
                continue
            scene_id = scene.get("id") or "scene"
            scene_title = scene.get("title") or "Untitled"
            lines.extend([f"### {scene_id}: {scene_title}", ""])

            for label, key in (
                ("Purpose", "purpose"),
                ("Conflict", "conflict"),
                ("Entry", "entry_state"),
                ("Exit", "exit_state"),
            ):
                if scene.get(key):
                    lines.append(f"**{label}:** {scene[key]}")
            if any(scene.get(key) for key in ("purpose", "conflict", "entry_state", "exit_state")):
                lines.append("")

            action = scene.get("action") or []
            if action:
                lines.append("**Action**")
                lines.extend(f"- {item}" for item in action)
                lines.append("")

            dialogue = scene.get("dialogue") or []
            if dialogue:
                lines.append("**Dialogue**")
                for item in dialogue:
                    if not isinstance(item, dict):
                        continue
                    speaker = character_names.get(item.get("speaker"), item.get("speaker") or "Unknown")
                    line = item.get("line") or ""
                    emotion = f" ({item['emotion']})" if item.get("emotion") else ""
                    lines.append(f"- **{speaker}**{emotion}: {line}")
                lines.append("")

    return "\n".join(lines).rstrip() + "\n"
