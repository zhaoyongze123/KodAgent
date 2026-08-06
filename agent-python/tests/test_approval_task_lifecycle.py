from __future__ import annotations

from types import SimpleNamespace

from src.domain.operation import OperationContext
from src.services import approval_task_approval as approval_task
from src.tools.common.events import set_event_context


def _operation(status: str = "WAITING_APPROVAL") -> OperationContext:
    return OperationContext(
        operation_id="op-task-1",
        action_id="approval.write.task",
        capability_id="approval",
        tenant_id="tenant-1",
        user_id="user-1",
        thread_id="thread-1",
        origin_run_id="run-1",
        current_run_id="run-1",
        message_id="message-1",
        status=status,
        approval_id="approval-1",
    )


def _context(status: str = "APPROVED", *, resume_key: str = "agent-resume:v1:approval-1"):
    return approval_task.ApprovalTaskContext(
        approval={
            "approvalId": "approval-1",
            "draftId": "draft-1",
            "draftType": "APPROVAL_TASK",
            "operationId": "op-task-1",
            "runId": "run-1",
            "threadId": "thread-1",
            "messageId": "message-1",
            "status": status,
            "resumeIdempotencyKey": resume_key,
            "draft": {"taskId": "task-1", "action": "APPROVE", "reason": "同意"},
        },
        runtime={
            "runId": "resume-1",
            "originRunId": "run-1",
            "resumeRunId": "resume-1",
            "threadId": "thread-1",
            "messageId": "message-1",
            "operationId": "op-task-1",
        },
    )


def test_operation_bound_context_does_not_require_a_task_projection(monkeypatch):
    context = _context()
    monkeypatch.setattr(approval_task, "_load", lambda _approval_id: (context, None))

    loaded, error = approval_task.load_approval_task_context("approval-1")

    assert error is None
    assert loaded is context


def test_pending_context_uses_operation_status_and_java_approval(monkeypatch):
    context = _context("PENDING", resume_key="")
    set_event_context(
        "run-1",
        "thread-1",
        tenant_id="tenant-1",
        user_id="user-1",
        message_id="message-1",
        operation_id="op-task-1",
    )
    monkeypatch.setattr(approval_task, "_operation_snapshot", lambda _operation_id: _operation())
    monkeypatch.setattr(approval_task, "_load", lambda _approval_id: (context, None))

    loaded, error = approval_task.load_pending_approval_task_context()

    assert error is None
    assert loaded is context


def test_approved_resume_requires_java_idempotency_proof(monkeypatch):
    context = _context()
    resumed: list[bool] = []
    monkeypatch.setattr(approval_task, "_load", lambda _approval_id: (context, None))
    monkeypatch.setattr(approval_task, "has_trusted_approval_projection", lambda *args, **kwargs: True)
    monkeypatch.setattr(approval_task, "mark_run_resumed", lambda: resumed.append(True))

    request = SimpleNamespace(
        tool_call={"args": {"approvalId": "approval-1"}},
        runtime=SimpleNamespace(stream_writer=None),
        state={"messages": []},
    )

    assert approval_task.prepare_confirmation_interrupt(request) is False
    assert resumed == [True]


def test_rejected_resume_uses_terminal_approval_fact_without_a_task_marker(monkeypatch):
    context = _context("REJECTED", resume_key="")
    resumed: list[bool] = []
    monkeypatch.setattr(approval_task, "_load", lambda _approval_id: (context, None))
    monkeypatch.setattr(approval_task, "has_trusted_approval_projection", lambda *args, **kwargs: True)
    monkeypatch.setattr(approval_task, "mark_run_resumed", lambda: resumed.append(True))

    request = SimpleNamespace(
        tool_call={"args": {"approvalId": "approval-1"}},
        runtime=SimpleNamespace(stream_writer=None),
        state={"messages": []},
    )

    assert approval_task.prepare_confirmation_interrupt(request) is False
    assert resumed == [True]
