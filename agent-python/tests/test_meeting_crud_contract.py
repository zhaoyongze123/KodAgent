from __future__ import annotations

from types import SimpleNamespace

from src.orchestration.routing.recovery_handlers.meeting import meeting_follow_up_plan


def _facts(candidates: list[dict]) -> SimpleNamespace:
    return SimpleNamespace(facts={"meeting_query": {"editableCandidates": candidates}})


def test_unique_authorized_meeting_query_can_bind_a_follow_up():
    result = meeting_follow_up_plan(
        "改到 14 点",
        _facts([{"bookingId": 40, "subject": "项目评审"}]),
    )

    assert result == {
        "status": "RESOLVED",
        "operation": "UPDATE",
        "source_booking_id": 40,
        "_authorized_source_fields": ["source_booking_id"],
    }


def test_ambiguous_meeting_query_stops_at_clarification():
    result = meeting_follow_up_plan(
        "取消刚才的预约",
        _facts([{"bookingId": 40}, {"bookingId": 41}]),
    )

    assert result["status"] == "CLARIFY"
    assert len(result["options"]) == 2


def test_explicit_unlisted_booking_id_is_not_authorized_by_a_query_projection():
    result = meeting_follow_up_plan(
        "取消预约 999",
        _facts([{"bookingId": 40}]),
    )

    assert result["status"] == "CLARIFY"
    assert result["options"] == []


def test_missing_query_fact_cannot_bind_a_write_target():
    assert meeting_follow_up_plan("修改刚才的预约", SimpleNamespace(facts={})) is None
