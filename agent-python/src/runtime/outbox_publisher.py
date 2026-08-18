"""Publisher for Python-owned runtime facts.

The publisher is deliberately a separate process boundary.  Agent workers only
append facts to PostgreSQL; they do not keep a process-local retry database or
hold a network call open while changing an Operation aggregate.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Protocol
from uuid import uuid4

from ..domain.events import RuntimeOutboxRecord
from ..persistence.operation_store import OperationStore
from ..tools.common.http_client import java_post


class RuntimeOutboxStore(Protocol):
    """Small store surface needed by the worker and its tests."""

    def claim_outbox(self, **kwargs) -> list[RuntimeOutboxRecord]: ...

    def mark_outbox_published(self, event_id: str, *, lease_owner: str, now: datetime | None = None) -> bool: ...

    def mark_outbox_failed(
        self,
        event_id: str,
        *,
        lease_owner: str,
        error: str,
        next_attempt_at: datetime,
        max_attempts: int = 10,
        now: datetime | None = None,
    ) -> bool: ...


@dataclass(frozen=True)
class PublishBatchResult:
    claimed: int
    published: int
    failed: int


def runtime_event_to_java_payload(record: RuntimeOutboxRecord) -> dict:
    """Translate the internal snake_case envelope to the Java Run contract."""

    payload = record.payload
    required = {
        "event_id": payload.get("event_id"),
        "run_id": payload.get("run_id"),
        "thread_id": payload.get("thread_id"),
        "tenant_id": payload.get("tenant_id"),
        "user_id": payload.get("user_id"),
        "event_type": payload.get("event_type"),
        "occurred_at": payload.get("occurred_at"),
    }
    missing = [key for key, value in required.items() if value in (None, "")]
    if missing:
        raise ValueError(f"runtime event is missing transport fields: {', '.join(missing)}")

    data = dict(payload.get("data") or {})
    data.setdefault("_runtime", {
        "source": payload.get("source"),
        "schemaVersion": payload.get("schema_version", 1),
        "aggregateType": payload.get("aggregate_type"),
        "aggregateId": payload.get("aggregate_id"),
        "aggregateVersion": payload.get("aggregate_version"),
        "operationId": payload.get("operation_id"),
        "correlationId": payload.get("correlation_id"),
        "causationId": payload.get("causation_id"),
    })
    return {
        "eventId": str(required["event_id"]),
        "runId": str(required["run_id"]),
        "threadId": str(required["thread_id"]),
        "messageId": payload.get("message_id"),
        "tenantId": str(required["tenant_id"]),
        "userId": str(required["user_id"]),
        "type": str(required["event_type"]),
        "schemaVersion": int(payload.get("schema_version", 1)),
        "timestamp": str(required["occurred_at"]),
        "data": data,
    }


def publish_runtime_event(record: RuntimeOutboxRecord) -> dict:
    """Publish one claimed runtime fact through the authenticated Java Facade."""

    event = runtime_event_to_java_payload(record)
    response = java_post(
        f"/agent/runs/{event['runId']}/events",
        event,
        identity=(event["userId"], event["tenantId"]),
    )
    return response


class RuntimeOutboxPublisher:
    """Claim, publish and acknowledge runtime facts with lease ownership."""

    def __init__(
        self,
        store: RuntimeOutboxStore,
        *,
        sink: Callable[[RuntimeOutboxRecord], object] = publish_runtime_event,
        worker_id: str | None = None,
        batch_size: int = 50,
        lease_seconds: int = 30,
        max_attempts: int = 10,
        retry_base_seconds: float = 2.0,
        retry_max_seconds: float = 300.0,
    ) -> None:
        self.store = store
        self.sink = sink
        self.worker_id = (worker_id or f"runtime-outbox-{uuid4().hex}")[:128]
        self.batch_size = max(1, int(batch_size))
        self.lease_seconds = max(1, int(lease_seconds))
        self.max_attempts = max(1, int(max_attempts))
        self.retry_base_seconds = max(0.1, float(retry_base_seconds))
        self.retry_max_seconds = max(self.retry_base_seconds, float(retry_max_seconds))

    def publish_once(self, *, now: datetime | None = None) -> PublishBatchResult:
        timestamp = now or datetime.now(timezone.utc)
        lease_until = timestamp + timedelta(seconds=self.lease_seconds)
        records = self.store.claim_outbox(
            lease_owner=self.worker_id,
            lease_until=lease_until,
            limit=self.batch_size,
            max_attempts=self.max_attempts,
            now=timestamp,
        )
        published = 0
        failed = 0
        for record in records:
            try:
                self.sink(record)
                if self.store.mark_outbox_published(
                    record.event_id,
                    lease_owner=self.worker_id,
                    now=timestamp,
                ):
                    published += 1
            except Exception as exc:
                failed += 1
                delay = min(
                    self.retry_max_seconds,
                    self.retry_base_seconds * (2 ** max(0, record.attempts - 1)),
                )
                self.store.mark_outbox_failed(
                    record.event_id,
                    lease_owner=self.worker_id,
                    error=f"{type(exc).__name__}: {str(exc)[:900]}",
                    next_attempt_at=timestamp + timedelta(seconds=delay),
                    max_attempts=self.max_attempts,
                    now=timestamp,
                )
        return PublishBatchResult(len(records), published, failed)

    def run_forever(self, *, stop_event: threading.Event | None = None) -> None:
        poll_seconds = max(0.1, float(os.getenv("OA_AGENT_RUNTIME_OUTBOX_POLL_SECONDS", "2")))
        event = stop_event or threading.Event()
        while not event.is_set():
            self.publish_once()
            event.wait(poll_seconds)


__all__ = [
    "PublishBatchResult",
    "RuntimeOutboxPublisher",
    "RuntimeOutboxStore",
    "publish_runtime_event",
    "runtime_event_to_java_payload",
]
