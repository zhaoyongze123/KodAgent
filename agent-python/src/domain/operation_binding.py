"""Domain-neutral outer contract for durable Agent operations.

The envelope is intentionally small. Domain services keep their own draft
payload and transaction tables; this contract only standardizes identity,
state, expiry and idempotency across workflows and ApprovalCards.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


OperationStatus = Literal["PENDING", "SUBMITTING", "COMPLETED", "CANCELLED", "EXPIRED", "FAILED"]


class OperationBinding(BaseModel):
    operation_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=64)
    operation: str = Field(min_length=1, max_length=64)
    status: OperationStatus
    tenant_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    run_id: str = Field(min_length=1, max_length=128)
    thread_id: str = Field(min_length=1, max_length=128)
    message_id: str = Field(min_length=1, max_length=128)
    idempotency_key: str = Field(min_length=1, max_length=128)
    expires_at: datetime | None = None


class OperationDraftEnvelope(BaseModel):
    binding: OperationBinding
    payload: dict[str, Any] = Field(default_factory=dict)
    fields: list[dict[str, str]] = Field(default_factory=list)
    allowed_actions: list[Literal["approve", "reject"]] = Field(default_factory=lambda: ["approve", "reject"])
    card_type: str = "approval"


__all__ = ["OperationBinding", "OperationDraftEnvelope", "OperationStatus"]
