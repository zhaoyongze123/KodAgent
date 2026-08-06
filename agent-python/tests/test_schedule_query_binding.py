from __future__ import annotations

from types import SimpleNamespace

from src.orchestration.routing.recovery_handlers.schedule import (
    schedule_follow_up_plan,
    schedule_metadata_fallback_plan,
)


def _facts(candidates: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(facts={"schedule_query": {"editableCandidates": candidates}})


def test_query_projection_can_bind_only_one_editable_personal_schedule():
    result = schedule_follow_up_plan(
        "把刚才日程改到 14 点",
        _facts([{"sourceType": "PERSONAL_SCHEDULE", "sourceId": 17, "editable": True}]),
    )

    assert result["status"] == "RESOLVED"
    assert result["source_schedule_id"] == 17
    assert result["_authorized_source_fields"] == ["source_schedule_id"]


def test_multiple_editable_schedules_require_clarification():
    result = schedule_follow_up_plan(
        "取消刚才日程",
        _facts([
            {"sourceType": "PERSONAL_SCHEDULE", "sourceId": 17, "editable": True},
            {"sourceType": "PERSONAL_SCHEDULE", "sourceId": 18, "editable": True},
        ]),
    )

    assert result["status"] == "CLARIFY"
    assert result["options"][0]["sourceScheduleId"] == 17


def test_query_projection_never_promotes_a_meeting_booking_to_schedule_target():
    result = schedule_follow_up_plan(
        "取消刚才日程",
        _facts([{"sourceType": "MEETING_BOOKING", "sourceId": 38, "editable": True}]),
    )

    assert result["status"] == "CLARIFY"
    assert result["options"] == []


def test_explicit_calendar_date_has_a_read_only_metadata_plan():
    result = schedule_metadata_fallback_plan("查询 2026年8月7日的日程")

    assert result["capability_id"] == "schedule"
    assert result["execution_class"] == "metadata_query"
    assert result["candidate_plan"]["action_id"] == "schedule.query"
    assert result["candidate_plan"]["operation"] == "QUERY"
