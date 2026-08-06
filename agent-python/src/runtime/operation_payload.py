"""Small access layer for facts that belong to the current Operation.

The old implementation exposed a thread-wide mutable task map.  This module
keeps workflow code independent from repository details while making the
Operation aggregate the only durable source for request facts.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator
from typing import Any

from ..domain.operation import OperationContext
from ..tools.common.events import current_agent_context
from .operation_runtime import OperationRuntime, get_active_operation


def _operation_id() -> str:
    return str(current_agent_context().get("operationId") or "").strip()


@contextmanager
def current_operation(*, required: bool = True) -> Iterator[OperationRuntime | None]:
    """Yield the active Operation runtime and close only runtimes opened here."""
    active = get_active_operation()
    if active is not None:
        yield active
        return
    operation_id = _operation_id()
    if not operation_id:
        if required:
            raise RuntimeError("当前请求缺少 Operation 绑定")
        yield None
        return
    runtime = OperationRuntime.open_existing(operation_id, required=required)
    if runtime is None:
        if required:
            raise RuntimeError("当前请求缺少可用的 Operation Runtime")
        yield None
        return
    try:
        yield runtime
    finally:
        runtime.close()


def operation_snapshot(*, required: bool = False) -> OperationContext | None:
    with current_operation(required=required) as runtime:
        return runtime.operation if runtime is not None else None


def operation_payload(*, required: bool = False) -> dict[str, Any]:
    operation = operation_snapshot(required=required)
    return dict(operation.payload) if operation is not None else {}


def merge_operation_payload(
    patch: dict[str, Any],
    *,
    required: bool = True,
    event_type: str = "operation.payload.updated",
) -> OperationContext | None:
    with current_operation(required=required) as runtime:
        if runtime is None:
            return None
        return runtime.merge_payload(patch, event_type=event_type)


__all__ = [
    "current_operation",
    "merge_operation_payload",
    "operation_payload",
    "operation_snapshot",
]
