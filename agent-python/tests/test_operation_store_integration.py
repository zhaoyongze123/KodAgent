"""Opt-in integration checks for the PostgreSQL runtime store.

These tests intentionally require ``OA_AGENT_RUNTIME_TEST_DSN`` so a normal
unit-test run cannot mutate a developer or production database by accident.
Run them explicitly against the local migration with:

    OA_AGENT_RUNTIME_TEST_DSN=postgresql://langgraph:langgraph@127.0.0.1:15432/langgraph \
      .venv/bin/pytest -q tests/test_operation_store_integration.py
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from psycopg import connect

from src.domain.effect import EffectRecord
from src.domain.events import EventEnvelope
from src.domain.operation import OperationContext, OperationTransitionError
from src.persistence.operation_store import OperationStore


TEST_DSN = os.getenv("OA_AGENT_RUNTIME_TEST_DSN")

pytestmark = pytest.mark.skipif(
    not TEST_DSN,
    reason="需要显式设置 OA_AGENT_RUNTIME_TEST_DSN 才运行 PostgreSQL 集成测试",
)


def make_operation(operation_id: str) -> OperationContext:
    return OperationContext(
        operation_id=operation_id,
        action_id="meeting.book",
        capability_id="meeting",
        tenant_id="integration-tenant",
        user_id="integration-user",
        thread_id=f"thread-{uuid4().hex}",
        origin_run_id=f"run-{uuid4().hex}",
        current_run_id=f"run-{uuid4().hex}",
        message_id=f"message-{uuid4().hex}",
        payload={"subject": "repository integration"},
    )


def test_postgres_store_enforces_versions_idempotency_and_claims():
    operation_id = f"op-integration-{uuid4().hex}"
    effect_id = f"effect-integration-{uuid4().hex}"
    idempotency_key = f"meeting-book-{uuid4().hex}"
    event_ids: list[str] = []
    store = OperationStore(TEST_DSN)

    try:
        created = store.create_operation(make_operation(operation_id))
        transition_event = EventEnvelope(
            source="python-runtime",
            event_type="operation.ready",
            aggregate_type="operation",
            aggregate_id=operation_id,
            aggregate_version=2,
            tenant_id="integration-tenant",
            operation_id=operation_id,
            correlation_id=operation_id,
            data={"toStatus": "READY"},
        )
        event_ids.append(transition_event.event_id)
        ready = store.transition_operation(
            operation_id,
            "READY",
            expected_version=created.version,
            event=transition_event,
        )
        assert ready.version == 2
        assert ready.status == "READY"

        # A new transport id must not create a second fact for the same
        # aggregate revision and event type.
        store.append_event(
            transition_event.model_copy(update={"event_id": f"event-replay-{uuid4().hex}"})
        )
        with connect(TEST_DSN) as connection:
            assert connection.execute(
                """
                SELECT COUNT(*) FROM agent_runtime.outbox
                WHERE source = %s AND aggregate_type = %s
                  AND aggregate_id = %s AND aggregate_version = %s
                  AND payload ->> 'event_type' = %s
                """,
                (
                    transition_event.source,
                    transition_event.aggregate_type,
                    operation_id,
                    transition_event.aggregate_version,
                    transition_event.event_type,
                ),
            ).fetchone()[0] == 1

        with connect(TEST_DSN) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM agent_runtime.outbox WHERE event_id = %s",
                (transition_event.event_id,),
            ).fetchone()[0] == 1

        with pytest.raises(OperationTransitionError, match="version conflict"):
            store.transition_operation(operation_id, "RUNNING", expected_version=1)

        effect = EffectRecord(
            effect_id=effect_id,
            operation_id=operation_id,
            action_id="meeting.book",
            idempotency_key=idempotency_key,
            request_hash="request-hash-v1",
            reconcile_strategy="meeting.booking.lookup",
            request_data={"draftId": "draft-1"},
        )
        effect_event = EventEnvelope(
            source="python-runtime",
            event_type="effect.planned",
            aggregate_type="effect",
            aggregate_id=effect_id,
            aggregate_version=1,
            tenant_id="integration-tenant",
            operation_id=operation_id,
            correlation_id=operation_id,
            data={"effectId": effect_id},
        )
        event_ids.append(effect_event.event_id)
        first = store.create_effect(effect, event=effect_event)
        replay = store.create_effect(
            effect.model_copy(update={"effect_id": f"effect-replay-{uuid4().hex}"})
        )
        assert replay.effect_id == first.effect_id

        with pytest.raises(ValueError, match="请求摘要不同"):
            store.create_effect(
                effect.model_copy(
                    update={
                        "effect_id": f"effect-conflict-{uuid4().hex}",
                        "request_hash": "request-hash-v2",
                    }
                )
            )

        claim_event = EventEnvelope(
            source="python-runtime",
            event_type="effect.claimed",
            aggregate_type="effect",
            aggregate_id=effect_id,
            aggregate_version=2,
            tenant_id="integration-tenant",
            operation_id=operation_id,
            correlation_id=operation_id,
            data={"effectId": effect_id, "attempt": 1},
        )
        event_ids.append(claim_event.event_id)
        claimed = store.claim_effect(
            first.effect_id,
            lease_owner="integration-worker",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
            expected_version=first.version,
            event=claim_event,
        )
        assert claimed.status == "CLAIMED"
        assert claimed.attempt == 1
        assert claimed.lease_owner == "integration-worker"

        executing = store.transition_effect(
            claimed.effect_id,
            "EXECUTING",
            expected_version=claimed.version,
        )
        failed = store.transition_effect(
            executing.effect_id,
            "FAILED_FINAL",
            expected_version=executing.version,
            error_data={"code": "TEST_FINAL"},
        )
        assert failed.lease_owner is None
        assert failed.lease_until is None

        operation_claim = store.claim_outbox(
            lease_owner="worker-a",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
            aggregate_id=operation_id,
            max_attempts=2,
        )
        assert len(operation_claim) == 1
        assert operation_claim[0].event_id == transition_event.event_id
        assert operation_claim[0].attempts == 1
        assert store.renew_outbox_lease(
            operation_claim[0].event_id,
            lease_owner="worker-a",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=2),
        ) is True
        assert store.mark_outbox_failed(
            operation_claim[0].event_id,
            lease_owner="worker-a",
            error="temporary publisher outage",
            next_attempt_at=datetime.now(timezone.utc),
            max_attempts=2,
        ) is True

        retry_claim = store.claim_outbox(
            lease_owner="worker-b",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
            aggregate_id=operation_id,
            max_attempts=2,
        )
        assert len(retry_claim) == 1
        assert retry_claim[0].attempts == 2
        assert store.mark_outbox_failed(
            retry_claim[0].event_id,
            lease_owner="worker-b",
            error="publisher still unavailable",
            next_attempt_at=datetime.now(timezone.utc),
            max_attempts=2,
        ) is True
        assert store.claim_outbox(
            lease_owner="worker-c",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
            aggregate_id=operation_id,
            max_attempts=2,
        ) == []

        effect_claim = store.claim_outbox(
            lease_owner="worker-publisher",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
            aggregate_id=effect_id,
        )
        assert len(effect_claim) == 2
        planned_effect = next(item for item in effect_claim if item.event_id == effect_event.event_id)
        assert store.mark_outbox_published(
            planned_effect.event_id,
            lease_owner="worker-publisher",
        ) is True
        assert store.mark_outbox_published(
            planned_effect.event_id,
            lease_owner="stale-worker",
        ) is False
    finally:
        with connect(TEST_DSN) as connection, connection.transaction():
            for event_id in event_ids:
                connection.execute(
                    "DELETE FROM agent_runtime.outbox WHERE event_id = %s",
                    (event_id,),
                )
            connection.execute(
                "DELETE FROM agent_runtime.effect WHERE operation_id = %s",
                (operation_id,),
            )
            connection.execute(
                "DELETE FROM agent_runtime.operation_transition WHERE operation_id = %s",
                (operation_id,),
            )
            connection.execute(
                "DELETE FROM agent_runtime.operation WHERE operation_id = %s",
                (operation_id,),
            )
        store.close()
