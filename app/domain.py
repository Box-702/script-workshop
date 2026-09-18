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


def _strip_prefix(seed: str, prefix: str) -> str:
    """剥掉字符串开头已有的 `<prefix>_` 前缀（大小写不敏感）。"""
    low = seed.lower()
    if low.startswith(prefix.lower() + "_"):
        return seed[len(prefix) + 1 :]
    if low.startswith(prefix.lower()):
        return seed[len(prefix) :]
    return seed


def normalize_id(value: object, prefix: str, *, fallback: str | None = None) -> str:
    """把 LLM 给的 id 规整为 `<prefix>_[a-z0-9_]+`。

    策略：保留已合格 id；去掉已有 prefix 再重加；无剩余内容时用 fallback 或 hash。
    对 scene / beat 这类数字 id，不足三位自动补零，保证稳定可寻址。

    注意：fallback 也要先剥前缀，否则 fallback 传进来的 "loc_main" 会被再拼一次，
    变成 "loc_loc_main"，导致引用对不上。
    """
    seed = str(value).strip() if value is not None else (fallback or "")
    slug = _slug_token(_strip_prefix(seed, prefix))
    if not slug:
        slug = _slug_token(_strip_prefix(str(fallback or "").strip(), prefix))
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


# =====================================================================
# 视频制作领域模型（v3.0 新增）
#
# 小说 → 剧本 → 分镜 → AI 短剧 全链路中的后半段数据结构。
# =====================================================================

# ---- 视频制作枚举 ----
ShotType = Literal[
    "extreme_wide", "wide", "medium", "close_up",
    "extreme_close_up", "over_shoulder", "pov",
]
CameraMoveType = Literal[
    "static", "pan", "tilt", "dolly", "tracking",
    "crane", "handheld", "zoom", "steady", "orbit",
]
CameraSpeed = Literal["slow", "medium", "fast"]
PacingType = Literal["slow", "medium", "fast", "variable"]
TransitionType = Literal["cut", "fade", "dissolve", "wipe", "none"]


class CameraMovement(BaseModel):
    """摄影机运动。

    只写 ``type``（推/摇/移）不足以让视频模型拍出想要的运动——它不知道镜头
    从哪儿出发、到哪儿停下。``path`` / ``height`` 把「摄影师规划好的运动轨迹」
    写成文字：把摄影机设想成一台贴近人物飞行的虚拟无人机，写清起点到终点的
    相对距离、机位高度与运动方式（前进/后退/侧移/环绕/升降/偏航/俯仰与惯性）。
    """

    type: CameraMoveType = "static"
    direction: str | None = None  # left / right / up / down / in / out
    speed: CameraSpeed = "medium"
    path: str = ""    # 运镜轨迹：起点 → 终点，含与主体的距离/角度变化与运动规律
    height: str = ""  # 机位高度：如「与人物胸口齐平，随后降到贴地」


