"""Versioned durable event envelope for runtime facts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    """An immutable observation, not a UI narration or model response."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: f"event-{uuid4().hex[:20]}", min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=128)
    schema_version: int = Field(default=1, ge=1)
    aggregate_type: str = Field(min_length=1, max_length=64)
    aggregate_id: str = Field(min_length=1, max_length=128)
    aggregate_version: int = Field(ge=1)
    tenant_id: str = Field(min_length=1, max_length=64)
    user_id: str | None = Field(default=None, max_length=64)
    thread_id: str | None = Field(default=None, max_length=128)
    message_id: str | None = Field(default=None, max_length=128)
    operation_id: str | None = Field(default=None, max_length=128)
    run_id: str | None = Field(default=None, max_length=128)
    correlation_id: str = Field(min_length=1, max_length=128)
    causation_id: str | None = Field(default=None, max_length=128)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)


class RuntimeOutboxRecord(BaseModel):
    """A claimed delivery row for a Python runtime fact."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=64)
    aggregate_type: str = Field(min_length=1, max_length=64)
    aggregate_id: str = Field(min_length=1, max_length=128)
    aggregate_version: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    attempts: int = Field(default=0, ge=0)
    lease_owner: str | None = Field(default=None, max_length=128)
    lease_until: datetime | None = None
    next_attempt_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    published_at: datetime | None = None
    dead_lettered_at: datetime | None = None
    last_error: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = ["EventEnvelope", "RuntimeOutboxRecord"]
