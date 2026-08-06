from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from src.middleware.meeting_prepare_first import MeetingPrepareFirstMiddleware
from src.middleware.meeting_task_guard import MeetingTaskCallGuardMiddleware


def test_prepare_first_blocks_booking_tools_in_the_same_parallel_model_batch():
    state = {
        "messages": [AIMessage(content="", tool_calls=[
            {"name": "prepare_meeting_booking_request", "args": {}, "id": "prepare", "type": "tool_call"},
            {"name": "create_meeting_booking_draft", "args": {}, "id": "draft", "type": "tool_call"},
        ])]
    }

    result = MeetingPrepareFirstMiddleware().after_model(state, None)

    assert result is not None
    assert len(result["messages"]) == 1
    assert result["messages"][0].response_metadata["guard"] == "meeting_prepare_first"


def test_meeting_task_guard_limits_repeated_subagent_calls_to_one_per_user_turn():
    state = {
        "messages": [
            HumanMessage(content="帮我预约会议室"),
            AIMessage(content="", tool_calls=[{
                "name": "task",
                "args": {"subagent_type": "meeting_rooms_agent", "description": "查询会议室"},
                "id": "task-1",
                "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "task",
                "args": {"subagent_type": "meeting_rooms_agent", "description": "再次查询会议室"},
                "id": "task-2",
                "type": "tool_call",
            }]),
        ]
    }

    result = MeetingTaskCallGuardMiddleware().after_model(state, None)

    assert result is not None
    assert result["messages"][0].response_metadata["guard"] == "meeting_task_once_per_message"


def test_non_meeting_task_is_not_blocked_by_meeting_guard():
    state = {
        "messages": [
            HumanMessage(content="查询审批"),
            AIMessage(content="", tool_calls=[{
                "name": "task",
                "args": {"subagent_type": "approvals_agent", "description": "查询审批"},
                "id": "task-1",
                "type": "tool_call",
            }]),
            AIMessage(content="", tool_calls=[{
                "name": "task",
                "args": {"subagent_type": "approvals_agent", "description": "再次查询审批"},
                "id": "task-2",
                "type": "tool_call",
            }]),
        ]
    }

    assert MeetingTaskCallGuardMiddleware().after_model(state, None) is None
