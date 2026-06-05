"""Pydantic v2 schemas for API and internal pipeline models."""
from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

AdaptationType = Literal["series", "film", "short_drama", "stage", "other"]
RoleType = Literal["protagonist", "antagonist", "supporting", "mentor", "foil", "other"]
Fidelity = Literal["faithful", "compressed", "reordered", "merged", "invented"]
RunStatus = Literal["queued", "running", "done", "failed"]


_ROLE_ALIASES: dict[str, RoleType] = {
    # protagonist
    "protagonist": "protagonist",
    "hero": "protagonist",
    "主角": "protagonist",
    "主人公": "protagonist",
    "第一主角": "protagonist",
    # antagonist
    "antagonist": "antagonist",
    "villain": "antagonist",
    "反派": "antagonist",
    "对手": "antagonist",
    "敌人": "antagonist",
    "boss": "antagonist",
    # mentor
    "mentor": "mentor",
    "teacher": "mentor",
    "导师": "mentor",
    "老师": "mentor",
    "师父": "mentor",
    # foil
    "foil": "foil",
    "对照": "foil",
    "反衬": "foil",
    # supporting
    "supporting": "supporting",
    "sidekick": "supporting",
    "配角": "supporting",
    "辅助": "supporting",
    "助手": "supporting",
    "协助者": "supporting",
    "npc": "supporting",
    "护士": "supporting",
    "医生": "supporting",
    "警察": "supporting",
    # other
    "other": "other",
    "narrator": "other",
    "旁白": "other",
    "叙述者": "other",
}


