from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from src.domain.effect import EffectRecord, transition_effect
from src.domain.operation import OperationContext, transition_operation
from src.services import approval_batch_approval as batch_service
from src.services.approval_batch_approval import ApprovalBatchContext
from src.tools.approval import actions


class FakeBatchRuntime:
    def __init__(self, status: str = "WAITING_APPROVAL") -> None:
        self.operation = OperationContext(
            operation_id="op-batch-1",
            action_id="approval.write.batch",
            capability_id="approval",
            tenant_id="tenant-1",
            user_id="user-1",
            thread_id="thread-1",
            origin_run_id="run-1",
            current_run_id="resume-1",
            message_id="message-1",
            status=status,
            approval_id="preview-1",
        )
        self.effect: EffectRecord | None = None
        self.closed = False

    @property
    def operation_id(self) -> str:
        return self.operation.operation_id

    def transition(self, status, *, event_type=None, data=None):
        self.operation = transition_operation(self.operation, status, expected_version=self.operation.version)
        return self.operation

    def bind_approval(self, approval_id):
        self.operation = self.operation.model_copy(update={"approval_id": approval_id})
        return self.operation

    def merge_payload(self, patch, *, event_type="operation.payload.updated"):
        del event_type
        self.operation = self.operation.model_copy(update={
            "payload": {**self.operation.payload, **dict(patch)},
            "version": self.operation.version + 1,
        })
        return self.operation

    def patch_result(self, result, *, event_type="operation.result.updated"):
        self.operation = self.operation.model_copy(update={
            "result": result,
            "version": self.operation.version + 1,
            "updated_at": datetime.now(timezone.utc),
        })
        return self.operation

    def get_effect(self, idempotency_key):
        return self.effect if self.effect and self.effect.idempotency_key == idempotency_key else None

    def create_effect(self, *, request_data, reconcile_strategy, idempotency_key):
        self.effect = EffectRecord(
            operation_id=self.operation_id,
            action_id=self.operation.action_id,
            idempotency_key=idempotency_key,
            request_hash="batch-request-hash",
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

    def close(self):
        self.closed = True


def _context(status: str = "APPROVED") -> ApprovalBatchContext:
    return ApprovalBatchContext(
        preview={
            "previewId": "preview-1",
            "operationId": "op-batch-1",
            "confirmationToken": "token-1",
            "status": status,
            "decisionIdempotencyKey": "decision-1",
            "runId": "run-1",
            "threadId": "thread-1",
            "messageId": "message-1",
            "preview": {
                "action": "APPROVE",
                "reason": "同意",
                "taskIds": ["task-1", "task-2"],
                "tasks": [{"taskId": "task-1"}, {"taskId": "task-2"}],
            },
        },
        runtime={
            "tenantId": "tenant-1",
            "userId": "user-1",
            "threadId": "thread-1",
            "messageId": "message-1",
            "runId": "resume-1",
            "originRunId": "run-1",
            "operationId": "op-batch-1",
        },
        origin_run_id="run-1",
    )


def test_batch_preview_creates_parent_operation_and_binds_java_preview(monkeypatch):
    runtime = FakeBatchRuntime("COLLECTING_INFO")
    captured = {}

    class RuntimeFactory:
        @classmethod
        def start(cls, **kwargs):
            assert kwargs["action_id"] == "approval.write.batch"
            assert kwargs["required"] is True
            return runtime

    monkeypatch.setattr(actions, "OperationRuntime", RuntimeFactory)
    monkeypatch.setattr(actions, "current_agent_context", lambda: {
        "tenantId": "tenant-1", "userId": "user-1", "threadId": "thread-1",
        "runId": "run-1", "originRunId": "run-1", "messageId": "message-1",
    })
    monkeypatch.setattr(actions, "get_stream_writer", lambda: None)
    monkeypatch.setattr(actions, "java_post", lambda path, payload: captured.update(path=path, payload=payload) or {
        "previewId": "preview-1", "operationId": "op-batch-1", "confirmationToken": "token-1",
        "taskCount": 1, "status": "PENDING",
    })

    response = actions.preview_approval_batch_action.func(action="APPROVE", task_ids=["task-1"])

    assert response.ok is True
    assert captured["payload"]["operationId"] == "op-batch-1"
    assert runtime.operation.status == "WAITING_APPROVAL"
    assert runtime.operation.approval_id == "preview-1"
    assert runtime.closed is True


def test_batch_pending_context_recovers_without_redis(monkeypatch):
    operation = SimpleNamespace(
        operation_id="op-batch-1",
        action_id="approval.write.batch",
        status="WAITING_APPROVAL",
        approval_id="preview-1",
        tenant_id="tenant-1",
        user_id="user-1",
        thread_id="thread-1",
        message_id="message-1",
    )
    runtime = SimpleNamespace(operation=operation, close=lambda: None)

    class RuntimeGateway:
        @classmethod
        def find_by_binding(cls, **kwargs):
            return [operation]

        @classmethod
        def open_existing(cls, operation_id, *, required=None):
            assert operation_id == "op-batch-1"
            assert required is True
            return runtime

    monkeypatch.setattr(batch_service, "OperationRuntime", RuntimeGateway)
    monkeypatch.setattr(batch_service, "set_operation_context", lambda value: None)
    monkeypatch.setattr(batch_service, "current_agent_context", lambda: {
        "tenantId": "tenant-1", "userId": "user-1", "threadId": "thread-1",
        "runId": "resume-1", "originRunId": "run-1", "messageId": "message-1",
        "operationId": "",
    })
    monkeypatch.setattr(batch_service, "java_get", lambda path: {
        "previewId": "preview-1", "operationId": "op-batch-1", "confirmationToken": "token-1",
        "status": "PENDING", "runId": "run-1", "threadId": "thread-1", "messageId": "message-1",
        "preview": {"action": "APPROVE", "reason": "同意", "tasks": [{"taskId": "task-1"}]},
    })

    context, error = batch_service.load_pending_approval_batch_context()

    assert error is None
    assert context is not None
    assert context.preview["operationId"] == "op-batch-1"


def test_batch_confirmation_persists_one_atomic_effect(monkeypatch):
    runtime = FakeBatchRuntime()
    context = _context()
    calls = []

    class RuntimeGateway:
        @classmethod
        def open_existing(cls, operation_id, *, required=None):
            assert operation_id == "op-batch-1"
            return runtime

    monkeypatch.setattr(actions, "OperationRuntime", RuntimeGateway)
    monkeypatch.setattr(actions, "load_approval_batch", lambda *_: (context, None))
    monkeypatch.setattr(actions, "can_execute_batch", lambda value: True)
    monkeypatch.setattr(actions, "can_replay_batch", lambda value: False)
    monkeypatch.setattr(actions, "complete_batch", lambda value: True)
    monkeypatch.setattr(actions, "get_stream_writer", lambda: None)
    monkeypatch.setattr(actions, "java_post", lambda path, payload: calls.append((path, payload)) or {
        "previewId": "preview-1", "success": True,
        "results": [{"taskId": "task-1", "status": "SUCCESS"}, {"taskId": "task-2", "status": "SUCCESS"}],
    })

    response = actions.confirm_approval_batch_action.func("preview-1", "token-1")

    assert response.ok is True
    assert calls[0][1]["operationId"] == "op-batch-1"
    assert runtime.effect is not None
    assert runtime.effect.status == "SUCCEEDED"
    assert runtime.operation.status == "SUCCEEDED"
    assert runtime.closed is True


def test_batch_reconcile_uses_java_external_fact_without_resubmitting(monkeypatch):
    runtime = FakeBatchRuntime("UNKNOWN")
    effect = EffectRecord(
        operation_id=runtime.operation_id,
        action_id="approval.write.batch",
        idempotency_key="approval-batch:v2:preview-1",
        request_hash="batch-request-hash",
        reconcile_strategy="approval.batch.preview-status",
        request_data={
            "previewId": "preview-1",
            "confirmationToken": "token-1",
        },
        status="UNKNOWN",
    )
    runtime.effect = effect
    calls = []

    class RuntimeGateway:
        @classmethod
        def open_existing(cls, operation_id, *, required=None):
            return runtime

    monkeypatch.setattr(actions, "java_post", lambda path, payload: calls.append((path, payload)) or {
        "previewId": "preview-1",
        "operationId": "op-batch-1",
        "status": "COMPLETED",
        "result": {"results": [{"taskId": "task-1", "status": "SUCCESS"}]},
    })

    result = actions._reconcile_batch_effect(runtime, effect)

    assert result["results"][0]["status"] == "SUCCESS"
    assert calls == [(
        "/agent/tools/approvals/batch/preview-1/reconcile",
        {
            "confirmationToken": "token-1",
            "operationId": "op-batch-1",
            "idempotencyKey": "approval-batch:v2:preview-1",
        },
    )]
