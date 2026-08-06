from __future__ import annotations

from src.orchestration.routing.router import (
    classify_message,
    clear_route_reasoning_policy,
    get_route_reasoning_policy,
)
from src.tools.common import conversation as conversation_tool


def test_route_tool_stores_the_current_run_reasoning_policy():
    response = conversation_tool.route_conversation.func(
        message="帮我预约一个会议室",
        capability_id="meeting",
        strategy="direct",
        confidence=0.9,
        action_id="meeting.create",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.create",
            "operation": "CREATE",
            "subject": "验收",
            "start_time": "2026-08-06 10:00:00",
            "end_time": "2026-08-06 11:00:00",
        },
    )

    assert response.ok is True
    assert get_route_reasoning_policy() is not None
    assert get_route_reasoning_policy().reasoning_effort == "low"
    clear_route_reasoning_policy()


def test_classifier_keeps_writes_above_the_off_reasoning_floor():
    route = classify_message("取消我的会议预约")

    assert route.mode == "business_action"
    assert route.reasoning_effort == "low"
    assert route.needs_confirmation is True


def test_schedule_workflow_is_selected_by_action_catalog(monkeypatch):
    monkeypatch.setenv("OA_AGENT_SCHEDULE_WORKFLOW_V2", "true")
    response = conversation_tool.route_conversation.func(
        message="创建个人日程",
        capability_id="schedule",
        strategy="direct",
        confidence=0.9,
        action_id="schedule.create",
        execution_class="workflow",
        candidate_plan={
            "action_id": "schedule.create",
            "operation": "CREATE",
            "title": "评审",
            "start_time": "2026-08-07 09:00:00",
            "end_time": "2026-08-07 10:00:00",
        },
    )

    assert response.data["executionTool"] == "run_personal_schedule_workflow"


def test_unsupported_long_tail_keeps_a_bounded_fallback_class():
    response = conversation_tool.route_conversation.func(
        message="帮我设计一个复杂流程图",
        capability_id="general_agent",
        strategy="fallback",
        confidence=0.8,
        execution_class="workflow",
        candidate_plan={},
    )

    assert response.ok is True
    assert response.data["planStatus"] in {"FALLBACK", "CLARIFY"}
