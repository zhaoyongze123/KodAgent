"""Resolve and validate natural-language meeting request fields.

This module deliberately does not decide whether a room or calendar is free.
That remains the responsibility of the existing read-only business Tools.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any

from ..tools.common import AGENT_TIMEZONE
from ..domain.meeting import MeetingBookingRequest, RequestValidation
from .meeting_policy import validate_interval


class MeetingRequestError(ValueError):
    """A user-facing request parsing or validation error."""


_WEEKDAYS = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6,
    "天": 6,
}

_CHINESE_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
                   "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}

# These are self references, not directory-search keywords.  The model may
# paraphrase the user's wording, so keep the list deliberately broader than
# the exact phrase used in the prompt.  They all resolve to the same canonical
# value before request keys are built and before any Java user lookup happens.
_SELF_REFERENT_PATTERN = (
    r"(?:当前用户本人|用户本人|本用户|我本人|当前用户|我|本人|自己|申请人|操作者)"
)

SELF_REFERENTS = frozenset({
    "我", "本人", "自己", "我本人", "当前用户", "用户", "用户本人", "发起人",
    "当前用户本人", "本用户", "申请人", "操作者",
    # OpenAI-compatible providers sometimes emit a typed English marker for
    # the user's self-only attendee constraint.  It is a transport alias, not
    # a directory name, and must resolve through the authenticated /me path.
    "only_current_user", "current_user_only", "only_me", "self_only", "current_user",
})

_SELF_ONLY_PATTERN = re.compile(
    r"^(?:仅有|只有|仅|只)?"
    + _SELF_REFERENT_PATTERN
    + r"(?:参加会议|参会会议|参加|参会|出席|参与)?$"
)
_SELF_ONLY_PROSE_PATTERN = re.compile(
    r"(?:仅有|只有|仅|只)?"
    + _SELF_REFERENT_PATTERN
    + r"(?:参加会议|参会会议|参加|参会|出席|参与)"
    # Do not match the prefix of "只有我本人和张三参加".  That request has
    # more than one attendee and must continue through normal name resolution.
    r"(?![ \t]*(?:和|、|及|与))"
)
_SELF_ONLY_LABEL_PATTERN = re.compile(
    r"(?:参会人|参会人员|参加人|attendees?)\s*(?:是|为|[:：])?\s*"
    r"(?:仅有|只有|仅|只)?"
    + _SELF_REFERENT_PATTERN
    + r"\s*[。.!！]?$",
    re.IGNORECASE,
)
_NON_BUSINESS_ATTENDEE_LABELS = frozenset({
    "参加", "参会", "出席", "参与", "人员", "参会人", "参会人员",
})

# Conflict override is intentionally narrow.  Generic phrases such as
# "忽略冲突" are not sufficient because they could refer to a room conflict;
# room conflicts are never overridable.  The caller must also prove that the
# text came from the current real HumanMessage.
_ATTENDEE_CONFLICT_OVERRIDE_PATTERNS = (
    re.compile(r"(?:忽略|无视|不管|不考虑)(?:掉)?(?:参会人|参会人员|参加人|人员|用户)(?:的)?(?:日程|时间|安排)?冲突"),
    re.compile(r"(?:参会人|参会人员|参加人|人员|用户)(?:有|存在)(?:日程|时间|安排)?冲突(?:也|仍然)?(?:继续|照常|可以预约|也要预约)"),
    re.compile(r"(?:即使|即便|哪怕)(?:有)?(?:参会人|参会人员|参加人|人员|用户)(?:的)?(?:日程|时间|安排)?冲突(?:也|仍然)?(?:继续|照常|可以预约|也要预约)"),
)


def attendee_conflict_override_requested(message: str | None) -> bool:
    """Return whether *this user message* explicitly allows attendee conflicts.

    This is deliberately a pure allow-list decision.  It does not inspect AI
    messages, system prompts, model tool arguments, or previous turns; callers
    must provide the current HumanMessage text proven at the Agent boundary.
    """
    text = " ".join(str(message or "").split())
    return bool(text and any(pattern.search(text) for pattern in _ATTENDEE_CONFLICT_OVERRIDE_PATTERNS))


def authorized_current_user_message(
    state: dict[str, Any] | None,
    *,
    expected_message_id: str | None = None,
) -> str:
    """Return text only from the parent-proven current HumanMessage marker."""
    if not isinstance(state, dict):
        return ""
    marker = state.get("current_user_message")
    if (
        not isinstance(marker, dict)
        or marker.get("source") != "current_human_message"
        or marker.get("trusted") is not True
        or not str(marker.get("messageId") or "")
        or (
            expected_message_id is not None
            and str(marker.get("messageId") or "") != str(expected_message_id or "")
        )
    ):
        return ""
    text = marker.get("text")
    return text.strip() if isinstance(text, str) else ""


def normalize_attendee_name(value: object) -> str:
    """Normalize model paraphrases before resolving users.

    The model often turns ``只有我参加`` into an attendee value instead of
    preserving the user's exact words.  Strip only self-only speech wrappers;
    names containing another person remain real search keys.
    """
    text = " ".join(str(value or "").strip().split())
    text = text.strip("，,。；;：:")
    if _SELF_ONLY_PATTERN.fullmatch(text) or text in SELF_REFERENTS:
        return "当前用户"
    if text in _NON_BUSINESS_ATTENDEE_LABELS:
        return ""
    return text


def normalize_attendee_names(values: list[object] | None) -> list[str]:
    """Normalize and de-duplicate attendee labels while preserving order."""
    result: list[str] = []
    for value in values or []:
        normalized = normalize_attendee_name(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def contains_self_only_attendee_phrase(value: object) -> bool:
    """Return whether text explicitly describes the current user alone.

    The prose matcher requires an attendance verb and rejects a conjunction
    immediately after the self reference.  This keeps phrases such as
    ``只有我本人和张三参加`` out of the self-only path; ``张三`` must still
    be resolved as a real directory name.
    """
    text = " ".join(str(value or "").strip().split())
    if not text:
        return False
    return (
        normalize_attendee_name(text) == "当前用户"
        or bool(_SELF_ONLY_PROSE_PATTERN.search(text))
        or bool(_SELF_ONLY_LABEL_PATTERN.search(text))
    )


def _number(value: str) -> int:
    if value.isdigit():
        return int(value)
    if value == "十":
        return 10
    if value.startswith("十"):
        return 10 + _CHINESE_DIGITS.get(value[1:], 0)
    if value.endswith("十"):
        return _CHINESE_DIGITS.get(value[0], 0) * 10
    if len(value) == 2 and value[0] in _CHINESE_DIGITS and value[1] in _CHINESE_DIGITS:
        return _CHINESE_DIGITS[value[0]] * 10 + _CHINESE_DIGITS[value[1]]
    return _CHINESE_DIGITS.get(value, -1)


def _parse_date_expression(value: str, today: date) -> date | None:
    text = value.strip()
    match = re.search(r"(20\d{2})[-年](\d{1,2})[-月](\d{1,2})日?", text)
    if match:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    if re.search(r"今天", text):
        return today
    if re.search(r"明天", text):
        return today + timedelta(days=1)
    if re.search(r"后天", text):
        return today + timedelta(days=2)
    if re.search(r"昨天", text):
        return today - timedelta(days=1)
    weekday = re.search(r"(?:下周|下星期|下礼拜)([一二三四五六日天])", text)
    if weekday:
        target = _WEEKDAYS[weekday.group(1)]
        # Monday is the start of the business week: next Wednesday from a
        # Friday is five days away, not twelve.
        days = 7 - today.weekday() + target
        return today + timedelta(days=days)
    weekday = re.search(r"(?:本周|这周|星期|周)([一二三四五六日天])", text)
    if weekday:
        target = _WEEKDAYS[weekday.group(1)]
        days = (target - today.weekday()) % 7
        return today + timedelta(days=days)
    return None


def _parse_time_expression(value: str) -> time | None:
    text = value.strip()
    match = re.search(r"(?<!\d)([01]?\d|2[0-3])[:：]([0-5]\d)", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
    else:
        match = re.search(r"(上午|早上|早晨|中午|下午|晚上|晚间)?\s*([0-9一二两三四五六七八九十]{1,3})(?:点|时)(?:(\d{1,2})分?)?", text)
        if not match:
            return None
        period, hour_text, minute_text = match.groups()
        hour, minute = _number(hour_text), int(minute_text or 0)
        if period in {"下午", "晚上", "晚间"} and hour < 12:
            hour += 12
        if period == "中午" and hour < 11:
            hour += 12
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute)


def resolve_time_range(
    start_expression: str | None,
    end_expression: str | None = None,
    *,
    now: datetime | None = None,
) -> tuple[datetime | None, datetime | None, list[str], list[str]]:
    """Resolve common Chinese date/time expressions without guessing silently."""
    now = now or datetime.now(AGENT_TIMEZONE)
    start_text = (start_expression or "").strip()
    end_text = (end_expression or "").strip()
    # Accept a single value such as ``2026-07-22 14:00—16:00``.
    # Do not split the hyphens inside an ISO date.
    range_match = re.split(r"\s*(?:[—–]|至|到)\s*", start_text)
    if len(range_match) == 2 and not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", range_match[0]):
        start_text, end_text = range_match[0], range_match[1]

    start_date = _parse_date_expression(start_text, now.date())
    end_date = _parse_date_expression(end_text, now.date()) or start_date
    start_time = _parse_time_expression(start_text)
    end_time = _parse_time_expression(end_text)
    missing: list[str] = []
    errors: list[str] = []
    if start_date is None:
        missing.append("start_date")
    if start_time is None:
        missing.append("start_time")
    if end_time is None:
        missing.append("end_time")
    if missing:
        return None, None, missing, errors
    assert start_date and end_date and start_time and end_time
    start = datetime.combine(start_date, start_time, tzinfo=AGENT_TIMEZONE)
    end = datetime.combine(end_date, end_time, tzinfo=AGENT_TIMEZONE)
    if end <= start:
        errors.append("结束时间必须晚于开始时间")
    return start, end, missing, errors


def _user_id(user: dict[str, Any]) -> int | None:
    value = user.get("userId", user.get("id"))
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _user_name(user: dict[str, Any]) -> str:
    return str(user.get("userNickname") or user.get("nickname") or user.get("name") or "")


def resolve_attendee_results(
    requested_names: list[str],
    *,
    current_user: dict[str, Any] | None,
    search_results: dict[str, list[dict[str, Any]]],
) -> tuple[list[int], list[str], list[dict[str, Any]], list[str]]:
    """Convert attendee names to unique IDs and report ambiguity explicitly."""
    ids: list[int] = []
    names: list[str] = []
    candidates: list[dict[str, Any]] = []
    errors: list[str] = []
    for requested in requested_names:
        key = normalize_attendee_name(requested)
        if not key:
            continue
        if key == "当前用户":
            users = [current_user] if current_user else []
        else:
            users = search_results.get(key, [])
        if not users:
            errors.append(f"未找到参会人“{key}”")
            continue
        if len(users) > 1:
            candidates.extend(users)
            continue
        uid = _user_id(users[0])
        display_name = _user_name(users[0]) or key
        if uid is None:
            errors.append(f"参会人“{key}”缺少有效用户 ID")
            continue
        if uid not in ids:
            ids.append(uid)
            names.append(display_name)
    return ids, names, candidates, errors


def validate_meeting_request(request: MeetingBookingRequest) -> RequestValidation:
    missing: list[str] = []
    errors: list[str] = []
    if not request.subject or not request.subject.strip():
        missing.append("subject")
    if request.start_time is None:
        missing.append("start_time")
    if request.end_time is None:
        missing.append("end_time")
    if not request.attendee_user_ids:
        missing.append("attendees")
    errors.extend(validate_interval(request.start_time, request.end_time))
    errors = list(dict.fromkeys(errors))
    return RequestValidation(
        valid=not missing and not errors,
        missing_fields=missing,
        errors=errors,
        request=request,
    )
