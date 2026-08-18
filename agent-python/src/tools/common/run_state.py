"""Short-lived cross-worker run coordination.

LangGraph Checkpoint remains the durable source of execution, interrupt and
resume state.  This module only stores two ephemeral coordination facts that
must be shared when a request is handled by different workers: a pause hint
used by lifecycle event classification and the one-time plan event claim.
Redis is preferred in production; the bounded in-process fallback keeps local
tests and a developer checkout usable when Redis is intentionally absent.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from redis import Redis


_REDIS: Redis | None = None
_LOCAL_LOCK = threading.Lock()
_LOCAL_PAUSED: dict[str, float] = {}
_LOCAL_PLAN_CLAIMS: dict[str, float] = {}
_TTL_SECONDS = max(60, int(os.getenv("OA_AGENT_RUN_STATE_TTL_SECONDS", "86400")))


def _redis() -> Redis:
    global _REDIS
    if _REDIS is None:
        _REDIS = Redis.from_url(
            os.getenv("OA_AGENT_REDIS_URL", "redis://127.0.0.1:16379/0"),
            decode_responses=True,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _REDIS


def _key(kind: str, run_id: str, scope: str = "global") -> str:
    return f"kodagent:run-state:{kind}:{scope}:{run_id}"


def _prune(now: float) -> None:
    cutoff = now - _TTL_SECONDS
    for mapping in (_LOCAL_PAUSED, _LOCAL_PLAN_CLAIMS):
        for key, started in list(mapping.items()):
            if started < cutoff:
                mapping.pop(key, None)


def _local_key(run_id: str, scope: str) -> str:
    return f"{scope}:{run_id}"


def _redis_set(run_id: str, kind: str, *, scope: str = "global", nx: bool = False) -> bool | None:
    try:
        result = _redis().set(_key(kind, run_id, scope), "1", ex=_TTL_SECONDS, nx=nx)
        return bool(result) if nx else True
    except Exception:
        return None


def _redis_exists(run_id: str, kind: str, *, scope: str = "global") -> bool | None:
    try:
        return bool(_redis().exists(_key(kind, run_id, scope)))
    except Exception:
        return None


def _redis_delete(run_id: str, kind: str, *, scope: str = "global") -> bool | None:
    try:
        _redis().delete(_key(kind, run_id, scope))
        return True
    except Exception:
        return None


def mark_paused(run_id: str, *, scope: str = "global") -> None:
    """Record an ephemeral pause hint; Checkpoint remains authoritative."""
    run_id = str(run_id or "local-run")
    local_key = _local_key(run_id, scope)
    if _redis_set(run_id, "paused", scope=scope) is not None:
        return
    now = time.monotonic()
    with _LOCAL_LOCK:
        _prune(now)
        _LOCAL_PAUSED[local_key] = now


def clear_paused(run_id: str, *, scope: str = "global") -> None:
    run_id = str(run_id or "local-run")
    local_key = _local_key(run_id, scope)
    if _redis_delete(run_id, "paused", scope=scope) is not None:
        return
    with _LOCAL_LOCK:
        _LOCAL_PAUSED.pop(local_key, None)


def is_paused(run_id: str, *, scope: str = "global") -> bool:
    run_id = str(run_id or "local-run")
    local_key = _local_key(run_id, scope)
    remote = _redis_exists(run_id, "paused", scope=scope)
    if remote is not None:
        return remote
    now = time.monotonic()
    with _LOCAL_LOCK:
        _prune(now)
        return local_key in _LOCAL_PAUSED


def claim_plan(run_id: str, *, scope: str = "global") -> bool:
    """Atomically claim the single ``plan.created`` event for a Run."""
    run_id = str(run_id or "local-run")
    local_key = _local_key(run_id, scope)
    remote = _redis_set(run_id, "plan", scope=scope, nx=True)
    if remote is not None:
        return remote
    now = time.monotonic()
    with _LOCAL_LOCK:
        _prune(now)
        if local_key in _LOCAL_PLAN_CLAIMS:
            return False
        _LOCAL_PLAN_CLAIMS[local_key] = now
        return True


__all__ = ["claim_plan", "clear_paused", "is_paused", "mark_paused"]