class Shot(BaseModel):
    """镜头：场景拆解后的最小视频生成单元。

    每个镜头对应一段 5-10 秒的 AI 生成视频。
    ``id`` 格式为 ``shot_sceneXXX_NNN``。

    一致性锚定：文生视频每个镜头是独立采样，仅靠 prompt 无法跨镜锁住
    场景与人物。通过以下字段把「共享参考素材 / 首尾帧接力」显式建模：
      - reference_images/videos：贯穿全片的共享环境参考图、上一镜成片参考；
      - first/last_frame_image：首尾帧控制（镜头 N 尾帧 → 镜头 N+1 首帧）。
    """

    id: str = Field(pattern=r"^shot_[a-z0-9_]+_\d{3,}$")
    scene_id: str = Field(pattern=r"^scene_[0-9]{3,}$")
    order: int = Field(ge=0)
    shot_type: ShotType = "medium"
    camera: CameraMovement = Field(default_factory=CameraMovement)
    subject: str = ""
    action: str = ""
    dialogue_ref: str | None = None  # 关联 beat_xxx
    duration_sec: float = Field(default=5.0, ge=1.0, le=30.0)
    lighting: str | None = None
    mood: str | None = None
    # ---- 画面调度的文字证据：视频模型看不见导演的脑内画面，只能靠这些字段 ----
    spatial: str = ""            # 空间关系：人物编号、人物间相对距离、离镜头/地面多高，及其在运镜中的变化
    background_action: str = ""  # 背景人物各自独立、不同步的生活化行为（允许少数人静止）
    cut_reason: str = ""               # 为什么必须在这里切镜（写不出理由就该合并）
    # ---- 一致性计划（导演输出的符号化接力方案，运行时再解析为下面的 URL）----
    reference_group: str = ""          # 共享环境参考图分组键：同组镜头共用一张环境参考图
    chain_from: int | None = None      # 首帧接力：本镜首帧取自该 order 镜头的尾帧；None=序列起点/硬切
    # ---- 一致性锚定（多模态输入，对接 VideoJobParams）----
    reference_images: list[str] = Field(default_factory=list)  # 共享环境/人物参考图 URL
    reference_videos: list[str] = Field(default_factory=list)  # 参考上一镜成片 URL，锁风格/运镜/光影
    first_frame_image: str | None = None  # 首帧图（接上一镜尾帧）
    last_frame_image: str | None = None   # 尾帧图（供下一镜接力）
    # ---- 视频生成状态 ----
    video_prompt: str | None = None
    video_url: str | None = None
    video_job_id: str | None = None

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        s = str(v).strip() if v is not None else ""
        if s.startswith("shot_"):
            return s
        return f"shot_{_slug_token(s) or hashlib.md5(str(v).encode()).hexdigest()[:8]}"

    @field_validator("scene_id", mode="before")
    @classmethod
    def _coerce_scene_id(cls, v: object) -> object:
        return normalize_id(v, "scene", fallback=v)

    @field_validator("dialogue_ref", mode="before")
    @classmethod
    def _coerce_dialogue_ref(cls, v: object) -> object:
        if v is None or str(v).strip() == "":
            return None
        return normalize_id(v, "beat", fallback=v)


class StyleGuide(BaseModel):
    """视觉风格指南：由美术指导 Agent 生成。

    ``reference_images`` 是图像级视觉锚的注册表：{人物名/地点名: 定妆图 URL}。
    由参考资产流水线（app/media/refs.py）生成并质检后回填，供镜头作为 reference_images 使用。
    """

    color_palette: list[str] = Field(default_factory=list)
    lighting_style: str = ""
    camera_style: str = ""
    visual_references: list[str] = Field(default_factory=list)
    character_appearances: dict[str, str] = Field(default_factory=dict)
    environment_descriptions: dict[str, str] = Field(default_factory=dict)
    reference_images: dict[str, str] = Field(default_factory=dict)


class SceneBreakdown(BaseModel):
    """场景拆解：由导演 Agent 生成，将一个 Scene 分解为多个 Shot。"""

    scene_id: str = Field(pattern=r"^scene_[0-9]{3,}$")
    director_notes: str = ""
    visual_approach: str = ""
    pacing: PacingType = "medium"
    key_moments: list[str] = Field(default_factory=list)
    shots: list[Shot] = Field(default_factory=list)

    @field_validator("scene_id", mode="before")
    @classmethod
    def _coerce_scene_id(cls, v: object) -> object:
        return normalize_id(v, "scene", fallback=v)


class VideoVersion(BaseModel):
    """视频版本快照：记录某次完整的分镜/镜头状态。"""

    id: str = Field(pattern=r"^vver_[a-z0-9_]+$")
    project_id: str
    parent_version_id: str | None = None
    source_type: str = "agent"  # agent / manual / generation
    label: str | None = None
    notes: str | None = None
    milestone: str | None = None  # draft / candidate / final
    shots: list[Shot] = Field(default_factory=list)
    style_guide: StyleGuide = Field(default_factory=StyleGuide)

    @field_validator("id", mode="before")
    @classmethod
    def _coerce_id(cls, v: object) -> object:
        s = str(v).strip() if v is not None else ""
        if s.startswith("vver_"):
            return s
        return f"vver_{_slug_token(s) or hashlib.md5(str(v).encode()).hexdigest()[:8]}"
