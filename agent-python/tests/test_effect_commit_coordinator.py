from datetime import datetime, timezone

import pytest

from src.domain.effect import EffectRecord, transition_effect
from src.domain.operation import OperationContext, transition_operation
from src.runtime.effect_commit import EffectCommitCoordinator, StoredFinalFailure


class FakeRuntime:
    def __init__(self):
        self.operation = OperationContext(
            operation_id="op-1",
            action_id="approval.write.task",
            capability_id="approval",
            tenant_id="tenant-1",
            user_id="user-1",
            thread_id="thread-1",
            origin_run_id="run-1",
            current_run_id="resume-1",
            message_id="message-1",
            status="UNKNOWN",
        )
        self.effect = EffectRecord(
            operation_id="op-1",
            action_id="approval.write.task",
            idempotency_key="effect-1",
            request_hash="hash-1",
            reconcile_strategy="approval.task.action-status",
            status="UNKNOWN",
        )

    def transition_effect(self, effect, status, *, response_data=None, error_data=None):
        updated = transition_effect(effect, status)
        if response_data is not None:
            updated = updated.model_copy(update={"response_data": response_data})
        if error_data is not None:
            updated = updated.model_copy(update={"error_data": error_data})
        self.effect = updated
        return updated

    def transition(self, status, *, event_type=None, data=None):
        self.operation = transition_operation(
            self.operation, status, expected_version=self.operation.version,
        )
        return self.operation

    def patch_result(self, result, *, event_type="operation.result.updated"):
        self.operation = self.operation.model_copy(update={
            "result": result,
            "version": self.operation.version + 1,
            "updated_at": datetime.now(timezone.utc),
        })
        return self.operation


def test_reconcile_persists_deterministic_final_failure():
    runtime = FakeRuntime()
    coordinator = EffectCommitCoordinator(
        runtime=runtime,
        expected_action_id="approval.write.task",
        request_data={"taskId": "task-1"},
        idempotency_key="effect-1",
        reconcile_strategy="approval.task.action-status",
        lease_owner="test",
    )
    coordinator.effect = runtime.effect

    with pytest.raises(StoredFinalFailure):
        coordinator.reconcile(
            lambda _effect: (_ for _ in ()).throw(StoredFinalFailure({
                "code": "APPROVAL_TASK_EXTERNAL_STATE_MISMATCH",
                "message": "动作与外部状态不一致",
            }))
        )

    assert runtime.effect.status == "FAILED_FINAL"
    assert runtime.operation.status == "FAILED"
    assert runtime.operation.result["status"] == "FAILED"


def test_reconcile_clears_stale_error_when_effect_succeeds():
    runtime = FakeRuntime()
    runtime.effect = runtime.effect.model_copy(update={
        "error_data": {"code": "RECONCILE_UNAVAILABLE"},
    })
    coordinator = EffectCommitCoordinator(
        runtime=runtime,
        expected_action_id="approval.write.task",
        request_data={"taskId": "task-1"},
        idempotency_key="effect-1",
        reconcile_strategy="approval.task.action-status",
        lease_owner="test",
    )
    coordinator.effect = runtime.effect

    result = coordinator.reconcile(lambda _effect: {"success": True})

    assert result == {"success": True}
    assert runtime.effect.status == "SUCCEEDED"
    assert runtime.effect.error_data == {}
