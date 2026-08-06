from __future__ import annotations

from src.domain.conversation import ConversationRoute
from src.orchestration.routing.router import classify_message
from src.tools.common import conversation as conversation_tools


def test_simple_chat_is_not_a_business_operation():
    route = classify_message("你好")

    assert route.mode == "chat"
    assert route.needs_tools is False
    assert route.reasoning_effort == "off"


def test_business_action_is_classified_with_a_safety_floor():
    route = classify_message("帮我预约一个会议室")

    assert route.mode == "business_action"
    assert route.needs_tools is True
    assert route.reasoning_effort == "low"


def test_read_only_schedule_query_has_no_operation_side_effect():
    response = conversation_tools.route_conversation.func(
        message="查询 2026年8月7日的日程",
        capability_id="schedule",
        execution_class="metadata_query",
        candidate_plan={
            "action_id": "schedule.query",
            "operation": "QUERY",
            "schedule_type": "personal",
            "date": "2026-08-07",
        },
    )

    assert response.ok is True
    assert response.data["planStatus"] == "RESOLVED"
    assert response.data["executionTool"] == "get_my_calendar"


def test_update_plan_requires_explicit_source_and_does_not_reuse_thread_memory(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    response = conversation_tools.route_conversation.func(
        message="把会议改到下午四点",
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.update",
            "operation": "UPDATE",
            "start_time": "2026-08-06 16:00:00",
            "end_time": "2026-08-06 17:00:00",
        },
    )

    assert response.ok is True
    assert response.data["planStatus"] == "CLARIFY"
    assert response.data["executionTool"] if "executionTool" in response.data else True
    assert response.data["clarification"]["missingFields"] == ["source_booking_id"]


def test_explicit_source_is_compiled_into_the_workflow_call(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    response = conversation_tools.route_conversation.func(
        message="把预约 40 改到下午四点",
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.update",
            "operation": "UPDATE",
            "source_booking_id": 40,
            "_authorized_source_fields": ["source_booking_id"],
            "start_time": "2026-08-06 16:00:00",
            "end_time": "2026-08-06 17:00:00",
        },
    )

    assert response.data["planStatus"] == "RESOLVED"
    assert response.data["executionTool"] == "run_meeting_booking_workflow"
    assert response.data["executionPlan"]["sourceBookingId"] == 40
