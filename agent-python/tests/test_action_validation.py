import pytest

from src.orchestration.action_validation import validate_action_payload
from src.orchestration.capabilities import ACTION_SPECS


def _action(action_id: str):
    action = next((item for item in ACTION_SPECS if item.action_id == action_id), None)
    assert action is not None
    return action


def test_meeting_create_rejects_non_positive_interval():
    result = validate_action_payload(
        _action("meeting.create"),
        {
            "subject": "评审",
            "start_time": "2026-08-05 14:00:00",
            "end_time": "2026-08-05 14:00:00",
        },
    )
    assert not result.ok
    assert any("结束时间必须晚于开始时间" in item for item in result.invalid_fields)


def test_schedule_query_requires_one_unambiguous_time_shape():
    action = _action("schedule.query")
    with_date_and_range = validate_action_payload(
        action,
        {
            "date": "2026-08-05",
            "start_time": "2026-08-05 09:00:00",
            "end_time": "2026-08-05 10:00:00",
        },
    )
    assert any("不能同时提供" in item for item in with_date_and_range.invalid_fields)

    with_partial_range = validate_action_payload(
        action,
        {"start_time": "2026-08-05 09:00:00"},
    )
    assert any("必须同时提供" in item for item in with_partial_range.invalid_fields)


def test_batch_approval_requires_unique_authorized_tasks_and_valid_action():
    action = _action("approval.write.batch")
    result = validate_action_payload(
        action,
        {"taskIds": ["task-1", "task-1"], "action": "ARCHIVE"},
        authorized_source_fields={"taskIds"},
    )
    assert not result.ok
    assert "action" in result.invalid_fields
    assert any("不能重复" in item for item in result.invalid_fields)

    empty = validate_action_payload(
        action,
        {"taskIds": [], "action": "APPROVE"},
        authorized_source_fields={"taskIds"},
    )
    assert any("不能为空" in item for item in empty.invalid_fields)


def test_source_id_must_be_bound_to_authorized_query_fact():
    action = _action("meeting.update")
    result = validate_action_payload(
        action,
        {
            "source_booking_id": 40,
            "start_time": "2026-08-05 14:00:00",
            "end_time": "2026-08-05 16:00:00",
        },
    )
    assert any("必须来自当前用户授权查询事实" in item for item in result.invalid_fields)


@pytest.mark.parametrize("action_id", ["meeting.update", "schedule.update", "party_file.update"])
def test_update_requires_at_least_one_mutable_field(action_id):
    source_field = {
        "meeting.update": "source_booking_id",
        "schedule.update": "source_schedule_id",
        "party_file.update": "source_party_file_id",
    }[action_id]
    result = validate_action_payload(
        _action(action_id),
        {source_field: 40},
        authorized_source_fields={source_field},
    )
    assert any("至少提供一个要修改的字段" in item for item in result.invalid_fields)


def test_non_approval_reports_require_a_complete_range():
    result = validate_action_payload(
        _action("reporting.meeting"),
        {"start_time": "2026-08-05 09:00:00"},
    )
    assert "end_time" in result.missing_fields


def test_approval_report_amount_filter_is_pairwise():
    result = validate_action_payload(
        _action("reporting.approval"),
        {"amount": 1000},
    )
    assert any("amount_operator" in item for item in result.invalid_fields)
