from __future__ import annotations

import json
from types import SimpleNamespace

from langchain_core.messages import HumanMessage, ToolMessage

from src.services import meeting_approval as meeting_approval_service
from src.tools.common.events import set_event_context


def _records(status: str) -> tuple[dict, dict]:
    draft = {
        "draftId": "draft-1",
        "approvalId": "approval-1",
        "operationId": "op-1",
        "tenantId": "tenant-1",
        "userId": "user-1",
        "runId": "run-1",
        "threadId": "thread-1",
        "messageId": "message-1",
        "subject": "项目评审",
    }
    approval = {
        "approvalId": "approval-1",
        "draftId": "draft-1",
        "operationId": "op-1",
        "tenantId": "tenant-1",
        "userId": "user-1",
        "runId": "run-1",
        "threadId": "thread-1",
        "messageId": "message-1",
        "status": status,
        "draft": draft,
    }
    return draft, approval


def _bind_context() -> None:
    set_event_context(
        "resume-1",
        "thread-1",
        tenant_id="tenant-1",
        user_id="user-1",
        message_id="message-1",
        origin_run_id="run-1",
        resume_run_id="resume-1",
    )


def test_pending_projection_recovers_operation_only_from_immediate_draft_result():
    request = SimpleNamespace(state={"messages": [ToolMessage(
        content=json.dumps({
            "ok": True,
            "data": {"status": "DRAFT_READY", "operation_id": "op-draft"},
        }),
        name="run_meeting_booking_workflow",
        tool_call_id="draft-call",
    )]})

    assert meeting_approval_service._operation_id_from_draft_request(request) == "op-draft"
    assert meeting_approval_service._operation_id_from_draft_request(
        SimpleNamespace(state={"messages": [HumanMessage(content="确认")]}),
    ) == ""


def test_pending_projection_restores_message_id_from_trusted_checkpoint_binding():
    request = SimpleNamespace(state={
        "current_user_message": {
            "source": "current_human_message",
            "messageId": "message-from-checkpoint",
            "trusted": True,
        },
    })

    assert meeting_approval_service._message_id_from_draft_request(request) == "message-from-checkpoint"
    assert meeting_approval_service._message_id_from_draft_request(SimpleNamespace(
        state={"current_user_message": {"messageId": "untrusted"}},
    )) == ""


def test_settled_rejection_syncs_operation_before_snapshot_resume(monkeypatch):
    _, approval = _records("REJECTED")
    _bind_context()
    monkeypatch.setattr(meeting_approval_service, "get_meeting_approval", lambda _: approval)
    monkeypatch.setattr(
        meeting_approval_service,
        "get_meeting_draft",
        lambda _: (_ for _ in ()).throw(RuntimeError("draft already cancelled")),
    )
    calls = []

    def settle(cls, operation_id, status, *, approval_id=None, required=None):
        calls.append((operation_id, status, approval_id, required))
        return SimpleNamespace(status="CANCELLED")

    monkeypatch.setattr(meeting_approval_service.OperationRuntime, "settle_approval", classmethod(settle))
    monkeypatch.setattr(
        meeting_approval_service.OperationRuntime,
        "open_existing",
        classmethod(lambda cls, operation_id, *, required=None: SimpleNamespace(
            operation=SimpleNamespace(
                action_id="meeting.create",
                approval_id="approval-1",
                origin_run_id="run-1",
            ),
            close=lambda: None,
        )),
    )

    context, error = meeting_approval_service.load_confirmation_context(
        "draft-1", "draft-1", "approval-1"
    )

    assert error is None
    assert context is not None
    assert context.draft_from_approval_snapshot is True
    assert calls == [("op-1", "REJECTED", "approval-1", True)]


def test_expired_approval_sync_failure_blocks_resume(monkeypatch):
    _, approval = _records("EXPIRED")
    _bind_context()
    monkeypatch.setattr(meeting_approval_service, "get_meeting_approval", lambda _: approval)
    monkeypatch.setattr(meeting_approval_service, "get_meeting_draft", lambda _: {"draft": {}})

    def settle(*args, **kwargs):
        raise RuntimeError("runtime database unavailable")

    monkeypatch.setattr(meeting_approval_service.OperationRuntime, "settle_approval", settle)

    context, error = meeting_approval_service.load_confirmation_context(
        "draft-1", "draft-1", "approval-1"
    )

    assert context is None
    assert error is not None
    assert error.error.code == "OPERATION_STATE_SYNC_FAILED"
    assert error.error.retryable is True
