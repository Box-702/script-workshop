"""JSON Schema validation + reference checks for ScriptForge scripts."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from .schemas import ValidationError


SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "script.schema.json"


@lru_cache
def _validator() -> Draft202012Validator:
    with SCHEMA_PATH.open("r", encoding="utf-8") as f:
        schema = json.load(f)
    return Draft202012Validator(schema)


def to_validation_errors(exc: jsonschema.ValidationError) -> ValidationError:
    path = ".".join(str(p) for p in exc.absolute_path) or "<root>"
    return ValidationError(path=path, message=exc.message)


def validate_script(data: dict[str, Any]) -> list[ValidationError]:
    """Run JSON Schema + cross-reference checks. Return all errors."""
    errors: list[ValidationError] = []
    v = _validator()
    for err in sorted(v.iter_errors(data), key=lambda e: list(e.absolute_path)):
        errors.append(to_validation_errors(err))

    # Cross-reference checks
    try:
        script = data.get("script", {})
        chapter_ids = set(script.get("source", {}).get("chapter_ids", []))
        char_ids = {c["id"] for c in script.get("characters", [])}
        loc_ids = {loc["id"] for loc in script.get("locations", [])}
        scene_ids: list[str] = []
        for i, scene in enumerate(script.get("scenes", [])):
            sid = scene.get("id", f"<scene[{i}]>")
            scene_ids.append(sid)
            # chapter_refs must exist
            for ref in scene.get("chapter_refs", []):
                if ref not in chapter_ids:
                    errors.append(
                        ValidationError(
                            path=f"script.scenes[{i}].chapter_refs",
                            message=f"unknown chapter id: {ref}",
                        )
                    )
            # location_id must exist
            if scene.get("location_id") not in loc_ids:
                errors.append(
                    ValidationError(
                        path=f"script.scenes[{i}].location_id",
                        message=f"unknown location id: {scene.get('location_id')}",
                    )
                )
            # characters must exist
            for j, cid in enumerate(scene.get("characters", [])):
                if cid not in char_ids:
                    errors.append(
                        ValidationError(
                            path=f"script.scenes[{i}].characters[{j}]",
                            message=f"unknown character id: {cid}",
                        )
                    )
            # dialogue speakers must exist
            for k, line in enumerate(scene.get("dialogue", [])):
                if line.get("speaker") not in char_ids:
                    errors.append(
                        ValidationError(
                            path=f"script.scenes[{i}].dialogue[{k}].speaker",
                            message=f"unknown character id: {line.get('speaker')}",
                        )
                    )
        # scene id uniqueness
        if len(scene_ids) != len(set(scene_ids)):
            errors.append(
                ValidationError(path="script.scenes", message="scene ids must be unique")
            )
        # character id uniqueness
        if len(char_ids) != len(set(char_ids)):
            errors.append(
                ValidationError(path="script.characters", message="character ids must be unique")
            )
    except Exception as e:  # noqa: BLE001
        errors.append(ValidationError(path="<root>", message=f"validation crashed: {e}"))
    return errors
