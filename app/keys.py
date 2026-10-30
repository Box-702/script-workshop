# =====================================================================
# keys.py —— 同一厂商多把 key 的轮换（「哪把能过用哪把」）
#
# 动机：一把 key 欠费或失效，整条链路（出片 / 配音）一起停摆，得等人手动
# 改 .env 重启。现实里同一个厂商常同时存在多把 key——不同账号、新旧并存、
# 免费额度与付费额度分开算。把这些 key 一起写进配置，运行时按可用性挑一把，
# 坏掉的进「冷却期」，冷却期内不再撞它，避免每次请求都先吃一个 402。
#
# 为什么不是简单的随机/轮询：
#   - 顺序即优先级。先写的先用，符合「我正在用哪把」的心智模型；
#   - 失效要留痕。401（key 无效）/ 402（余额不足）不是偶发错误，重试同一把
#     没有意义，必须冷却；而 400（参数错）/ 429（限流）是请求本身的问题，
#     换 key 也没用，绝不能把 key 判死。
#   - 冷却不是永久。充值后十分钟自动恢复，不需要重启进程。
# =====================================================================

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Iterable

log = logging.getLogger(__name__)

# 判定失效后的冷却时长（秒）。可用 KEY_COOLDOWN_SEC 覆盖。
DEFAULT_COOLDOWN_SEC = 600.0

# MiniMax 的 key 级错误码：1004 鉴权失败、1008 余额不足。
_KEY_ERROR_CODES = ("1004", "1008")
_KEY_ERROR_RE = re.compile(r"\b(?:" + "|".join(_KEY_ERROR_CODES) + r")\b")
_KEY_ERROR_HTTP = (401, 402, 403)


def mask(key: str) -> str:
    """日志里只露头尾，避免整串 key 落盘。"""
    key = (key or "").strip()
    if len(key) <= 10:
        return key[:2] + "***" if key else "(空)"
    return f"{key[:6]}…{key[-4:]}"


def split_keys(raw: str | Iterable[str] | None) -> list[str]:
    """把 "a,b" / "a;b" / "a b" / 换行分隔 / 列表 拆成去重保序的 key 列表。"""
    if raw is None:
        return []
    if isinstance(raw, str):
        parts: Iterable[str] = re.split(r"[,;\s]+", raw)
    else:
        parts = raw
    out: list[str] = []
    seen: set[str] = set()
    for part in parts:
        item = str(part).strip().strip('"').strip("'")
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def merge_keys(*groups: str | Iterable[str] | None) -> list[str]:
    """按给定顺序合并多组 key 并去重（先出现的优先）。"""
    merged: list[str] = []
    for group in groups:
        for key in split_keys(group):
            if key not in merged:
                merged.append(key)
    return merged


def key_failure(status_code: int, payload: object) -> bool:
    """这次失败是否**归因于 key 本身**（该换 key，而不是该改参数）。

    HTTP 401/402/403 直接算；MiniMax 也有 HTTP 200 但 body 里带错误码的情形，
    所以再扫一遍响应体里的 (1004)/(1008)。
    """
    if status_code in _KEY_ERROR_HTTP:
        return True
    try:
        text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(payload)
    return bool(_KEY_ERROR_RE.search(text or ""))


def error_message(payload: object, status_code: int = 0) -> str:
    """从各家响应体里捞出人话错误信息，捞不到就退回 HTTP 状态。"""
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict) and err.get("message"):
            return str(err["message"])
        if isinstance(err, str) and err.strip():
            return err.strip()
        base = payload.get("base_resp")
        if isinstance(base, dict) and base.get("status_msg"):
            return str(base["status_msg"])
    text = payload if isinstance(payload, str) else ""
    return (text.strip()[:200] or f"HTTP {status_code}")


@dataclass
class KeyState:
    """单个 key 的运行时状态。"""

    key: str
    bad_until: float = 0.0
    reason: str = ""
    failures: int = field(default=0)

    def healthy(self, now: float) -> bool:
        return self.bad_until <= now


