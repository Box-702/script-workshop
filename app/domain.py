# =====================================================================
# domain.py —— 剧本领域模型（数据契约）
#
# 这是「剧本工坊」主题的核心数据结构。它刻画一部结构化剧本：
#   剧本 Script -> 人物 Character / 地点 Location / 场景 Scene
#   场景 Scene   -> 节拍流 beats（动作 / 对白 / cue）+ 兼容字段 action / dialogue
#
# 模型用 Pydantic v2 定义，并带 `mode="before"` 校验器，把 LLM 输出的
# 自由文本（role / fidelity / id）规整到受约束的枚举与稳定 id 上，
# 从而让下游的 Agent patch、diff、校验和导出都能依赖稳定标识。
#
# 这一层刻意只放「数据形状与规整逻辑」，不碰存储、不碰 LLM、不碰 LangGraph，
# 保证它能在测试里被单独、稳定地验证。
# =====================================================================

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---- 受约束的枚举 -----
AdaptationType = Literal["series", "film", "short_drama", "stage", "other"]
RoleType = Literal["protagonist", "antagonist", "supporting", "mentor", "foil", "other"]
Fidelity = Literal["faithful", "compressed", "reordered", "merged", "invented"]

# ---- id / 枚举规整 ----
_ID_SUFFIX_RE = re.compile(r"[^a-z0-9_]+")


def _slug_token(value: str) -> str:
    """把任意字符串转成小写、适合 snake_case 的 token。"""
    s = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    s = _ID_SUFFIX_RE.sub("", s)
    return re.sub(r"_+", "_", s).strip("_")


def normalize_id(value: object, prefix: str, *, fallback: str | None = None) -> str:
    """把 LLM 给的 id 规整为 `<prefix>_[a-z0-9_]+`。

    策略：保留已合格 id；去掉已有 prefix 再重加；无剩余内容时用 fallback 或 hash。
    对 scene / beat 这类数字 id，不足三位自动补零，保证稳定可寻址。
    """
    seed = str(value).strip() if value is not None else (fallback or "")
    if seed.lower().startswith(prefix.lower() + "_"):
        seed = seed[len(prefix) + 1 :]
    elif seed.lower().startswith(prefix.lower()):
        seed = seed[len(prefix) :]
    slug = _slug_token(seed)
    if not slug:
        slug = _slug_token(fallback or "")
    if not slug:
        slug = hashlib.md5(str(value).encode("utf-8")).hexdigest()[:8]
    if prefix in {"scene", "beat"} and slug.isdigit():
        slug = slug.zfill(3)
    return f"{prefix}_{slug}"


_ROLE_ALIASES: dict[str, RoleType] = {
    "protagonist": "protagonist", "hero": "protagonist", "主角": "protagonist",
    "主人公": "protagonist", "第一主角": "protagonist",
    "antagonist": "antagonist", "villain": "antagonist", "反派": "antagonist",
    "对手": "antagonist", "敌人": "antagonist", "boss": "antagonist",
    "mentor": "mentor", "teacher": "mentor", "导师": "mentor", "老师": "mentor",
    "foil": "foil", "对照": "foil", "反衬": "foil",
    "supporting": "supporting", "sidekick": "supporting", "配角": "supporting",
    "辅助": "supporting", "助手": "supporting", "npc": "supporting",
    "other": "other", "narrator": "other", "旁白": "other",
}


def normalize_role(value: object) -> RoleType | None:
    """把自由文本角色名映射到 RoleType；无法识别时回退为 ``other``。"""
    text = str(value).strip() if value is not None else ""
    if not text:
        return None
    if text in _ROLE_ALIASES:
        return _ROLE_ALIASES[text]
    key = re.sub(r"[\s_]+", "", text).lower()
    if key in _ROLE_ALIASES:
        return _ROLE_ALIASES[key]
    for suffix in ("角色", "role"):
        if key.endswith(suffix) and key[: -len(suffix)] in _ROLE_ALIASES:
            return _ROLE_ALIASES[key[: -len(suffix)]]
    candidates = sorted(_ROLE_ALIASES.keys(), key=len, reverse=True)
    for alias in candidates:
        if alias and alias in key:
            return _ROLE_ALIASES[alias]
    return "other"


_FIDELITY_ALIASES: dict[str, Fidelity] = {
    "faithful": "faithful", "忠实": "faithful", "原貌": "faithful",
    "compressed": "compressed", "压缩": "compressed", "精简": "compressed",
    "reordered": "reordered", "重排": "reordered",
    "merged": "merged", "合并": "merged",
    "invented": "invented", "新增": "invented", "原创": "invented",
}


def normalize_fidelity(value: object) -> Fidelity | None:
    """把自由文本 fidelity 映射到枚举；无法识别时回退为 ``compressed``。"""
    text = str(value).strip() if value is not None else ""
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
    return "compressed"


