from __future__ import annotations

from datetime import datetime, timezone

from src.domain.effect import EffectRecord, transition_effect
from src.domain.operation import OperationContext, transition_operation
from src.services.meeting_approval import ConfirmationContext
from src.tools.common.http_client import JavaFacadeBusinessError
from src.tools.common.events import set_event_context
from src.tools.meeting import booking as booking_module


class FakeOperationRuntime:
    def __init__(self) -> None:
        self.operation = OperationContext(
            operation_id="op-1",
            action_id="meeting.create",
            capability_id="meeting",
            tenant_id="tenant-1",
            user_id="user-1",
            thread_id="thread-1",
            origin_run_id="run-1",
            current_run_id="resume-1",
            message_id="message-1",
            status="WAITING_APPROVAL",
        )
        self.effect: EffectRecord | None = None
        self.closed = False

    @property
    def operation_id(self) -> str:
        return self.operation.operation_id

    def get_effect(self, idempotency_key: str) -> EffectRecord | None:
        if self.effect is not None and self.effect.idempotency_key == idempotency_key:
            return self.effect
        return None

    def create_effect(self, *, request_data, reconcile_strategy, idempotency_key):
        self.effect = EffectRecord(
            operation_id=self.operation_id,
            action_id=self.operation.action_id,
            idempotency_key=idempotency_key,
            request_hash="request-hash",
            reconcile_strategy=reconcile_strategy,
            request_data=request_data,
        )
        return self.effect

    def claim_effect(self, effect, *, lease_owner, lease_until):
        claimed = transition_effect(effect, "CLAIMED").model_copy(update={
            "attempt": effect.attempt + 1,
            "lease_owner": lease_owner,
            "lease_until": lease_until,
        })
        self.effect = claimed
        return claimed

    def transition_effect(self, effect, status, *, response_data=None, error_data=None):
        updated = transition_effect(effect, status)
        updates = {}
        if response_data is not None:
            updates["response_data"] = response_data
        if error_data is not None:
            updates["error_data"] = error_data
        self.effect = updated.model_copy(update=updates)
        return self.effect

    def transition(self, status, *, event_type=None, data=None):
        self.operation = transition_operation(self.operation, status, expected_version=self.operation.version)
        return self.operation

    def patch_result(self, result, *, event_type="operation.result.updated"):
        self.operation = self.operation.model_copy(update={
            "result": result,
            "version": self.operation.version + 1,
            "updated_at": datetime.now(timezone.utc),
        })
        return self.operation

    def close(self):
        self.closed = True


def _install(monkeypatch, *, java_post):
    runtime = FakeOperationRuntime()
    draft = {
        "operationId": "op-1",
        "draftId": "draft-1",
        "approvalId": "approval-1",
        "operation": "CREATE",
        "runId": "run-1",
        "threadId": "thread-1",
        "tenantId": "tenant-1",
        "userId": "user-1",
        "messageId": "message-1",
    }
    context = ConfirmationContext(
        draft=draft,
        approval={"status": "APPROVED"},
        runtime={
            "runId": "resume-1",
            "originRunId": "run-1",
            "resumeRunId": "resume-1",
            "threadId": "thread-1",
            "tenantId": "tenant-1",
            "userId": "user-1",
            "messageId": "message-1",
        },
        origin_run_id="run-1",
        resume_run_id="resume-1",
    )

    class RuntimeFactory:
        @classmethod
        def open_existing(cls, operation_id, *, required=None):
            assert operation_id == "op-1"
            assert required is True
            return runtime

    set_event_context(
        "resume-1",
        "thread-1",
        tenant_id="tenant-1",
        user_id="user-1",
        message_id="message-1",
        origin_run_id="run-1",
        resume_run_id="resume-1",
    )
    monkeypatch.setattr(booking_module, "OperationRuntime", RuntimeFactory)
    monkeypatch.setattr(booking_module, "load_confirmation_context", lambda *args: (context, None))
    monkeypatch.setattr(booking_module, "consume_approval_resume", lambda _: True)
    monkeypatch.setattr(booking_module, "complete_approval_resume", lambda _: True)
    monkeypatch.setattr(booking_module, "consume_rejected_resume", lambda _: True)
    monkeypatch.setattr(booking_module, "mark_run_resumed", lambda: None)
    monkeypatch.setattr(booking_module, "get_stream_writer", lambda: None)
    monkeypatch.setattr(booking_module, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(booking_module, "merge_operation_payload", lambda patch: runtime)
    monkeypatch.setattr(booking_module, "java_post", java_post)
    return runtime


def test_confirm_meeting_booking_persists_effect_and_operation_success(monkeypatch):
    calls = []
    runtime = _install(
        monkeypatch,
        java_post=lambda path, payload: calls.append((path, payload)) or {
            "bookingId": 42,
            "operation": "CREATE",
        },
    )

    response = booking_module.confirm_meeting_booking.func("draft-1", "draft-1", "approval-1")

    assert response.ok is True
    assert calls[0][1]["operationId"] == "op-1"
    assert runtime.effect is not None
    assert runtime.effect.status == "SUCCEEDED"
    assert runtime.operation.status == "SUCCEEDED"
    assert runtime.operation.result["bookingResult"]["bookingId"] == 42
    assert runtime.closed is True


def test_unknown_commit_is_reconciled_before_any_second_write(monkeypatch):
    calls = []
    runtime = _install(
        monkeypatch,
        java_post=lambda path, payload: calls.append((path, payload)) or (_ for _ in ()).throw(
            RuntimeError("connection reset after Java accepted the request")
        ),
    )

    failed = booking_module.confirm_meeting_booking.func("draft-1", "draft-1", "approval-1")

    assert failed.ok is False
    assert failed.error.code == "BOOKING_COMMIT_UNKNOWN"
    assert runtime.effect is not None
    assert runtime.effect.status == "UNKNOWN"
    assert runtime.operation.status == "UNKNOWN"
    assert len(calls) == 1

    monkeypatch.setattr(
        booking_module,
        "get_meeting_booking_commit_status",
        lambda draft_id, approval_id, operation_id: {
            "status": "SUBMITTED",
            "result": {"bookingId": 42, "operation": "CREATE"},
        },
    )
    recovered = booking_module.confirm_meeting_booking.func("draft-1", "draft-1", "approval-1")

    assert recovered.ok is True
    assert len(calls) == 1
    assert runtime.effect.status == "SUCCEEDED"
    assert runtime.operation.status == "SUCCEEDED"


def test_business_rejection_is_final_and_is_not_marked_unknown(monkeypatch):
    runtime = _install(
        monkeypatch,
        java_post=lambda path, payload: (_ for _ in ()).throw(
            JavaFacadeBusinessError(409, "会议室已被占用", {}, path)
        ),
    )

    response = booking_module.confirm_meeting_booking.func("draft-1", "draft-1", "approval-1")

    assert response.ok is False
    assert response.error.code == "BOOKING_BUSINESS_REJECTED"
    assert runtime.effect is not None
    assert runtime.effect.status == "FAILED_FINAL"
    assert runtime.operation.status == "FAILED"
