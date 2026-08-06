from __future__ import annotations

from datetime import datetime, timezone

from src.domain.events import RuntimeOutboxRecord
from src.runtime.outbox_publisher import (
    RuntimeOutboxPublisher,
    runtime_event_to_java_payload,
)


def _record(*, attempts: int = 1) -> RuntimeOutboxRecord:
    return RuntimeOutboxRecord(
        event_id="event-runtime-1",
        source="python-runtime",
        aggregate_type="operation",
        aggregate_id="op-1",
        aggregate_version=2,
        attempts=attempts,
        payload={
            "event_id": "event-runtime-1",
            "source": "python-runtime",
            "event_type": "operation.ready",
            "schema_version": 1,
            "aggregate_type": "operation",
            "aggregate_id": "op-1",
            "aggregate_version": 2,
            "tenant_id": "tenant-1",
            "user_id": "user-1",
            "thread_id": "thread-1",
            "message_id": "message-1",
            "operation_id": "op-1",
            "run_id": "run-1",
            "correlation_id": "run-1",
            "occurred_at": "2026-08-05T12:00:00Z",
            "data": {"toStatus": "READY"},
        },
    )


class FakeStore:
    def __init__(self, records):
        self.records = records
        self.published = []
        self.failed = []

    def claim_outbox(self, **kwargs):
        return self.records

    def mark_outbox_published(self, event_id, *, lease_owner, now=None):
        self.published.append((event_id, lease_owner))
        return True

    def mark_outbox_failed(self, event_id, *, lease_owner, error, next_attempt_at, max_attempts=10, now=None):
        self.failed.append((event_id, lease_owner, error, next_attempt_at, max_attempts))
        return True


def test_runtime_event_is_translated_to_java_run_contract():
    payload = runtime_event_to_java_payload(_record())

    assert payload["eventId"] == "event-runtime-1"
    assert payload["type"] == "operation.ready"
    assert payload["runId"] == "run-1"
    assert payload["threadId"] == "thread-1"
    assert payload["userId"] == "user-1"
    assert payload["data"]["toStatus"] == "READY"
    assert payload["data"]["_runtime"]["aggregateVersion"] == 2


def test_publisher_acknowledges_only_after_sink_succeeds():
    record = _record()
    store = FakeStore([record])
    seen = []
    publisher = RuntimeOutboxPublisher(store, sink=lambda item: seen.append(item.event_id), worker_id="worker-1")

    result = publisher.publish_once(now=datetime(2026, 8, 5, tzinfo=timezone.utc))

    assert result.claimed == 1
    assert result.published == 1
    assert result.failed == 0
    assert seen == ["event-runtime-1"]
    assert store.published == [("event-runtime-1", "worker-1")]
    assert store.failed == []


def test_publisher_releases_failed_claim_with_backoff():
    record = _record(attempts=3)
    store = FakeStore([record])
    publisher = RuntimeOutboxPublisher(
        store,
        sink=lambda _: (_ for _ in ()).throw(RuntimeError("Java unavailable")),
        worker_id="worker-2",
        retry_base_seconds=2,
    )

    result = publisher.publish_once(now=datetime(2026, 8, 5, tzinfo=timezone.utc))

    assert result.claimed == 1
    assert result.published == 0
    assert result.failed == 1
    assert store.published == []
    assert store.failed[0][0:2] == ("event-runtime-1", "worker-2")
    assert store.failed[0][3].isoformat() == "2026-08-05T00:00:08+00:00"
