"""Regression coverage for the shared one-frame approval projection rule."""

from types import SimpleNamespace

from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.middleware import approval_batch_approval as batch_middleware
from src.middleware import approval_task_approval as task_middleware
from src.middleware.approval_projection import is_delegated_draft_projection_turn


def _response():
    return ModelResponse(result=[AIMessage(content="预览已经生成")])


def _draft_frame(tool_name: str):
    return SimpleNamespace(state={"messages": [ToolMessage(
        content='{"ok": true, "data": {"requires_confirmation": true}}',
        name=tool_name,
        tool_call_id="preview-call",
    )]})


def _later_text_frame():
    return SimpleNamespace(state={"messages": [HumanMessage(content="确认")]})


def _delegated_task_frame(agent_name: str):
    """The generic DeepAgents gateway returns an unnamed ToolMessage."""
    return SimpleNamespace(state={"messages": [
        AIMessage(content="", tool_calls=[{
            "name": "task",
            "args": {"subagent_type": agent_name, "description": "处理业务请求"},
            "id": "parent-task-call",
            "type": "tool_call",
        }]),
        ToolMessage(content="子 Agent 已生成待确认草稿", tool_call_id="parent-task-call"),
    ]})


def test_batch_projection_requires_immediately_preceding_preview(monkeypatch):
    context = SimpleNamespace(
        origin_run_id="run-1",
        runtime={"messageId": "message-1"},
        preview={"previewId": "preview-1"},
    )
    monkeypatch.setattr(batch_middleware, "load_pending_approval_batch_context", lambda: (context, None))
    monkeypatch.setattr(batch_middleware, "confirmation_args", lambda _context, _args: {"preview_id": "preview-1"})
    middleware = batch_middleware.ApprovalBatchAutoConfirmMiddleware()

    projected = middleware._inject(_draft_frame("preview_approval_batch_action"), _response())
    later = middleware._inject(_later_text_frame(), _response())

    assert projected.result[0].tool_calls[0]["name"] == "confirm_approval_batch_action"
    assert later.result[0].tool_calls == []


def test_task_projection_requires_immediately_preceding_preview(monkeypatch):
    context = SimpleNamespace(
        runtime={"runId": "run-1", "messageId": "message-1"},
        approval={"approvalId": "approval-1"},
    )
    monkeypatch.setattr(task_middleware, "load_pending_approval_task_context", lambda: (context, None))
    monkeypatch.setattr(task_middleware, "confirmation_args", lambda _context, _args: {"approvalId": "approval-1"})
    middleware = task_middleware.ApprovalTaskAutoConfirmMiddleware()

    projected = middleware._apply(_draft_frame("preview_approval_task_action"), _response())
    later = middleware._apply(_later_text_frame(), _response())

    assert projected.result[0].tool_calls[0]["name"] == "confirm_approval_task_action"
    assert later.result[0].tool_calls == []


def test_delegated_projection_recovers_the_parent_task_boundary_only():
    assert is_delegated_draft_projection_turn(
        _delegated_task_frame("meeting_rooms_agent"), {"meeting_rooms_agent"}
    ) is True
    assert is_delegated_draft_projection_turn(
        _delegated_task_frame("approvals_agent"), {"meeting_rooms_agent"}
    ) is False
    assert is_delegated_draft_projection_turn(
        _later_text_frame(), {"meeting_rooms_agent"}
    ) is False


def test_batch_projection_accepts_the_trusted_approvals_child_gateway(monkeypatch):
    context = SimpleNamespace(
        origin_run_id="run-1",
        runtime={"messageId": "message-1"},
        preview={"previewId": "preview-1"},
    )
    monkeypatch.setattr(batch_middleware, "load_pending_approval_batch_context", lambda: (context, None))
    monkeypatch.setattr(batch_middleware, "confirmation_args", lambda _context, _args: {"preview_id": "preview-1"})

    result = batch_middleware.ApprovalBatchAutoConfirmMiddleware()._inject(
        _delegated_task_frame("approvals_agent"), _response()
    )

    assert result.result[0].tool_calls[0]["name"] == "confirm_approval_batch_action"


def test_single_task_projection_accepts_the_trusted_approvals_child_gateway(monkeypatch):
    context = SimpleNamespace(
        runtime={"runId": "run-1", "messageId": "message-1"},
        approval={"approvalId": "approval-1"},
    )
    monkeypatch.setattr(task_middleware, "load_pending_approval_task_context", lambda: (context, None))
    monkeypatch.setattr(task_middleware, "confirmation_args", lambda _context, _args: {"approvalId": "approval-1"})

    result = task_middleware.ApprovalTaskAutoConfirmMiddleware()._apply(
        _delegated_task_frame("approvals_agent"), _response()
    )

    assert result.result[0].tool_calls[0]["name"] == "confirm_approval_task_action"
