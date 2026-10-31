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
- fast：短镜，靠切碎制造加速度（冲击镜头）。

数值是**起点不是枷锁**：导演可以按时长阶梯（长 → 渐短 → 冲击）在这附近微调，
只要落在生成器的可行区间内。
"""

from __future__ import annotations

# 单镜可行区间：与导演侧校验（4–15 秒）保持一致，改一处就要改两处。
MIN_SHOT_SEC = 4.0
MAX_SHOT_SEC = 15.0

# 各节奏档的基准单镜时长。
RHYTHM_BASE_SEC: dict[str, float] = {
    "slow": 8.0,
    "medium": 6.0,
    "fast": 4.0,
}

# 拿不到 pacing 时的兜底（也是新镜头的默认时长）。
DEFAULT_SHOT_SEC = RHYTHM_BASE_SEC["medium"]


def suggest_duration(pacing: str | None = None) -> float:
    """按本场节奏给一个建议单镜时长；未知/缺省一律按 medium。"""
    key = str(pacing or "").strip().lower()
    return RHYTHM_BASE_SEC.get(key, DEFAULT_SHOT_SEC)


def clamp_duration(sec: float) -> float:
    """把时长夹进生成器可行区间（模型偶尔给出 2 秒、20 秒这类不可执行的值）。"""
    return max(MIN_SHOT_SEC, min(MAX_SHOT_SEC, float(sec)))


def suggest_ladder(pacing: str | None, count: int) -> list[float]:
    """给出一个场景内 ``count`` 个镜头的时长阶梯建议（长 → 渐短 → 收尾）。

    slow 缓降、medium 中速渐短、fast 急剧缩短——最后一镜略回收，避免整场
    越切越碎、观众疲劳。仅作默认建议，导演可逐镜覆盖。
    """
    if count <= 0:
        return []
    base = suggest_duration(pacing)
    key = str(pacing or "").strip().lower()
    if key == "fast":
        factors = [1.0 + 0.5 * (1 - i / max(1, count - 1)) for i in range(count)]
    elif key == "slow":
        factors = [1.15 - 0.15 * (i / max(1, count - 1)) for i in range(count)]
    else:
        factors = [1.1 - 0.2 * (i / max(1, count - 1)) for i in range(count)]
    return [clamp_duration(base * f) for f in factors]
