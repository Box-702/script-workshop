"""Validation + repair endpoints (operate on raw YAML text)."""
from __future__ import annotations

from fastapi import APIRouter

from ..repair import repair_yaml
from ..schemas import (
    RepairRequest,
    RepairResponse,
    ScriptYamlResponse,
    ValidateRequest,
    ValidateResponse,
    ValidateScriptRequest,
)
from ..validation import validate_script
from ..yaml_io import from_yaml, to_yaml

router = APIRouter(prefix="/api", tags=["validate"])


@router.post("/validate", response_model=ValidateResponse)
def validate(req: ValidateRequest) -> ValidateResponse:
    try:
        data = from_yaml(req.yaml)
    except Exception as e:  # noqa: BLE001
        return ValidateResponse(
            valid=False, errors=[{"path": "<root>", "message": f"YAML parse error: {e}"}]
        )
    if not isinstance(data, dict):
        return ValidateResponse(
            valid=False, errors=[{"path": "<root>", "message": "root must be a mapping"}]
        )
    errors = validate_script(data)
    return ValidateResponse(valid=not errors, errors=errors)


@router.post("/validate/script", response_model=ValidateResponse)
def validate_script_json(req: ValidateScriptRequest) -> ValidateResponse:
    data = {"script": req.script}
    errors = validate_script(data)
    return ValidateResponse(valid=not errors, errors=errors)


@router.post("/script-to-yaml", response_model=ScriptYamlResponse)
def script_to_yaml(req: ValidateScriptRequest) -> ScriptYamlResponse:
    return ScriptYamlResponse(yaml=to_yaml({"script": req.script}))


@router.post("/repair", response_model=RepairResponse)
def repair(req: RepairRequest) -> RepairResponse:
    fixed, changes = repair_yaml(req.yaml)
    return RepairResponse(fixed_yaml=fixed, changes=changes)
