"""节奏建议时长：给「这一镜该拍多长」一个默认值，而不是让调用方各自拍脑袋。

为什么需要它
------------
出片接口原先写死 ``params.get("duration_sec") or 6``——导演在分镜里设计的
8 秒、10 秒镜头，只要调用方没显式传时长，就会一律按 6 秒送进模型。动作被
硬塞进更短的时间，模型只能丢节拍、糊成一片（2026-10-31《孔乙己》实测）。

现在的优先级是：**调用方显式指定 > 导演给该镜的 duration_sec > 这里的节奏默认值**。
用户随时可以在提交出片时改 duration_sec 覆盖掉前两者。

节奏档位
--------
- slow：长镜，让观众沉进空间与情绪里（停顿比剪切更重要）；
- medium：常规叙事镜头；
- fast：短镜，靠切碎制造加速度（冲击镜头）；
- variable：本场节奏本身有起伏（建立 → 加速 → 收），按 medium 取值。

按改编类型分档（2026-10-31 加入）
--------------------------------
短剧不是「短一点的电影」，而是另一种观看场景：手机竖屏、手指随时准备划走。
它的默认节奏必须更紧——基准镜头 4–6 秒，慢镜只留给情绪转折，不能像电影那样
开场先给 8 秒的环境建立。所以同一档 pacing 在不同类型下取不同的秒数：
短剧 medium = 5 秒，电影 medium = 6 秒，舞台 medium = 8 秒（观众已在场，不必抢注意力）。

数值是**起点不是枷锁**：导演可以按时长阶梯（长 → 渐短 → 冲击）在这附近微调，
只要落在生成器的可行区间内；用户后期也能逐镜覆盖。
"""

from __future__ import annotations

# 单镜可行区间：与导演侧校验（4–15 秒）保持一致，改一处就要改两处。
MIN_SHOT_SEC = 4.0
MAX_SHOT_SEC = 15.0

# 各节奏档的基准单镜时长（未指定改编类型时的通用值）。
RHYTHM_BASE_SEC: dict[str, float] = {
    "slow": 8.0,
    "medium": 6.0,
    "fast": 4.0,
    "variable": 6.0,  # 有起伏的场：取中位，让导演自己在阶梯上拉开
}

# 按改编类型覆盖基准值。短剧整体下压一档——短视频时代的注意力只给开头 3 秒。
RHYTHM_BY_FORMAT: dict[str, dict[str, float]] = {
    "short_drama": {"slow": 6.0, "medium": 5.0, "fast": 4.0, "variable": 5.0},
    "film": {"slow": 8.0, "medium": 6.0, "fast": 4.0, "variable": 6.0},
    "series": {"slow": 8.0, "medium": 6.0, "fast": 4.0, "variable": 6.0},
    "stage": {"slow": 10.0, "medium": 8.0, "fast": 6.0, "variable": 8.0},
    "other": dict(RHYTHM_BASE_SEC),
}

# 拿不到 adaptation_type 时的类型兜底。
DEFAULT_FORMAT = "other"

# 各类型在导演没给 pacing 时的默认档位：短剧默认就是快的。
DEFAULT_PACING_BY_FORMAT: dict[str, str] = {
    "short_drama": "fast",
    "film": "medium",
    "series": "medium",
    "stage": "medium",
    "other": "medium",
}

VALID_PACINGS = ("slow", "medium", "fast", "variable")

# 拿不到 pacing 时的兜底（也是新镜头的默认时长）。短剧项目请走 suggest_duration。
DEFAULT_SHOT_SEC = RHYTHM_BASE_SEC["medium"]


def normalize_format(format: str | None) -> str:
    """改编类型别名 -> 本模块认识的键（不认识的一律当 other）。"""
    key = str(format or "").strip().lower()
    if key in RHYTHM_BY_FORMAT:
        return key
    if key in {"short", "短剧", "短视频"}:
        return "short_drama"
    if key in {"anime", "漫剧", "动态漫", "漫画剧", "二次元"}:
        return "other"  # 画风不是改编类型：漫剧=短剧+二次元画风，见 visual_styles.py
    if key in {"movie", "电影", "院线"}:
        return "film"
    if key in {"tv", "drama", "剧集", "电视剧"}:
        return "series"
    if key in {"theatre", "舞台", "舞台剧"}:
        return "stage"
    return DEFAULT_FORMAT


def rhythm_table(format: str | None = None) -> dict[str, float]:
    """该类型的完整节奏表（pacing -> 建议秒数）。"""
    return dict(RHYTHM_BY_FORMAT[normalize_format(format)])


def default_pacing(format: str | None = None) -> str:
    """该类型在导演缺省时该用的 pacing。短剧 = fast（4 秒一镜）。"""
    return DEFAULT_PACING_BY_FORMAT[normalize_format(format)]


def suggest_duration(pacing: str | None = None, format: str | None = None) -> float:
    """按本场节奏与改编类型给一个建议单镜时长。

    ``format`` 缺省时用通用表；非法 pacing 落到该类型的 medium。
    """
    table = RHYTHM_BY_FORMAT[normalize_format(format)]
    key = str(pacing or "").strip().lower()
    return table.get(key, table["medium"])


def clamp_duration(sec: float) -> float:
    """把时长夹进生成器可行区间（模型偶尔给出 2 秒、20 秒这类不可执行的值）。"""
    return max(MIN_SHOT_SEC, min(MAX_SHOT_SEC, float(sec)))


def suggest_ladder(pacing: str | None, count: int, format: str | None = None) -> list[float]:
    """给出一个场景内 ``count`` 个镜头的时长阶梯建议（长 → 渐短 → 收尾）。

    slow 缓降、medium 中速渐短、fast 急剧缩短——最后一镜略回收，避免整场
    越切越碎、观众疲劳。仅作默认建议，导演可逐镜覆盖。

    短剧的 fast 阶梯从 6 秒收到 4 秒（4×1.5 → 4），正好是短视频的常见切镜密度。
    """
    if count <= 0:
        return []
    base = suggest_duration(pacing, format)
    key = str(pacing or "").strip().lower()
    if key == "fast":
        factors = [1.0 + 0.5 * (1 - i / max(1, count - 1)) for i in range(count)]
    elif key == "slow":
        factors = [1.15 - 0.15 * (i / max(1, count - 1)) for i in range(count)]
    else:
        factors = [1.1 - 0.2 * (i / max(1, count - 1)) for i in range(count)]
    return [clamp_duration(base * f) for f in factors]
