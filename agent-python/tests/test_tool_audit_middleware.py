import asyncio

import pytest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphBubbleUp
from langgraph.prebuilt.tool_node import ToolCallRequest

from src.middleware import tool_audit as audit_module
from src.middleware.tool_audit import ToolAuditMiddleware
from src.tools.common.events import set_event_context


def _request(name, call_id="call-1", args=None):
    return ToolCallRequest(
        tool_call={"name": name, "id": call_id, "args": args or {}},
        tool=None,
        state={"messages": []},
        runtime=None,
    )


@pytest.fixture(autouse=True)
def _event_context():
    set_event_context("run-audit", "thread-audit", message_id="message-audit")


def _capture_events(monkeypatch):
    events = []
    monkeypatch.setattr(audit_module, "get_stream_writer", lambda: None)
    monkeypatch.setattr(
        audit_module,
        "emit",
        lambda writer, event_type, text, **data: events.append(
            {"type": event_type, "text": text, "data": data}
        ),
    )
    return events


def test_parent_tool_gets_structured_lifecycle_without_raw_payload(monkeypatch):
    events = _capture_events(monkeypatch)
    middleware = ToolAuditMiddleware()

    result = middleware.wrap_tool_call(
        _request("route_conversation", "route-1", {"message": "查询我的日程"}),
        lambda request: ToolMessage(
            content='{"ok": true, "data": {"message": "已完成结构化路由"}}',
            tool_call_id="route-1",
        ),
    )

    assert isinstance(result, ToolMessage)
    assert [event["type"] for event in events] == ["tool.started", "tool.completed"]
    assert events[0]["data"]["toolCallId"] == "route-1"
    assert events[1]["data"]["summary"] == "已完成结构化路由"
    assert "args" not in events[0]["data"]


def test_task_emits_subagent_events_with_readable_completion(monkeypatch):
    events = _capture_events(monkeypatch)
    middleware = ToolAuditMiddleware()

    middleware.wrap_tool_call(
        _request(
            "task",
            "task-1",
            {"subagent_type": "meeting_rooms_agent", "description": "查询会议室"},
        ),
        lambda request: ToolMessage(
            content='{"ok": true, "data": {"output": "已查询到二楼会议室"}}',
            tool_call_id="task-1",
        ),
    )

    assert [event["type"] for event in events] == ["subagent.started", "subagent.completed"]
    assert all(event["data"]["toolCallId"] == "task-1" for event in events)
    assert events[1]["data"]["summary"] == "已查询到二楼会议室"
    assert "description" not in repr(events)


def test_task_markdown_completion_preserves_process_body(monkeypatch):
    events = _capture_events(monkeypatch)
    middleware = ToolAuditMiddleware()
    markdown = "## 处理过程\n\n- 已查询会议室\n- 已检查日程\n\n最终建议：二楼会议室"

    middleware.wrap_tool_call(
        _request("task", "task-markdown", {"subagent_type": "meeting_rooms_agent"}),
        lambda request: ToolMessage(content=markdown, tool_call_id="task-markdown"),
    )

    completed = events[-1]
    assert completed["type"] == "subagent.completed"
    assert completed["text"] == markdown
    assert completed["data"]["summary"] == markdown
    assert "\n\n- 已查询会议室" in completed["text"]


def test_manual_business_tool_is_not_emitted_again(monkeypatch):
    events = _capture_events(monkeypatch)
    called = []
    middleware = ToolAuditMiddleware()

    middleware.wrap_tool_call(
        _request("list_available_meeting_rooms", "room-1"),
        lambda request: called.append(True) or ToolMessage(
            content="业务工具已自行上报", tool_call_id="room-1"
        ),
    )

    assert called == [True]
    assert events == []


def test_failed_parent_tool_emits_failed_and_re_raises(monkeypatch):
    events = _capture_events(monkeypatch)
    middleware = ToolAuditMiddleware()

    with pytest.raises(RuntimeError, match="boom"):
        middleware.wrap_tool_call(
            _request("route_conversation", "route-failed"),
            lambda request: (_ for _ in ()).throw(RuntimeError("boom")),
        )

    assert [event["type"] for event in events] == ["tool.started", "tool.failed"]
    assert events[-1]["data"]["toolCallId"] == "route-failed"
    assert events[-1]["data"]["success"] is False


def test_structured_failed_tool_message_emits_failed(monkeypatch):
    events = _capture_events(monkeypatch)
    middleware = ToolAuditMiddleware()

    middleware.wrap_tool_call(
        _request("route_conversation", "route-1"),
        lambda request: ToolMessage(
            content='{"ok": false, "error": {"code": "ROUTE_FAILED", "message": "路由不可用"}}',
            tool_call_id="route-1",
        ),
    )

    assert [event["type"] for event in events] == ["tool.started", "tool.failed"]
    assert events[-1]["data"]["success"] is False
    assert events[-1]["data"]["summary"] == "路由不可用"


def test_hitl_graph_bubble_up_is_not_recorded_as_tool_failure(monkeypatch):
    events = _capture_events(monkeypatch)
    middleware = ToolAuditMiddleware()

    with pytest.raises(GraphBubbleUp):
        middleware.wrap_tool_call(
            _request("task", "task-hitl", {"subagent_type": "meeting_rooms_agent"}),
            lambda request: (_ for _ in ()).throw(GraphBubbleUp()),
        )

    assert [event["type"] for event in events] == ["subagent.started"]


def test_async_task_uses_same_event_contract(monkeypatch):
    events = _capture_events(monkeypatch)
    middleware = ToolAuditMiddleware()

    async def handler(request):
        return ToolMessage(content="子 Agent 已完成日历查询", tool_call_id="task-async")

    asyncio.run(
        middleware.awrap_tool_call(
            _request("task", "task-async", {"subagent_type": "schedules_agent"}), handler
        )
    )

    assert [event["type"] for event in events] == ["subagent.started", "subagent.completed"]
    assert events[-1]["data"]["toolCallId"] == "task-async"
