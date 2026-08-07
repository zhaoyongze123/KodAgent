from __future__ import annotations

import pytest

from src.orchestration.capabilities import ACTION_SPECS, actions_for_capability, resolve_action
from src.orchestration.compiler import compile_plan
from src.tools.common import conversation as conversation_tools


def test_action_catalog_is_domain_scoped_and_contains_no_transport_paths():
    for capability in {item.capability_id for item in ACTION_SPECS}:
        actions = actions_for_capability(capability)
        assert actions
        assert all("/agent/" not in item.action_id for item in actions)
        assert all("tool" not in item.action_id.lower() for item in actions)


def test_first_route_stage_returns_action_catalog_without_executing_business_code():
    response = conversation_tools.route_conversation.func(
        message="我想处理一条审批",
        capability_id="approval_process",
        strategy="direct",
        confidence=0.9,
    )

    assert response.ok is True
    assert response.data["planStatus"] == "CLARIFY"
    assert response.data["routePhase"] == "ACTION_SELECTION"
    assert response.data["actionSelection"]["required"] is True
    assert response.data["actionSelection"]["actions"]


def test_second_route_stage_compiles_a_registered_workflow(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    plan = compile_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.create",
            "operation": "CREATE",
            "subject": "架构评审",
            "start_time": "2026-08-06 10:00:00",
            "end_time": "2026-08-06 11:00:00",
        },
    )

    assert plan is not None
    assert plan.status == "RESOLVED"
    assert plan.execution_tool == "run_meeting_booking_workflow"


def test_provider_transport_aliases_compile_to_the_canonical_meeting_action(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    response = conversation_tools.route_conversation.func(
        message="预约会议室，主题为架构验收",
        capability_id="meeting_rooms",
        action_id="create_booking",
        strategy="delegate",
        confidence=0.99,
        execution_class="workflow",
        query_intent={
            "topic": "架构验收",
            "start_time": "2026-12-31 10:00:00",
            "end_time": "2026-12-31 11:00:00",
            "attendees": "仅本人",
        },
        candidate_plan="由会议预约工作流生成草稿",
    )

    assert response.ok is True
    assert response.data["routeDecision"]["capabilityId"] == "meeting"
    assert response.data["actionId"] == "meeting.create"
    assert response.data["planStatus"] == "RESOLVED"
    assert response.data["executionTool"] == "run_meeting_booking_workflow"


def test_book_meeting_room_provider_alias_compiles_to_the_canonical_meeting_action(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    response = conversation_tools.route_conversation.func(
        message="预约会议室，主题为垂直闭环验收",
        capability_id="meeting",
        action_id="book_meeting_room",
        strategy="delegate",
        confidence=0.99,
        execution_class="workflow",
        candidate_plan={
            "subject": "垂直闭环验收",
            "start_time": "2027-01-02 10:00:00",
            "end_time": "2027-01-02 11:00:00",
        },
    )

    assert response.ok is True
    assert response.data["actionId"] == "meeting.create"
    assert response.data["planStatus"] == "RESOLVED"
    assert response.data["executionTool"] == "run_meeting_booking_workflow"


def test_personal_schedule_provider_alias_compiles_to_the_canonical_schedule_action(monkeypatch):
    monkeypatch.setenv("OA_AGENT_SCHEDULE_WORKFLOW_V2", "true")
    response = conversation_tools.route_conversation.func(
        message="创建个人日程，标题为阶段三验收",
        capability_id="schedules",
        action_id="create_schedule_draft",
        strategy="delegate",
        confidence=0.99,
        execution_class="workflow",
        candidate_plan={
            "title": "阶段三验收",
            "start_time": "2026-12-31 10:00:00",
            "end_time": "2026-12-31 11:00:00",
        },
    )

    assert response.ok is True
    assert response.data["routeDecision"]["capabilityId"] == "schedule"
    assert response.data["actionId"] == "schedule.create"
    assert response.data["planStatus"] == "RESOLVED"
    assert response.data["executionTool"] == "run_personal_schedule_workflow"
    assert response.data["executionPlan"]["operation"] == "CREATE"


@pytest.mark.parametrize("provider_action", [
    "create_personal_schedule_draft",
    "schedules/create_schedule_draft",
])
def test_personal_schedule_tool_name_aliases_compile_to_the_canonical_action(monkeypatch, provider_action):
    monkeypatch.setenv("OA_AGENT_SCHEDULE_WORKFLOW_V2", "true")
    response = conversation_tools.route_conversation.func(
        message="创建个人日程，标题为阶段三验收",
        capability_id="schedule",
        action_id=provider_action,
        strategy="delegate",
        confidence=0.99,
        execution_class="workflow",
        candidate_plan={
            "title": "阶段三验收",
            "start_time": "2026-12-31 10:00:00",
            "end_time": "2026-12-31 11:00:00",
        },
    )

    assert response.ok is True
    assert response.data["actionId"] == "schedule.create"
    assert response.data["planStatus"] == "RESOLVED"
    assert response.data["executionTool"] == "run_personal_schedule_workflow"


def test_unknown_action_is_rejected_instead_of_falling_back_to_react():
    plan = compile_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={"action_id": "meeting.unknown", "operation": "CREATE"},
    )

    assert plan is not None
    assert plan.status == "UNSUPPORTED"
    assert plan.execution_tool is None


def test_operation_only_payload_stays_clarification_in_strict_mode():
    plan = compile_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={"operation": "CREATE", "subject": "没有 action id"},
    )

    assert plan is not None
    assert plan.status == "CLARIFY"
    assert "action_id" in plan.missing_fields


