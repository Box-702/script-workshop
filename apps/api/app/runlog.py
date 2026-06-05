"""Structured logging helpers for pipeline runs.

`log_event` writes a single-line JSON record that includes the run_id,
stage, level, message, and any extra context. Combined with the default
text logger output this gives operators both human-readable logs and
machine-parseable events for dashboards / debugging.

Events are emitted on the `scriptforge.runs` logger; the default formatter
in `app.main` can be replaced with a JSON formatter if downstream tooling
prefers to consume the whole stream uniformly.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

_RUN_LOGGER_NAME = "scriptforge.runs"
_run_logger = logging.getLogger(_RUN_LOGGER_NAME)

# Emit structured events at INFO by default; set SCRIPTFORGE_RUNS_DEBUG=1
# to see DEBUG entries (rare — used only when a developer opts in).
_LEVEL = logging.DEBUG if os.environ.get("SCRIPTFORGE_RUNS_DEBUG") else logging.INFO
if not _run_logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(_LEVEL)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _run_logger.addHandler(handler)
_run_logger.setLevel(_LEVEL)
_run_logger.propagate = False


def log_event(
    run_id: str,
    stage: str,
    message: str,
    *,
    level: int = logging.INFO,
    duration_ms: int | None = None,
    error: str | None = None,
    **extra: Any,
) -> None:
    """Emit a structured JSON line tagged with run_id and stage."""
    payload: dict[str, Any] = {
        "ts": round(time.time() * 1000),
        "run_id": run_id,
        "stage": stage,
        "message": message,
    }
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if error is not None:
        payload["error"] = error
    payload.update(extra)
    _run_logger.log(level, json.dumps(payload, ensure_ascii=False))


class StageTimer:
    """Context manager that logs a structured event with elapsed time."""

    def __init__(self, run_id: str, stage: str, *, level: int = logging.INFO) -> None:
        self.run_id = run_id
        self.stage = stage
        self.level = level
        self._start: float = 0.0

    def __enter__(self) -> "StageTimer":
        self._start = time.perf_counter()
        log_event(self.run_id, self.stage, "stage_started", level=self.level)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        elapsed_ms = int((time.perf_counter() - self._start) * 1000)
        if exc is None:
            log_event(
                self.run_id,
                self.stage,
                "stage_finished",
                level=self.level,
                duration_ms=elapsed_ms,
            )
        else:
            log_event(
                self.run_id,
                self.stage,
                "stage_failed",
                level=logging.ERROR,
                duration_ms=elapsed_ms,
                error=f"{exc_type.__name__}: {exc}",
            )
