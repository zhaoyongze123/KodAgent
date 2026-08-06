from __future__ import annotations

import pytest

from src.orchestration.capabilities import ACTION_SPECS, actions_for_capability
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
