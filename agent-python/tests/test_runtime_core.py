from datetime import datetime, timezone

import pytest

from src.domain.effect import EffectRecord, EffectTransitionError, transition_effect
from src.domain.events import EventEnvelope
from src.domain.operation import (
    OperationContext,
    OperationTransitionError,
    bind_approval,
    patch_operation,
    transition_operation,
)
from src.runtime.operation_runtime import OperationRuntime
import src.runtime.operation_runtime as operation_runtime_module
from src.tools.common.events import set_event_context


def operation() -> OperationContext:
    return OperationContext(
        action_id="meeting.book",
        capability_id="meeting",
        tenant_id="tenant-1",
        user_id="user-1",
        thread_id="thread-1",
        origin_run_id="run-1",
        current_run_id="run-1",
        message_id="message-1",
        payload={"subject": "review"},
    )


def effect() -> EffectRecord:
    return EffectRecord(
        operation_id="op-1",
        action_id="meeting.book",
        idempotency_key="meeting-book:op-1",
        request_hash="hash-1",
        reconcile_strategy="meeting.booking.lookup",
    )


def test_operation_transition_is_immutable_and_versioned():
    current = operation()
    next_value = transition_operation(
        current, "READY", expected_version=1,
        now=datetime(2026, 8, 5, tzinfo=timezone.utc),
    )

    assert current.status == "CREATED"
    assert next_value.status == "READY"
    assert next_value.version == 2
    assert next_value.updated_at.year == 2026


def test_operation_rejects_invalid_transition_and_stale_version():
    current = operation()
    with pytest.raises(OperationTransitionError, match="Invalid Operation transition"):
        transition_operation(current, "COMMITTING")
    with pytest.raises(OperationTransitionError, match="version conflict"):
        transition_operation(current, "READY", expected_version=9)


def test_operation_approval_binding_is_not_a_status_transition():
    current = operation()
    bound = bind_approval(current, "approval-1", expected_version=1)

    assert bound.approval_id == "approval-1"
    assert bound.status == "CREATED"
    assert bound.version == 2


def test_effect_must_reconcile_unknown_before_success():
    current = effect()
    claimed = transition_effect(current, "CLAIMED")
    executing = transition_effect(claimed, "EXECUTING")
    unknown = transition_effect(executing, "UNKNOWN")
    reconciling = transition_effect(unknown, "RECONCILING")
    succeeded = transition_effect(reconciling, "SUCCEEDED")

    assert succeeded.status == "SUCCEEDED"
    with pytest.raises(EffectTransitionError, match="Invalid Effect transition"):
        transition_effect(unknown, "EXECUTING")


def test_event_envelope_requires_aggregate_revision():
    event = EventEnvelope(
        source="python-runtime",
        event_type="operation.ready",
        aggregate_type="operation",
        aggregate_id="op-1",
        aggregate_version=2,
        tenant_id="tenant-1",
        correlation_id="corr-1",
        operation_id="op-1",
        data={"actionId": "meeting.book"},
    )

    assert event.schema_version == 1
    assert event.aggregate_version == 2


def test_operation_events_keep_correlation_across_resume_runs():
    runtime = OperationRuntime(store=None, operation=operation())

    event = runtime._event("operation.resumed", {"toRunId": "resume-1"})

    assert event.correlation_id == runtime.operation_id
    assert event.run_id != event.correlation_id


def test_open_existing_rejects_operation_from_other_scope(monkeypatch):
    stored = operation().model_copy(update={"operation_id": "op-1"})

    class Store:
        def __init__(self, dsn):
            self.closed = False

        def get_operation(self, operation_id):
            assert operation_id == "op-1"
            return stored

        def close(self):
            self.closed = True

    store_holder = {}

    def build_store(dsn):
        value = Store(dsn)
        store_holder["store"] = value
        return value

    monkeypatch.setattr(operation_runtime_module, "OperationStore", build_store)
    monkeypatch.setenv("OA_AGENT_RUNTIME_POSTGRES_URI", "postgresql://runtime")
    set_event_context(
        "resume-1", "other-thread", tenant_id="tenant-1", user_id="user-1",
        message_id="message-1", origin_run_id="run-1",
    )

    with pytest.raises(PermissionError, match="OPERATION_SCOPE_MISMATCH"):
        OperationRuntime.open_existing("op-1", required=True)

    assert store_holder["store"].closed is True


def test_replayed_result_does_not_create_a_new_operation_revision():
    class Store:
        def __init__(self):
            self.calls = 0

        def patch_operation(self, operation_id, **kwargs):
            self.calls += 1
            return patch_operation(runtime.operation, **kwargs)

    result = {"status": "SUCCEEDED", "effectId": "effect-1", "result": {"success": True}}
    current = operation().model_copy(update={"status": "SUCCEEDED", "result": result})
    store = Store()
    runtime = OperationRuntime(store=store, operation=current)

    replay = runtime.patch_result(result)

    assert replay is current
    assert store.calls == 0
    assert replay.version == current.version


@pytest.mark.parametrize(
    ("approval_status", "operation_status"),
    [("REJECTED", "CANCELLED"), ("EXPIRED", "EXPIRED")],
)
def test_settle_approval_projects_terminal_java_decision(monkeypatch, approval_status, operation_status):
    class FakeRuntime:
        def __init__(self):
            self.operation = operation().model_copy(update={"status": "WAITING_APPROVAL"})
            self.closed = False
            self.transition_data = None

        def transition(self, status, *, event_type=None, data=None):
            self.transition_data = (event_type, data)
            self.operation = transition_operation(
                self.operation, status, expected_version=self.operation.version,
            )
            return self.operation

        def close(self):
            self.closed = True

    fake = FakeRuntime()
    monkeypatch.setattr(
        OperationRuntime,
        "open_existing",
        classmethod(lambda cls, operation_id, *, required=None: fake),
    )

    settled = OperationRuntime.settle_approval(
        "op-1", approval_status, approval_id="approval-1", required=True,
    )

    assert settled is not None
    assert settled.status == operation_status
    assert fake.closed is True
    assert fake.transition_data[1]["approvalId"] == "approval-1"


def test_settle_approval_replaying_same_terminal_decision_is_idempotent(monkeypatch):
    class FakeRuntime:
        def __init__(self):
            self.operation = operation().model_copy(update={"status": "CANCELLED"})
            self.closed = False

        def transition(self, *args, **kwargs):
            raise AssertionError("terminal replay must not transition again")

        def close(self):
            self.closed = True

    fake = FakeRuntime()
    monkeypatch.setattr(
        OperationRuntime,
        "open_existing",
        classmethod(lambda cls, operation_id, *, required=None: fake),
    )

    settled = OperationRuntime.settle_approval(
        "op-1", "REJECTED", approval_id="approval-1", required=True,
    )

    assert settled is fake.operation
    assert fake.closed is True
