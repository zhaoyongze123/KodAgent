from datetime import date, datetime

import pytest

from src.domain.meeting import MeetingBookingRequest
from src.services.meeting_request import (
    contains_self_only_attendee_phrase,
    normalize_attendee_name,
    normalize_attendee_names,
    resolve_attendee_results,
    resolve_time_range,
    validate_meeting_request,
)


def test_resolve_explicit_time_range():
    start, end, missing, errors = resolve_time_range(
        "2026-07-22 14:00—16:00",
        now=datetime(2026, 7, 20, 9, 0),
    )
    assert start.strftime("%Y-%m-%d %H:%M:%S") == "2026-07-22 14:00:00"
    assert end.strftime("%Y-%m-%d %H:%M:%S") == "2026-07-22 16:00:00"
    assert missing == []
    assert errors == []


def test_resolve_next_weekday_without_guessing_end_time():
    start, end, missing, errors = resolve_time_range(
        "下周三下午两点",
        "下午四点",
        now=datetime(2026, 7, 24, 9, 0),  # Friday
    )
    assert start.date() == date(2026, 7, 29)
    assert end.date() == date(2026, 7, 29)
    assert start.hour == 14 and end.hour == 16
    assert missing == []
    assert errors == []


def test_missing_time_is_reported_instead_of_inferred():
    start, end, missing, errors = resolve_time_range(
        "明天下午",
        now=datetime(2026, 7, 24, 9, 0),
    )
    assert start is None and end is None
    assert "start_time" in missing
    assert "end_time" in missing
    assert errors == []


def test_attendees_are_deduplicated_and_ambiguous_users_are_returned():
    ids, names, candidates, errors = resolve_attendee_results(
        ["我", "侯斌超", "张伟"],
        current_user={"userId": 1, "userNickname": "超级管理员"},
        search_results={
            "侯斌超": [{"userId": 215, "userNickname": "侯斌超"}],
            "张伟": [
                {"userId": 2, "userNickname": "张伟", "department": "技术部"},
                {"userId": 3, "userNickname": "张伟", "department": "行政部"},
            ],
        },
    )
    assert ids == [1, 215]
    assert names == ["超级管理员", "侯斌超"]
    assert len(candidates) == 2
    assert errors == []


def test_model_compound_self_reference_resolves_to_current_user():
    # The user said "只有我参加", while the model emitted "我本人" as the
    # structured attendee argument.  It must resolve through /me, not a
    # directory search for the literal phrase.
    assert normalize_attendee_names(["我本人"]) == ["当前用户"]
    assert contains_self_only_attendee_phrase("只有我参加") is True
    ids, names, candidates, errors = resolve_attendee_results(
        ["我本人"],
        current_user={"userId": 1, "userNickname": "系统管理员"},
        search_results={},
    )
    assert ids == [1]
    assert names == ["系统管理员"]
    assert candidates == []
    assert errors == []


@pytest.mark.parametrize(
    "value",
    [
        "我本人",
        "本人参加",
        "仅我本人参加",
        "仅当前用户本人",
        "只有当前用户本人参会",
        "仅有用户本人出席",
        "only_current_user",
    ],
)
def test_decorated_current_user_referents_are_canonicalized(value):
    assert normalize_attendee_name(value) == "当前用户"


@pytest.mark.parametrize("value", ["我本人张三", "只有我本人和张三参加", "张三本人"])
def test_real_or_mixed_attendee_names_are_not_swallowed(value):
    assert normalize_attendee_name(value) == value


def test_mixed_self_and_named_attendee_is_not_self_only():
    assert contains_self_only_attendee_phrase("只有我本人和张三参加") is False


@pytest.mark.parametrize("value", ["参会人只有我", "参会人：仅我", "参会人员为当前用户本人。"])
def test_labeled_self_only_attendee_phrase_is_self_only(value):
    assert contains_self_only_attendee_phrase(value) is True


def test_request_validation_requires_business_fields():
    result = validate_meeting_request(MeetingBookingRequest())
    assert result.valid is False
    assert {"subject", "start_time", "end_time", "attendees"} <= set(result.missing_fields)


def test_meeting_policy_accepts_quarter_hour_intervals_up_to_eight_hours():
    request = MeetingBookingRequest(
        subject="评审", start_time=datetime(2026, 7, 22, 14, 15),
        end_time=datetime(2026, 7, 22, 15, 45), attendee_user_ids=[1],
    )
    result = validate_meeting_request(request)
    assert result.valid is True
    assert result.errors == []


def test_meeting_policy_rejects_non_quarter_hour_and_overnight_intervals():
    request = MeetingBookingRequest(
        subject="评审", start_time=datetime(2026, 7, 22, 23, 45),
        end_time=datetime(2026, 7, 23, 0, 15), attendee_user_ids=[1],
    )
    result = validate_meeting_request(request)
    assert result.valid is False
    assert "会议室预约暂不支持跨天" in result.errors
