"""Run-local metadata for comparing routing decisions and prompt versions."""

from __future__ import annotations

from contextvars import ContextVar
from threading import Lock
from typing import Any


_MODEL_TRACE: ContextVar[dict[str, Any]] = ContextVar(
    "kodagent_model_trace", default={}
)
_MODEL_TRACE_BY_RUN: dict[str, dict[str, Any]] = {}
_MODEL_TRACE_LOCK = Lock()
_MAX_RUN_TRACES = 512


def set_model_trace(*, run_id: str | None = None, **values: Any) -> None:
    current = dict(_MODEL_TRACE.get() or {})
    current.update({key: value for key, value in values.items() if value not in (None, "")})
    _MODEL_TRACE.set(current)
    if run_id and run_id != "local-run":
        with _MODEL_TRACE_LOCK:
            _MODEL_TRACE_BY_RUN[run_id] = current
            while len(_MODEL_TRACE_BY_RUN) > _MAX_RUN_TRACES:
                _MODEL_TRACE_BY_RUN.pop(next(iter(_MODEL_TRACE_BY_RUN)))


def current_model_trace(run_id: str | None = None) -> dict[str, Any]:
    if run_id and run_id != "local-run":
        with _MODEL_TRACE_LOCK:
            return dict(_MODEL_TRACE_BY_RUN.get(run_id) or _MODEL_TRACE.get() or {})
    return dict(_MODEL_TRACE.get() or {})


__all__ = ["current_model_trace", "set_model_trace"]