@pytest.mark.parametrize(
    ("message", "action_id", "execution_tool"),
    [
        ("查看我发起的审批", "approval.process.applications", "list_my_approval_applications"),
        ("查看已办审批历史", "approval.process.history", "list_my_approval_history"),
    ],
)
def test_approval_scope_is_compiled_to_the_selected_process_action(message, action_id, execution_tool):
    operation = "APPLICATIONS" if action_id.endswith("applications") else "HISTORY"
    response = conversation_tools.route_conversation.func(
        message=message,
        capability_id="approval_process",
        strategy="direct",
        confidence=0.95,
        action_id=action_id,
        execution_class="metadata_query",
        candidate_plan={"action_id": action_id, "operation": operation},
    )

    assert response.ok is True
    assert response.data["executionTool"] == execution_tool


def test_pending_approval_query_remains_read_only():
    plan = compile_plan(
        capability_id="approval_read",
        execution_class="metadata_query",
        candidate_plan={
            "action_id": "approval.read.pending",
            "operation": "QUERY",
            "entity": "pending_approval",
            "limit": 5,
        },
    )

    assert plan is not None
    assert plan.status == "RESOLVED"
    assert plan.execution_tool == "run_approval_query_plan"


@pytest.mark.parametrize("provider_action", [
    "query_pending_approvals",
    "list_pending_approvals",
    "pending_approvals",
    "list_pending_approval_tasks",
])
def test_pending_approval_provider_aliases_resolve_to_only_canonical_read_action(provider_action):
    action = resolve_action("approvals_agent", provider_action)

    assert action is not None
    assert action.action_id == "approval.read.pending"
    assert action.capability_id == "approval_read"
    assert action.read_only is True
    assert action.requires_confirmation is False


def test_pending_approval_provider_alias_cannot_cross_capability():
    assert resolve_action("approval_write", "list_pending_approval_tasks") is None
    assert resolve_action("approval_process", "list_pending_approval_tasks") is None
    assert resolve_action("meeting", "list_pending_approval_tasks") is None


@pytest.mark.parametrize("provider_action", [
    "create_document_draft",
    "create_party_file_draft",
])
def test_party_file_create_aliases_are_scoped_and_confirmation_bound(provider_action):
    action = resolve_action("party_files_agent", provider_action)

    assert action is not None
    assert action.action_id == "party_file.create"
    assert action.read_only is False
    assert action.requires_confirmation is True

    for capability_id in ("approval_read", "approval_process", "meeting", "schedule"):
        assert resolve_action(capability_id, provider_action) is None
