"""Durable Agent operation aggregate and its state transition rules.

An operation is the long-lived unit of business work.  A Thread and a Run are
only correlation scopes: an operation may span multiple Runs and resumes, and
one Thread may contain multiple concurrent operations.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


OperationStatus = Literal[
    "CREATED",
    "COLLECTING_INFO",
    "READY",
    "RUNNING",
    "WAITING_APPROVAL",
    "COMMITTING",
    "SUCCEEDED",
    "FAILED",
    "CANCELLED",
    "EXPIRED",
    "UNKNOWN",
]

TERMINAL_OPERATION_STATUSES = frozenset({
    "SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED",
})

OPERATION_TRANSITIONS: dict[str, frozenset[str]] = {
    "CREATED": frozenset({"COLLECTING_INFO", "READY", "FAILED", "CANCELLED", "EXPIRED"}),
    "COLLECTING_INFO": frozenset({"READY", "FAILED", "CANCELLED", "EXPIRED"}),
    "READY": frozenset({"RUNNING", "FAILED", "CANCELLED", "EXPIRED"}),
    "RUNNING": frozenset({
        "READY", "WAITING_APPROVAL", "COMMITTING", "SUCCEEDED", "FAILED",
        "CANCELLED", "UNKNOWN",
    }),
    "WAITING_APPROVAL": frozenset({"COMMITTING", "CANCELLED", "EXPIRED"}),
    "COMMITTING": frozenset({"SUCCEEDED", "FAILED", "UNKNOWN"}),
    "UNKNOWN": frozenset({"RUNNING", "COMMITTING", "SUCCEEDED", "FAILED", "CANCELLED"}),
    "SUCCEEDED": frozenset(),
    "FAILED": frozenset(),
    "CANCELLED": frozenset(),
    "EXPIRED": frozenset(),
}


class OperationTransitionError(ValueError):
    """Raised when an operation version or state transition is invalid."""


class OperationContext(BaseModel):
    """Versioned orchestration state; domain payloads remain typed by Action."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(default_factory=lambda: f"op-{uuid4().hex[:20]}", min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=64)
    tenant_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    thread_id: str = Field(min_length=1, max_length=128)
    origin_run_id: str = Field(min_length=1, max_length=128)
    current_run_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    status: OperationStatus = "CREATED"
    version: int = Field(default=1, ge=1)
    payload_schema_version: int = Field(default=1, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)
    plan_id: str | None = Field(default=None, max_length=128)
    plan_revision: int | None = Field(default=None, ge=1)
    approval_id: str | None = Field(default=None, max_length=128)
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def transition_operation(
    operation: OperationContext,
    target: OperationStatus,
    *,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> OperationContext:
    """Return a new operation version after validating its state transition."""

    if expected_version is not None and operation.version != expected_version:
        raise OperationTransitionError(
            f"Operation {operation.operation_id} version conflict: "
            f"expected={expected_version}, actual={operation.version}"
        )
    if target not in OPERATION_TRANSITIONS.get(operation.status, frozenset()):
        raise OperationTransitionError(
            f"Invalid Operation transition: {operation.status} -> {target}"
        )
    timestamp = now or datetime.now(timezone.utc)
    return operation.model_copy(update={
        "status": target,
        "version": operation.version + 1,
        "updated_at": timestamp,
    })


def bind_approval(
    operation: OperationContext,
    approval_id: str,
    *,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> OperationContext:
    """Bind a Java-owned approval without changing the operation status."""

    if expected_version is not None and operation.version != expected_version:
        raise OperationTransitionError(
            f"Operation {operation.operation_id} version conflict: "
            f"expected={expected_version}, actual={operation.version}"
        )
    if not approval_id.strip():
        raise ValueError("approval_id cannot be blank")
    timestamp = now or datetime.now(timezone.utc)
    return operation.model_copy(update={
        "approval_id": approval_id,
        "version": operation.version + 1,
        "updated_at": timestamp,
    })


def patch_operation(
    operation: OperationContext,
    *,
    expected_version: int | None = None,
    current_run_id: str | None = None,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    approval_id: str | None = None,
    now: datetime | None = None,
) -> OperationContext:
    """Return a new revision for non-state operation metadata.

    Status changes remain the responsibility of ``transition_operation``.
    Keeping payload/result updates separate prevents a caller from silently
    changing the lifecycle while persisting a tool response.
    """

    if expected_version is not None and operation.version != expected_version:
        raise OperationTransitionError(
            f"Operation {operation.operation_id} version conflict: "
            f"expected={expected_version}, actual={operation.version}"
        )
    if current_run_id is not None and not current_run_id.strip():
        raise ValueError("current_run_id cannot be blank")
    if approval_id is not None and not approval_id.strip():
        raise ValueError("approval_id cannot be blank")
    timestamp = now or datetime.now(timezone.utc)
    updates: dict[str, Any] = {
        "version": operation.version + 1,
        "updated_at": timestamp,
    }
    if current_run_id is not None:
        updates["current_run_id"] = current_run_id
    if payload is not None:
        updates["payload"] = payload
    if result is not None:
        updates["result"] = result
    if approval_id is not None:
        updates["approval_id"] = approval_id
    return operation.model_copy(update=updates)


__all__ = [
    "OPERATION_TRANSITIONS",
    "OperationContext",
    "OperationStatus",
    "OperationTransitionError",
    "TERMINAL_OPERATION_STATUSES",
    "bind_approval",
    "patch_operation",
    "transition_operation",
]
