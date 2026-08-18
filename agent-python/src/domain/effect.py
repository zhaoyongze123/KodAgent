"""Durable records for external side effects."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


EffectStatus = Literal[
    "PLANNED",
    "CLAIMED",
    "EXECUTING",
    "SUCCEEDED",
    "FAILED_RETRYABLE",
    "FAILED_FINAL",
    "UNKNOWN",
    "RECONCILING",
    "CANCELLED",
]

EFFECT_TRANSITIONS: dict[str, frozenset[str]] = {
    "PLANNED": frozenset({"CLAIMED", "CANCELLED"}),
    "CLAIMED": frozenset({"EXECUTING", "FAILED_RETRYABLE", "UNKNOWN", "CANCELLED"}),
    "EXECUTING": frozenset({
        "SUCCEEDED", "FAILED_RETRYABLE", "FAILED_FINAL", "UNKNOWN", "CANCELLED",
    }),
    "FAILED_RETRYABLE": frozenset({"CLAIMED", "CANCELLED"}),
    "UNKNOWN": frozenset({"RECONCILING", "FAILED_FINAL", "SUCCEEDED", "CANCELLED"}),
    "RECONCILING": frozenset({"SUCCEEDED", "FAILED_FINAL", "UNKNOWN"}),
    "SUCCEEDED": frozenset(),
    "FAILED_FINAL": frozenset(),
    "CANCELLED": frozenset(),
}


class EffectTransitionError(ValueError):
    """Raised when an Effect cannot move to the requested state."""


class EffectRecord(BaseModel):
    """One idempotent attempt at an external side effect."""

    model_config = ConfigDict(extra="forbid")

    effect_id: str = Field(default_factory=lambda: f"effect-{uuid4().hex[:20]}", min_length=1, max_length=128)
    operation_id: str = Field(min_length=1, max_length=128)
    action_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=256)
    request_hash: str = Field(min_length=1, max_length=128)
    status: EffectStatus = "PLANNED"
    attempt: int = Field(default=0, ge=0)
    lease_owner: str | None = Field(default=None, max_length=128)
    lease_until: datetime | None = None
    reconcile_strategy: str = Field(min_length=1, max_length=128)
    request_data: dict[str, Any] = Field(default_factory=dict)
    response_data: dict[str, Any] = Field(default_factory=dict)
    error_data: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def transition_effect(
    effect: EffectRecord,
    target: EffectStatus,
    *,
    expected_version: int | None = None,
    now: datetime | None = None,
) -> EffectRecord:
    """Return a new Effect version after validating its state transition."""

    if expected_version is not None and effect.version != expected_version:
        raise EffectTransitionError(
            f"Effect {effect.effect_id} version conflict: "
            f"expected={expected_version}, actual={effect.version}"
        )
    if target not in EFFECT_TRANSITIONS.get(effect.status, frozenset()):
        raise EffectTransitionError(f"Invalid Effect transition: {effect.status} -> {target}")
    timestamp = now or datetime.now(timezone.utc)
    updates: dict[str, Any] = {
        "status": target,
        "version": effect.version + 1,
        "updated_at": timestamp,
    }
    # A worker lease is only meaningful while the side effect is actively
    # owned.  Keeping it on UNKNOWN/terminal rows makes stale workers look
    # authoritative and prevents the reconciler from claiming responsibility.
    if target in {"FAILED_RETRYABLE", "FAILED_FINAL", "UNKNOWN", "RECONCILING", "SUCCEEDED", "CANCELLED"}:
        updates.update({"lease_owner": None, "lease_until": None})
    return effect.model_copy(update=updates)


__all__ = [
    "EFFECT_TRANSITIONS",
    "EffectRecord",
    "EffectStatus",
    "EffectTransitionError",
    "transition_effect",
]