_ADAPTATION_ALIASES: dict[str, AdaptationType] = {
    "series": "series", "tv": "series", "drama": "series", "剧集": "series",
    "电视剧": "series", "连续剧": "series",
    "film": "film", "movie": "film", "电影": "film", "院线": "film",
    "short_drama": "short_drama", "short": "short_drama", "短剧": "short_drama",
    "stage": "stage", "theatre": "stage", "舞台": "stage", "舞台剧": "stage",
    "other": "other", "其他": "other",
}


def normalize_adaptation_type(value: object) -> AdaptationType:
    """把自由文本改编类型映射到枚举；无法识别时回退为 ``other``。"""
    text = str(value).strip() if value is not None else ""
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


# ---- 领域模型 -----


class Character(BaseModel):
    """人物。id 需为 ``char_xxx`` 且全剧唯一。"""

    id: str = Field(pattern=r"^char_[a-z0-9_]+$")
    name: str
    role: RoleType | None = None
    goal: str | None = None
    motivation: str | None = None
    personality: str | None = None
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
    """地点。id 需为 ``loc_xxx``。"""

    id: str = Field(pattern=r"^loc_[a-z0-9_]+$")
    name: str
    description: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        return normalize_id(v, "loc", fallback=v)


class DialogueLine(BaseModel):
    """兼容结构里的对白行。speaker 必须引用某个 ``char_xxx``。"""

    speaker: str = Field(pattern=r"^char_[a-z0-9_]+$")
    line: str
    emotion: str | None = None
    subtext: str | None = None

    @field_validator("speaker", mode="before")
    @classmethod
    def _coerce_speaker(cls, v: object) -> object:
        return normalize_id(v, "char", fallback=v)


class ScriptBeat(BaseModel):
    """剧本流节拍：按阅读顺序混排动作 / 对白 / cue。id 需为 ``beat_数字``。"""

    id: str = Field(pattern=r"^beat_[0-9]{3,}$")
    type: Literal["action", "dialogue", "cue"]
    text: str | None = None
    speaker: str | None = Field(default=None, pattern=r"^char_[a-z0-9_]+$")
    line: str | None = None
    emotion: str | None = None
    subtext: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        return normalize_id(v, "beat", fallback=v)

    @field_validator("speaker", mode="before")
    @classmethod
    def _coerce_speaker(cls, v: object) -> object:
        if v is None or str(v).strip() == "":
            return None
        return normalize_id(v, "char", fallback=v)


class AdaptationNotes(BaseModel):
    """某个场景的改编说明。"""

    reason: str | None = None
    fidelity: Fidelity | None = None

    @field_validator("fidelity", mode="before")
    @classmethod
    def _coerce_fidelity(cls, v: object) -> object:
        return normalize_fidelity(v)


class Scene(BaseModel):
    """场景。id 需为 ``scene_数字``。

    ``beats`` 是主编辑结构；``action`` / ``dialogue`` 是兼容层，
    由后端在应用 patch 后从 beats 自动同步。
    """

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
    beats: list[ScriptBeat] = Field(default_factory=list)
    adaptation_notes: AdaptationNotes | None = None

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


class Source(BaseModel):
    """来源信息：原始章节数与其 id（至少 3 章才符合产品预期）。"""

    chapter_count: int = Field(ge=1)
    chapter_ids: list[str] = Field(min_length=1)


class Adaptation(BaseModel):
    """改编元信息：类型与目标格式。"""

    type: AdaptationType
    target_format: str | None = None
    tone: str | None = None

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_type(cls, v: object) -> object:
        return normalize_adaptation_type(v)


class Script(BaseModel):
    """顶层剧本对象，对应 schema/script.schema.json。"""

    model_config = ConfigDict(validate_assignment=False)

    title: str
    version: str = Field(default="1.0")
    language: str = "zh-CN"
    adaptation: Adaptation | None = None
    source: Source
    logline: str = Field(min_length=1)
    themes: list[str] = Field(default_factory=list)
    characters: list[Character] = Field(min_length=1)
    locations: list[Location] = Field(default_factory=list)
    scenes: list[Scene] = Field(min_length=1)

    @field_validator("characters")
    @classmethod
    def _unique_char_ids(cls, v: list[Character]) -> list[Character]:
        ids = [c.id for c in v]
        if len(ids) != len(set(ids)):
            raise ValueError("人物 id 必须唯一")
        return v

    @field_validator("scenes")
    @classmethod
    def _unique_scene_ids(cls, v: list[Scene]) -> list[Scene]:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("场景 id 必须唯一")
        return v


class ScriptDocument(BaseModel):
    """根文档：包一层 ``script`` 字段，与现有项目 / 旧数据兼容。"""

    script: Script


def script_from_dict(data: dict[str, Any]) -> Script:
    """从字典构建 Script，容错处理缺失字段。"""
    return Script.model_validate(data)