def normalize_role(value: object) -> RoleType | None:
    """Coerce a free-form LLM-provided role into the RoleType enum.

    - None / empty → None
    - already a valid literal → kept
    - Chinese/English alias → mapped
    - otherwise → "other"
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in _ROLE_ALIASES:
        return _ROLE_ALIASES[text]
    key = re.sub(r"[\s_]+", "", text).lower()
    if key in _ROLE_ALIASES:
        return _ROLE_ALIASES[key]
    # strip a trailing "角色" / "角色" type suffix
    for suffix in ("角色", "role"):
        if key.endswith(suffix):
            stem = key[: -len(suffix)]
            if stem in _ROLE_ALIASES:
                return _ROLE_ALIASES[stem]
    # substring match: any alias contained in the input wins (longest first)
    candidates = sorted(_ROLE_ALIASES.keys(), key=len, reverse=True)
    for alias in candidates:
        if alias and alias in key:
            return _ROLE_ALIASES[alias]
    return "other"


_FIDELITY_ALIASES: dict[str, Fidelity] = {
    "faithful": "faithful",
    "faithfuladaptation": "faithful",
    "忠实": "faithful",
    "忠实改编": "faithful",
    "原貌": "faithful",
    "compressed": "compressed",
    "compress": "compressed",
    "condensed": "compressed",
    "abridged": "compressed",
    "压缩": "compressed",
    "精简": "compressed",
    "删减": "compressed",
    "reordered": "reordered",
    "reshuffled": "reordered",
    "rearranged": "reordered",
    "重排": "reordered",
    "调换": "reordered",
    "merged": "merged",
    "combined": "merged",
    "合并": "merged",
    "融合": "merged",
    "invented": "invented",
    "added": "invented",
    "原创": "invented",
    "新加": "invented",
    "新增": "invented",
}


def normalize_fidelity(value: object) -> Fidelity | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in _FIDELITY_ALIASES:
        return _FIDELITY_ALIASES[text]
    key = re.sub(r"[\s_]+", "", text).lower()
    if key in _FIDELITY_ALIASES:
        return _FIDELITY_ALIASES[key]
    for alias in sorted(_FIDELITY_ALIASES.keys(), key=len, reverse=True):
        if alias and alias in key:
            return _FIDELITY_ALIASES[alias]
    return "compressed"  # safe default for unrecognised fidelity


_ADAPTATION_ALIASES: dict[str, AdaptationType] = {
    "series": "series",
    "tv": "series",
    "television": "series",
    "drama": "series",
    "连续剧": "series",
    "电视剧": "series",
    "剧集": "series",
    "film": "film",
    "movie": "film",
    "feature": "film",
    "电影": "film",
    "院线": "film",
    "short_drama": "short_drama",
    "shortdrama": "short_drama",
    "short": "short_drama",
    "短剧": "short_drama",
    "短视频": "short_drama",
    "stage": "stage",
    "theatre": "stage",
    "theater": "stage",
    "舞台": "stage",
    "舞台剧": "stage",
    "话剧": "stage",
    "戏剧": "stage",
    "other": "other",
    "其他": "other",
}


def normalize_adaptation_type(value: object) -> AdaptationType:
    if value is None:
        return "other"
    text = str(value).strip()
    if not text:
        return "other"
    if text in _ADAPTATION_ALIASES:
        return _ADAPTATION_ALIASES[text]
    key = re.sub(r"[\s_]+", "", text).lower()
    if key in _ADAPTATION_ALIASES:
        return _ADAPTATION_ALIASES[key]
    for alias in sorted(_ADAPTATION_ALIASES.keys(), key=len, reverse=True):
        if alias and alias in key:
            return _ADAPTATION_ALIASES[alias]
    return "other"


_ID_SUFFIX_RE = re.compile(r"[^a-z0-9_]+")


def _slug_token(value: str) -> str:
    """Map any string to a lowercase, snake-friendly token (no leading/trailing _)."""
    s = str(value).strip().lower()
    s = s.replace("-", "_").replace(" ", "_")
    s = _ID_SUFFIX_RE.sub("", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def normalize_id(value: object, prefix: str, *, fallback: str | None = None) -> str:
    """Coerce an LLM-supplied id into `<prefix>_[a-z0-9_]+`.

    Strategy:
    - Keep the existing valid id untouched.
    - Strip an existing prefix and re-apply ours.
    - Slugify the rest.
    - If nothing is left, fall back to `<prefix>_<fallback>` or `<prefix>_<hash>`.
    """
    if value is None:
        seed = fallback or ""
    else:
        seed = str(value).strip()
    # If the seed already starts with prefix, strip it before slugifying to avoid duplication.
    if seed.lower().startswith(prefix.lower() + "_"):
        seed = seed[len(prefix) + 1 :]
    elif seed.lower().startswith(prefix.lower()):
        seed = seed[len(prefix) :]
    slug = _slug_token(seed)
    if not slug:
        slug = _slug_token(fallback or "")
    if not slug:
        slug = hashlib.md5(str(value).encode("utf-8")).hexdigest()[:8]
    # Scene ids follow `<prefix>_<digits>`. If the slug isn't all digits, keep
    # the slug as-is; otherwise zero-pad short numbers so they satisfy the
    # `<prefix>_[0-9]{3,}` pattern that downstream code (and the JSON schema)
    # expects.
    if prefix == "scene" and slug.isdigit():
        slug = slug.zfill(3)
    return f"{prefix}_{slug}"


# ===== API request/response =====


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    raw_text: str = Field(min_length=1)
    adaptation_type: AdaptationType = "short_drama"
    # BCP-47 language tag for the *output*. If omitted, the server detects
    # the dominant script of `raw_text` and uses that.
    language: str | None = None


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
    error_message: str | None = None
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


class ScriptVersionSaveRequest(BaseModel):
    yaml: str = Field(min_length=1)


class ScriptVersionOut(BaseModel):
    id: str
    project_id: str
    validation_status: str
    validation_errors: list[dict] | None = None
    created_at: str


class ScriptVersionDetail(ScriptVersionOut):
    yaml_content: str


# ===== Script domain models (mirror JSON Schema) =====


class Character(BaseModel):
    id: str = Field(pattern=r"^char_[a-z0-9_]+$")
    name: str
    role: RoleType | None = None
    goal: str | None = None
    motivation: str | None = None
    personality: str | None = None
    relationship: str | None = None
    arc: str | None = None
    speech_style: str | None = None

    @field_validator("role", mode="before")
    @classmethod
    def _coerce_role(cls, v: object) -> object:
        return normalize_role(v)

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        return normalize_id(v, "char", fallback=v)


class Location(BaseModel):
    id: str = Field(pattern=r"^loc_[a-z0-9_]+$")
    name: str
    description: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        return normalize_id(v, "loc", fallback=v)


class DialogueLine(BaseModel):
    speaker: str = Field(pattern=r"^char_[a-z0-9_]+$")
    line: str
    emotion: str | None = None
    subtext: str | None = None

    @field_validator("speaker", mode="before")
    @classmethod
    def _coerce_speaker(cls, v: object) -> object:
        return normalize_id(v, "char", fallback=v)


class AdaptationNotes(BaseModel):
    reason: str | None = None
    fidelity: Fidelity | None = None

    @field_validator("fidelity", mode="before")
    @classmethod
    def _coerce_fidelity(cls, v: object) -> object:
        return normalize_fidelity(v)


class Scene(BaseModel):
    id: str = Field(pattern=r"^scene_[0-9]{3,}$")
    title: str
    chapter_refs: list[str] = Field(min_length=1)
    location_id: str = Field(pattern=r"^loc_[a-z0-9_]+$")
    time: str | None = None
    characters: list[str] = Field(min_length=1)
    purpose: str
    conflict: str
    entry_state: str | None = None
    exit_state: str | None = None
    action: list[str] = Field(default_factory=list)
    dialogue: list[DialogueLine] = Field(default_factory=list)

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        return normalize_id(v, "scene", fallback=v)

    @field_validator("location_id", mode="before")
    @classmethod
    def _coerce_location_id(cls, v: object) -> object:
        return normalize_id(v, "loc", fallback=v)

    @field_validator("characters", mode="before")
    @classmethod
    def _coerce_characters(cls, v: object) -> object:
        if not isinstance(v, list):
            return v
        return [normalize_id(x, "char", fallback=x) for x in v]
    adaptation_notes: AdaptationNotes | None = None


class Source(BaseModel):
    chapter_count: int = Field(ge=3)
    chapter_ids: list[str] = Field(min_length=3)


class Adaptation(BaseModel):
    type: AdaptationType
    target_format: str | None = None
    tone: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: object) -> object:
        return normalize_adaptation_type(v)


class Script(BaseModel):
    """Top-level script object. Mirrors schema/script.schema.json."""

    title: str
    version: str = Field(default="1.0", pattern=r"^[0-9]+\.[0-9]+(\.[0-9]+)?$")
    language: str = "zh-CN"
    adaptation: Adaptation | None = None
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
