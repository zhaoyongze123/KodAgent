from __future__ import annotations

import importlib.util

from src.orchestration.compiler import compile_plan


def test_meeting_update_compiles_only_with_an_authorized_source_booking(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    plan = compile_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.update",
            "operation": "UPDATE",
            "source_booking_id": 40,
            "_authorized_source_fields": ["source_booking_id"],
            "start_time": "2026-08-06 14:00:00",
            "end_time": "2026-08-06 16:00:00",
        },
    )

    assert plan is not None
    assert plan.status == "RESOLVED"
    assert plan.execution_tool == "run_meeting_booking_workflow"
    assert plan.canonical["operation"] == "UPDATE"
    assert plan.canonical["sourceBookingId"] == 40


def test_meeting_update_without_source_is_clarification_not_a_new_create(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    plan = compile_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.update",
            "operation": "UPDATE",
            "start_time": "2026-08-06 14:00:00",
            "end_time": "2026-08-06 16:00:00",
        },
    )

    assert plan is not None
    assert plan.status == "CLARIFY"
    assert plan.execution_tool is None


def test_meeting_cancel_uses_the_same_workflow_boundary(monkeypatch):
    monkeypatch.setenv("OA_AGENT_MEETING_WORKFLOW_V2", "true")
    plan = compile_plan(
        capability_id="meeting",
        execution_class="workflow",
        candidate_plan={
            "action_id": "meeting.cancel",
            "operation": "CANCEL",
            "source_booking_id": 40,
            "_authorized_source_fields": ["source_booking_id"],
        },
    )

    assert plan is not None
    assert plan.status == "RESOLVED"
    assert plan.execution_tool == "run_meeting_booking_workflow"
    assert plan.canonical["operation"] == "CANCEL"


def test_removed_direct_update_tool_is_not_importable():
    assert importlib.util.find_spec("src.tools.meeting.update") is None
