from __future__ import annotations

from types import SimpleNamespace

from src.tools.common import tool_success
from src.tools.common.events import set_event_context
from src.tools.workflows.meeting_booking import run_meeting_booking_workflow as meeting_tool
from src.workflows.meeting_booking import graph as graph_module


def test_meeting_workflow_requires_an_explicit_source_for_update(monkeypatch):
    monkeypatch.setattr(graph_module, "OperationRuntime", SimpleNamespace(
        start=lambda **kwargs: None,
    ))
    set_event_context("run-update", "thread-update", tenant_id="1", user_id="7", message_id="message-update")

    result = graph_module.run_meeting_booking_workflow(
        operation="UPDATE",
        start_time="2026-08-06 14:00:00",
        end_time="2026-08-06 16:00:00",
        parent_state={"messages": []},
    )

    assert result.status == "NEEDS_INPUT"
    assert result.error_code == "MEETING_SOURCE_REQUIRED"


def test_cancel_workflow_reads_source_before_generating_a_draft(monkeypatch):
    set_event_context("run-cancel", "thread-cancel", tenant_id="1", user_id="7", message_id="message-cancel")
    monkeypatch.setattr(graph_module, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(graph_module, "get_stream_writer", lambda: None)
    source_calls: list[int] = []
    draft_calls: list[dict] = []

    monkeypatch.setattr(
        graph_module,
        "get_my_meeting_booking_service",
        lambda booking_id, **kwargs: source_calls.append(booking_id) or tool_success({
            "bookingId": booking_id,
            "editable": True,
            "status": 1,
            "subject": "项目评审",
            "startTime": "2026-08-06 14:00:00",
            "endTime": "2026-08-06 16:00:00",
        }),
    )
    monkeypatch.setattr(
        graph_module,
        "create_meeting_booking_cancellation_draft_service",
        lambda **kwargs: draft_calls.append(kwargs) or tool_success({
            "requires_confirmation": True,
            "draftId": "draft-1",
            "approvalId": "approval-1",
            "confirmation_token": "draft-1",
            "operationId": "op-1",
        }),
    )
    monkeypatch.setattr(graph_module, "OperationRuntime", SimpleNamespace(
        start=lambda **kwargs: None,
    ))

    result = graph_module.run_meeting_booking_workflow(
        operation="CANCEL",
        source_booking_id=40,
        cancel_reason="时间调整",
        parent_state={"messages": []},
        tool_call_id="cancel-call",
    )

    assert result.status == "DRAFT_READY"
    assert result.draft_id == "draft-1"
    assert source_calls == [40]
    assert draft_calls[0]["booking_id"] == 40
    assert draft_calls[0]["cancel_reason"] == "时间调整"


def test_model_facing_workflow_exposes_structured_source_field():
    schema = meeting_tool.tool_call_schema.model_json_schema()

    assert "operation" in schema["properties"]
    assert "source_booking_id" in schema["properties"]
