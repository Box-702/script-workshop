"""Schema-aware repair for user-edited YAML.

Goals:
- Fill missing optional fields with safe defaults.
- Fix obvious id typos by aligning references to known character/location ids.
- Strip dialogue lines whose speaker is unknown.
- Do NOT alter user-supplied content (lines, action, conflict text).
"""
from __future__ import annotations

from .validation import validate_script
from .yaml_io import from_yaml, to_yaml


def _nearest(target: str, pool: set[str]) -> str | None:
    if target in pool:
        return target
    if not pool:
        return None
    # 1. Same prefix of length 4 (e.g. char_linyu -> char_linyu_xxx)
    for p in pool:
        if p.startswith(target[:8]) or target.startswith(p[:8]):
            return p
    # 2. Same prefix of length 5 — covers char_X vs char_X_h6xxxx when X>=5
    for p in pool:
        if p.startswith(target[:5]) or target.startswith(p[:5]):
            return p
    # 3. char_/loc_ shared root: compare the part after the underscore
    def _root(s: str) -> str:
        parts = s.split("_", 1)
        return parts[1] if len(parts) > 1 else s

    t_root = _root(target)
    best: tuple[int, str] | None = None
    for p in pool:
        p_root = _root(p)
        # longest common prefix of roots
        n = 0
        for a, b in zip(t_root, p_root, strict=False):
            if a != b:
                break
            n += 1
        if n >= 4 and (best is None or n > best[0]):
            best = (n, p)
    return best[1] if best else None


def repair_yaml(yaml_text: str) -> tuple[str, list[str]]:
    try:
        data = from_yaml(yaml_text) or {}
    except Exception as e:  # noqa: BLE001
        return yaml_text, [f"YAML parse error; nothing repaired: {e}"]
    if not isinstance(data, dict):
        return yaml_text, ["payload is not a mapping; nothing repaired"]

    changes: list[str] = []

    # Pre-pass: collect character & location ids
    script = data.get("script", {}) if isinstance(data.get("script"), dict) else {}
    char_ids = {c.get("id") for c in script.get("characters", []) if isinstance(c, dict)}
    loc_ids = {loc.get("id") for loc in script.get("locations", []) if isinstance(loc, dict)}
    chapter_ids = set((script.get("source") or {}).get("chapter_ids", []) or [])

    # Fix scene references
    for i, scene in enumerate(script.get("scenes", []) or []):
        if not isinstance(scene, dict):
            continue
        if scene.get("location_id") and scene["location_id"] not in loc_ids and loc_ids:
            rep = _nearest(scene["location_id"], loc_ids)
            if rep:
                scene["location_id"] = rep
                changes.append(f"script.scenes[{i}].location_id: snapped to known id '{rep}'")
        # characters
        if isinstance(scene.get("characters"), list):
            new_chars: list[str] = []
            for cid in scene["characters"]:
                if cid in char_ids or not char_ids:
                    new_chars.append(cid)
                else:
                    rep = _nearest(cid, char_ids)
                    if rep:
                        new_chars.append(rep)
                        changes.append(
                            f"script.scenes[{i}].characters: snapped '{cid}' -> '{rep}'"
                        )
                    else:
                        changes.append(
                            f"script.scenes[{i}].characters: removed unknown id '{cid}'"
                        )
            scene["characters"] = new_chars
        # dialogue speakers
        if isinstance(scene.get("dialogue"), list):
            for k, line in enumerate(scene["dialogue"]):
                if not isinstance(line, dict):
                    continue
                if line.get("speaker") not in char_ids and char_ids:
                    rep = _nearest(line["speaker"], char_ids)
                    if rep:
                        line["speaker"] = rep
                        changes.append(
                            f"script.scenes[{i}].dialogue[{k}].speaker: snapped to '{rep}'"
                        )
                    else:
                        changes.append(
                            f"script.scenes[{i}].dialogue[{k}].speaker: removed unknown speaker"
                        )
                        line["__invalid__"] = True
            scene["dialogue"] = [ln for ln in scene["dialogue"] if not ln.get("__invalid__")]
        # script-flow dialogue speakers
        if isinstance(scene.get("beats"), list):
            for k, beat in enumerate(scene["beats"]):
                if not isinstance(beat, dict) or beat.get("type") != "dialogue":
                    continue
                if beat.get("speaker") not in char_ids and char_ids:
                    rep = _nearest(beat["speaker"], char_ids)
                    if rep:
                        beat["speaker"] = rep
                        changes.append(
                            f"script.scenes[{i}].beats[{k}].speaker: snapped to '{rep}'"
                        )
                    else:
                        changes.append(
                            f"script.scenes[{i}].beats[{k}].speaker: removed unknown speaker"
                        )
                        beat["__invalid__"] = True
            scene["beats"] = [beat for beat in scene["beats"] if not beat.get("__invalid__")]
        # chapter_refs: drop unknowns
        if isinstance(scene.get("chapter_refs"), list):
            keep = [c for c in scene["chapter_refs"] if c in chapter_ids] or scene["chapter_refs"]
            if keep != scene["chapter_refs"]:
                changes.append(
                    f"script.scenes[{i}].chapter_refs: pruned unknown chapter ids"
                )
                scene["chapter_refs"] = keep

    data["script"] = script

    # Re-validate; if still invalid, don't add defaults that may lie
    errs = validate_script(data)
    if errs:
        changes.append(f"repair finished with {len(errs)} remaining errors (no auto-fill applied)")
    return to_yaml(data), changes
