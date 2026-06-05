"""Pydantic v2 schemas for API and internal pipeline models."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


AdaptationType = Literal["series", "film", "short_drama", "stage", "other"]
RoleType = Literal["protagonist", "antagonist", "supporting", "mentor", "foil", "other"]
Fidelity = Literal["faithful", "compressed", "reordered", "merged", "invented"]
RunStatus = Literal["queued", "running", "done", "failed"]


# ===== API request/response =====


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    raw_text: str = Field(min_length=1)
    adaptation_type: AdaptationType = "short_drama"


class ChapterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    word_count: int
    order_index: int


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    adaptation_type: str
    status: str
    created_at: str
    chapter_count: int


class ProjectCreateResponse(BaseModel):
    project_id: str
    chapter_count: int
    chapters: list[ChapterOut]


class GenerateAccepted(BaseModel):
    run_id: str
    status: RunStatus


class RunOut(BaseModel):
    id: str
    project_id: str
    status: RunStatus
    current_step: str
    progress: int
    error_message: Optional[str] = None
    created_at: str
    updated_at: str


class ValidateRequest(BaseModel):
    yaml: str


class ValidationError(BaseModel):
    path: str
    message: str
    severity: Literal["error", "warning"] = "error"


class ValidateResponse(BaseModel):
    valid: bool
    errors: list[ValidationError] = Field(default_factory=list)


class RepairRequest(BaseModel):
    yaml: str
    errors: list[ValidationError] = Field(default_factory=list)


class RepairResponse(BaseModel):
    fixed_yaml: str
    changes: list[str]


# ===== Script domain models (mirror JSON Schema) =====


class Character(BaseModel):
    id: str = Field(pattern=r"^char_[a-z0-9_]+$")
    name: str
    role: Optional[RoleType] = None
    goal: Optional[str] = None
    motivation: Optional[str] = None
    personality: Optional[str] = None
    relationship: Optional[str] = None
    arc: Optional[str] = None
    speech_style: Optional[str] = None


class Location(BaseModel):
    id: str = Field(pattern=r"^loc_[a-z0-9_]+$")
    name: str
    description: Optional[str] = None


class DialogueLine(BaseModel):
    speaker: str = Field(pattern=r"^char_[a-z0-9_]+$")
    line: str
    emotion: Optional[str] = None
    subtext: Optional[str] = None


class AdaptationNotes(BaseModel):
    reason: Optional[str] = None
    fidelity: Optional[Fidelity] = None


class Scene(BaseModel):
    id: str = Field(pattern=r"^scene_[0-9]{3,}$")
    title: str
    chapter_refs: list[str] = Field(min_length=1)
    location_id: str = Field(pattern=r"^loc_[a-z0-9_]+$")
    time: Optional[str] = None
    characters: list[str] = Field(min_length=1)
    purpose: str
    conflict: str
    entry_state: Optional[str] = None
    exit_state: Optional[str] = None
    action: list[str] = Field(default_factory=list)
    dialogue: list[DialogueLine] = Field(default_factory=list)
    adaptation_notes: Optional[AdaptationNotes] = None


class Source(BaseModel):
    chapter_count: int = Field(ge=3)
    chapter_ids: list[str] = Field(min_length=3)


class Adaptation(BaseModel):
    type: AdaptationType
    target_format: Optional[str] = None
    tone: Optional[str] = None


class Script(BaseModel):
    """Top-level script object. Mirrors schema/script.schema.json."""

    title: str
    version: str = Field(default="1.0", pattern=r"^[0-9]+\.[0-9]+(\.[0-9]+)?$")
    language: str = "zh-CN"
    adaptation: Optional[Adaptation] = None
    source: Source
    logline: str = Field(min_length=10)
    themes: list[str] = Field(default_factory=list)
    characters: list[Character] = Field(min_length=1)
    locations: list[Location] = Field(default_factory=list)
    scenes: list[Scene] = Field(min_length=1)

    @field_validator("characters")
    @classmethod
    def _unique_char_ids(cls, v: list[Character]) -> list[Character]:
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("character ids must be unique")
        return v

    @field_validator("scenes")
    @classmethod
    def _unique_scene_ids(cls, v: list[Scene]) -> list[Scene]:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("scene ids must be unique")
        return v


class ScriptDocument(BaseModel):
    script: Script
