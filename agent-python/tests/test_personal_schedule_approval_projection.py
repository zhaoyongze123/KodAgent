from __future__ import annotations

import json
from types import SimpleNamespace

from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.middleware import personal_schedule_approval as middleware
from src.services import personal_schedule_approval as service
from src.tools.common.events import current_agent_context, set_event_context


def _request(last_message, *, binding=None):
    state = {"messages": [last_message]}
    if binding is not None:
        state["current_user_message"] = binding
    return SimpleNamespace(state=state)


def _draft_message(operation_id: str = "op-schedule-1"):
    return ToolMessage(
        content=json.dumps({
            "ok": True,
            "data": {"status": "DRAFT_READY", "operationId": operation_id},
        }),
        name="run_personal_schedule_workflow",
        tool_call_id="draft-call",
    )


def test_pending_schedule_context_recovers_operation_and_message_from_current_draft_frame(monkeypatch):
    set_event_context("run-1", "thread-1", message_id="")
    operation = SimpleNamespace(status="WAITING_APPROVAL", approval_id="op-approval-1")
    context = SimpleNamespace(
        approval={"operationId": "op-schedule-1", "status": "PENDING"},
    )
    monkeypatch.setattr(service, "_operation_snapshot", lambda operation_id: operation)
    monkeypatch.setattr(
        service,
        "load_personal_schedule_confirmation",
        lambda draft_id, approval_id: (context, None),
    )

    request = _request(
        _draft_message(),
        binding={
            "source": "current_human_message",
            "messageId": "message-1",
            "trusted": True,
        },
    )

    resolved, error = service.load_pending_personal_schedule_context(request)

    assert error is None
    assert resolved is context
    assert current_agent_context()["operationId"] == "op-schedule-1"
    assert current_agent_context()["messageId"] == "message-1"


def test_pending_schedule_context_does_not_recover_operation_from_a_later_human_message(monkeypatch):
    set_event_context("run-1", "thread-1", message_id="")
    called = []
    monkeypatch.setattr(service, "_operation_snapshot", lambda operation_id: called.append(operation_id))

    resolved, error = service.load_pending_personal_schedule_context(
        _request(HumanMessage(content="确认"))
    )

    assert resolved is None
    assert error is not None
    assert error.error.code == "OPERATION_REQUIRED"
    assert called == []


def test_schedule_middleware_passes_the_current_request_to_context_loader(monkeypatch):
    request = _request(_draft_message())
    response = ModelResponse(result=[AIMessage(content="等待确认")])
    observed = []
    context = SimpleNamespace(
        origin_run_id="run-1",
        runtime={"messageId": "message-1"},
        draft={"approvalId": "approval-1", "draftId": "draft-1"},
    )
    monkeypatch.setattr(
        middleware,
        "load_pending_personal_schedule_context",
        lambda incoming: observed.append(incoming) or (context, None),
    )
    monkeypatch.setattr(middleware, "is_draft_projection_turn", lambda *_args: True)
    monkeypatch.setattr(middleware, "is_delegated_draft_projection_turn", lambda *_args: False)
    monkeypatch.setattr(
        middleware,
        "personal_schedule_confirmation_args",
        lambda _context, _args: {"approvalId": "approval-1"},
    )

    projected = middleware._enrich_or_inject(request, response)

    assert observed == [request]
    assert projected.result[0].tool_calls[0]["name"] == middleware.CONFIRM_TOOL_NAME
