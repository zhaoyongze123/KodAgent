from __future__ import annotations

from datetime import datetime, timezone

from src.domain.effect import EffectRecord, transition_effect
from src.domain.operation import OperationContext, transition_operation
from src.services.personal_schedule_approval import PersonalScheduleApprovalContext
from src.tools.common.events import set_event_context
from src.tools.common.http_client import JavaFacadeBusinessError
from src.tools.schedule import drafts as schedule_module


class FakeOperationRuntime:
    def __init__(self) -> None:
        self.operation = OperationContext(
            operation_id="op-schedule-1",
            action_id="schedule.create",
            capability_id="schedule",
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
        return self.effect if self.effect and self.effect.idempotency_key == idempotency_key else None

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
        self.effect = transition_effect(effect, "CLAIMED").model_copy(update={
            "attempt": effect.attempt + 1,
            "lease_owner": lease_owner,
            "lease_until": lease_until,
        })
        return self.effect

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
        "operationId": "op-schedule-1",
        "draftId": "schedule-draft-1",
        "approvalId": "schedule-approval-1",
        "operation": "CREATE",
        "runId": "run-1",
        "threadId": "thread-1",
        "tenantId": "tenant-1",
        "userId": "user-1",
        "messageId": "message-1",
    }
    context = PersonalScheduleApprovalContext(
        draft=draft,
        approval={"status": "APPROVED", "operationId": "op-schedule-1"},
        runtime={
            "runId": "resume-1",
            "originRunId": "run-1",
            "resumeRunId": "resume-1",
            "threadId": "thread-1",
            "tenantId": "tenant-1",
            "userId": "user-1",
            "messageId": "message-1",
            "operationId": "op-schedule-1",
        },
        origin_run_id="run-1",
        resume_run_id="resume-1",
    )

    class RuntimeFactory:
        @classmethod
        def open_existing(cls, operation_id, *, required=None):
            assert operation_id == "op-schedule-1"
            assert required is True
            return runtime

    set_event_context(
        "resume-1", "thread-1", tenant_id="tenant-1", user_id="user-1",
        message_id="message-1", origin_run_id="run-1", resume_run_id="resume-1",
        operation_id="op-schedule-1",
    )
    monkeypatch.setattr(schedule_module, "OperationRuntime", RuntimeFactory)
    monkeypatch.setattr(schedule_module, "load_personal_schedule_confirmation", lambda *args: (context, None))
    monkeypatch.setattr(schedule_module, "consume_personal_schedule_resume", lambda _: True)
    monkeypatch.setattr(schedule_module, "complete_personal_schedule_resume", lambda _: True)
    monkeypatch.setattr(schedule_module, "mark_run_resumed", lambda: None)
    monkeypatch.setattr(schedule_module, "get_stream_writer", lambda: None)
    monkeypatch.setattr(schedule_module, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(schedule_module, "merge_operation_payload", lambda patch: runtime)
    monkeypatch.setattr(schedule_module, "java_post", java_post)
    return runtime


def test_personal_schedule_commit_uses_operation_effect_and_operation_id(monkeypatch):
    calls = []
    runtime = _install(
        monkeypatch,
        java_post=lambda path, payload: calls.append((path, payload)) or {
            "success": True, "operation": "CREATE", "scheduleId": 42,
        },
    )

    response = schedule_module.confirm_personal_schedule.func(
        "schedule-draft-1", "schedule-draft-1", "schedule-approval-1",
    )

    assert response.ok is True
    assert calls[0][1]["operationId"] == "op-schedule-1"
    assert runtime.effect is not None
    assert runtime.effect.status == "SUCCEEDED"
    assert runtime.operation.status == "SUCCEEDED"
    assert runtime.closed is True


def test_unknown_personal_schedule_commit_reconciles_without_second_write(monkeypatch):
    calls = []
    runtime = _install(
        monkeypatch,
        java_post=lambda path, payload: calls.append((path, payload)) or (_ for _ in ()).throw(
            RuntimeError("connection reset after Java accepted the request")
        ),
    )

    failed = schedule_module.confirm_personal_schedule.func(
        "schedule-draft-1", "schedule-draft-1", "schedule-approval-1",
    )

    assert failed.ok is False
    assert failed.error.code == "SCHEDULE_COMMIT_UNKNOWN"
    assert runtime.effect is not None
    assert runtime.effect.status == "UNKNOWN"
    assert runtime.operation.status == "UNKNOWN"
    assert len(calls) == 1

    monkeypatch.setattr(
        schedule_module,
        "get_personal_schedule_commit_status",
        lambda draft_id, approval_id, operation_id: {
            "status": "SUBMITTED",
            "result": {"success": True, "operation": "CREATE", "scheduleId": 42},
        },
    )
    recovered = schedule_module.confirm_personal_schedule.func(
        "schedule-draft-1", "schedule-draft-1", "schedule-approval-1",
    )

    assert recovered.ok is True
    assert len(calls) == 1
    assert runtime.effect.status == "SUCCEEDED"
    assert runtime.operation.status == "SUCCEEDED"


def test_personal_schedule_business_rejection_is_final(monkeypatch):
    runtime = _install(
        monkeypatch,
        java_post=lambda path, payload: (_ for _ in ()).throw(
            JavaFacadeBusinessError(409, "PERSONAL_SCHEDULE_CONFLICT：时间冲突", {}, path)
        ),
    )

    response = schedule_module.confirm_personal_schedule.func(
        "schedule-draft-1", "schedule-draft-1", "schedule-approval-1",
    )

    assert response.ok is False
    assert response.error.code == "PERSONAL_SCHEDULE_CONFLICT"
    assert runtime.effect is not None
    assert runtime.effect.status == "FAILED_FINAL"
    assert runtime.operation.status == "FAILED"