class KeyRing:
    """一组 key + 冷却状态。线程安全（FastAPI 的同步/异步接口共享）。"""

    def __init__(
        self,
        keys: str | Iterable[str] | None,
        *,
        cooldown: float | None = None,
        label: str = "",
    ) -> None:
        self.label = label
        self.cooldown = DEFAULT_COOLDOWN_SEC if cooldown is None else float(cooldown)
        self._states = [KeyState(k) for k in split_keys(keys)]
        self._lock = threading.Lock()

    def __len__(self) -> int:
        return len(self._states)

    def ordered(self) -> list[str]:
        """配置顺序下的全部 key（不含冷却信息，仅用于比较是否需要重建）。"""
        return [s.key for s in self._states]

    def candidates(self) -> list[str]:
        """候选顺序：健康的按配置顺序在前，冷却中的按恢复时间垫后。

        垫后而不是剔除——全都在冷却里时，赌一把最早恢复的也比直接报错强。
        """
        now = time.time()
        with self._lock:
            healthy = [s.key for s in self._states if s.healthy(now)]
            cooling = sorted(
                (s for s in self._states if not s.healthy(now)),
                key=lambda s: s.bad_until,
            )
        return healthy + [s.key for s in cooling]

    def pick(self) -> str:
        """取当前最该用的一把；一个都没配时返回空串。"""
        got = self.candidates()
        return got[0] if got else ""

    def mark_bad(self, key: str, reason: str = "") -> None:
        now = time.time()
        with self._lock:
            for state in self._states:
                if state.key == key:
                    state.failures += 1
                    state.bad_until = now + self.cooldown
                    state.reason = reason or state.reason
                    break
        log.warning(
            "[%s] key %s 进入冷却 %ds：%s",
            self.label or "provider",
            mask(key),
            int(self.cooldown),
            reason or "未知原因",
        )

    def mark_ok(self, key: str) -> None:
        with self._lock:
            for state in self._states:
                if state.key == key:
                    state.bad_until = 0.0
                    state.reason = ""
                    state.failures = 0
                    break

    def snapshot(self) -> list[dict[str, object]]:
        """诊断用：给前端/日志看每把 key 的状态（不含 key 本体）。"""
        now = time.time()
        with self._lock:
            return [
                {
                    "key": mask(s.key),
                    "healthy": s.healthy(now),
                    "cooldown_left": max(0, int(s.bad_until - now)),
                    "failures": s.failures,
                    "reason": s.reason,
                }
                for s in self._states
            ]


# ---- 进程级 key 环缓存 ----

_RINGS: dict[str, KeyRing] = {}
_RINGS_LOCK = threading.Lock()


def _cooldown_setting() -> float:
    raw = os.environ.get("KEY_COOLDOWN_SEC", "").strip()
    if not raw:
        return DEFAULT_COOLDOWN_SEC
    try:
        return max(0.0, float(raw))
    except ValueError:
        return DEFAULT_COOLDOWN_SEC


def ring_for(name: str, keys: str | Iterable[str] | None, *, cooldown: float | None = None) -> KeyRing:
    """取（或重建）某个厂商的 key 环。

    key 列表变了就重建——运行中改了配置/数据库里的 key 也能立即生效，
    代价只是把冷却状态清零（可接受：配置变了本就该重新试一遍）。
    """
    wanted = split_keys(keys)
    with _RINGS_LOCK:
        ring = _RINGS.get(name)
        if ring is None or ring.ordered() != wanted:
            ring = KeyRing(wanted, cooldown=_cooldown_setting() if cooldown is None else cooldown, label=name)
            _RINGS[name] = ring
        return ring


def reset_rings() -> None:
    """清空所有 key 环（测试用）。"""
    with _RINGS_LOCK:
        _RINGS.clear()


def minimax_keys(primary: str = "") -> list[str]:
    """MiniMax 的候选 key 列表，顺序即优先级。

    来源（依次拼接、去重）：
      1. 调用方显式传入的 key（视频 Provider 由数据库/设置注入的那把）；
      2. ``MINIMAX_API_KEY``——.env 里的主 key；
      3. ``MINIMAX_API_KEYS``——逗号分隔的备用 key 列表；
      4. ``MINIMAX_API_KEY_FALLBACKS``——同上，语义更直白的老写法。
    """
    return merge_keys(
        primary,
        os.environ.get("MINIMAX_API_KEY", ""),
        os.environ.get("MINIMAX_API_KEYS", ""),
        os.environ.get("MINIMAX_API_KEY_FALLBACKS", ""),
    )
