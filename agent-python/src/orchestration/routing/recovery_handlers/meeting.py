"""Meeting follow-up recovery bound to authorized working-memory facts."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..patterns import (
    BOOKING_ID_IN_MESSAGE,
    MEETING_CANCEL_FOLLOW_UP,
    MEETING_ORDINAL,
    MEETING_UPDATE_FOLLOW_UP,
    DATE_QUERY,
)


def meeting_query_target_range(
    message: str,
    *,
    now: datetime | None = None,
) -> tuple[str, str] | None:
    """Resolve a bounded time range for an already selected meeting query."""
    text = str(message or "")
    if not re.search(r"会议室|会议预约|会议安排|已有预约|可用会议", text):
        return None
    if re.search(r"订|预订|预约一间|创建|安排一个|新建", text) and not re.search(r"查询|查看|有没有|哪些|空闲|已被预约", text):
        return None
    current = (now or datetime.now(ZoneInfo("Asia/Shanghai"))).date()
    date_match = DATE_QUERY.search(text)
    if date_match:
        target = f"{int(date_match.group('year')):04d}-{int(date_match.group('month')):02d}-{int(date_match.group('day')):02d}"
    else:
        offsets = {"前天": -2, "昨天": -1, "今天": 0, "明天": 1, "后天": 2}
        phrase = next((item for item in offsets if item in text), None)
        if phrase is not None:
            target = (current + timedelta(days=offsets[phrase])).isoformat()
        else:
            weekday = re.search(r"(?:下周|下星期)([一二三四五六日天])", text)
            if weekday:
                index = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}[weekday.group(1)]
                monday = current + timedelta(days=7 - current.weekday())
                target = (monday + timedelta(days=index)).isoformat()
            else:
                return None
    if re.search(r"上午", text):
        return f"{target} 09:00:00", f"{target} 12:00:00"
    if re.search(r"下午", text):
        return f"{target} 13:00:00", f"{target} 18:00:00"
    if re.search(r"晚上|晚间", text):
        return f"{target} 18:00:00", f"{target} 22:00:00"
    return f"{target} 00:00:00", f"{target} 23:59:59"


def normalize_meeting_query_candidate(
    message: str,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Fill a selected meeting query with a trusted relative-date range."""
    target_range = meeting_query_target_range(message, now=now)
    if target_range is None:
        return None
    candidate = dict(candidate_plan or {})
    intent = dict(query_intent or {})
    normalized = {**candidate, **intent, "operation": "QUERY", "action_id": "meeting.query"}
    start = str(normalized.get("start_time") or normalized.get("startTime") or "").strip()
    end = str(normalized.get("end_time") or normalized.get("endTime") or "").strip()
    if start and end:
        target_date = target_range[0][:10]
        normalized["start_time"] = f"{target_date}{start[10:]}" if len(start) >= 10 else target_range[0]
        normalized["end_time"] = f"{target_date}{end[10:]}" if len(end) >= 10 else target_range[1]
    else:
        normalized["start_time"], normalized["end_time"] = target_range
    normalized.pop("startTime", None)
    normalized.pop("endTime", None)
    normalized.pop("date", None)
    return normalized


def meeting_metadata_fallback_plan(message: str) -> dict[str, Any] | None:
    target_range = meeting_query_target_range(message)
    if target_range is None:
        return None
    return {
        "capability_id": "meeting",
        "execution_class": "metadata_query",
        "candidate_plan": {
            "action_id": "meeting.query",
            "operation": "QUERY",
            "start_time": target_range[0],
            "end_time": target_range[1],
        },
    }


def recover_meeting_write_action(
    message: str,
    current_action_id: str | None,
) -> str | None:
    """Repair an obvious meeting write verb when the model chose a read.

    The helper only changes the action within the already selected meeting
    capability and never supplies a target ID or authorization marker.
    """
    text = str(message or "")
    action = str(current_action_id or "").strip()
    if re.search(r"取消|撤销|删除", text) and not re.search(r"有没有|哪些|查询|查看|列表|记录", text):
        return "meeting.cancel" if action != "meeting.cancel" else None
    if re.search(r"修改|改到|改成|换成|调整|变更", text):
        # An already-correct ``meeting.update`` selection is still a terminal
        # decision here.  Falling through lets the generic ``预约`` creation
        # expression overwrite it for input such as “把预约 40 改到下午四点”.
        return "meeting.update"
    # ``预约会议室`` is the ordinary creation expression.  The previous
    # pattern only accepted its longer variant ``预约一间会议室``; when a
    # provider incorrectly selected ``meeting.query``, the recovery boundary
    # therefore let a booking request compile into a completed read plan.
    # Keep the read-intent exclusion so requests such as "查询预约记录" remain
    # reads rather than being rewritten merely because they contain 预约.
    if re.search(
        r"(?:预约(?!\s*(?:编号|号))|预订|订(?:一(?:间|个))?|创建|安排一个|新建)",
        text,
    ) and not re.search(r"有没有|哪些|查询|查看|列表|记录", text):
        return "meeting.create" if action != "meeting.create" else None
    return None


def meeting_follow_up_plan(message: str, memory: Any) -> dict[str, Any] | None:
    """Bind an update/cancel follow-up to an authorized query fact.

    This is not a keyword route for arbitrary requests.  It is a state
    invariant: only a message that expresses a write action *and* follows a
    meeting query with an authorized candidate can enter the meeting CRUD
    workflow. Ambiguous candidates stop at clarification instead of falling
    through to the ReAct child.
    """
    if memory is None:
        return None
    text = str(message or "").strip()
    operation = None
    if MEETING_CANCEL_FOLLOW_UP.search(text):
        operation = "CANCEL"
    elif MEETING_UPDATE_FOLLOW_UP.search(text):
        operation = "UPDATE"
    if operation is None:
        return None
    facts = memory.facts if isinstance(getattr(memory, "facts", None), dict) else {}
    query = facts.get("meeting_query")
    # A booking id in the user's message is only a reference candidate.  It
    # becomes an authorized write target after it is found in the latest
    # Java-backed query projection.  Without that projection this recovery
    # handler must not manufacture authorization from prose alone.
    if not isinstance(query, dict):
        return None
    candidates: list[dict[str, Any]] = []
    raw = query.get("editableCandidates") or []
    candidates = [item for item in raw if isinstance(item, dict) and item.get("bookingId") is not None]
    source_id = None
    explicit = BOOKING_ID_IN_MESSAGE.search(text)
    if explicit:
        proposed = int(explicit.group(1))
        if any(int(item["bookingId"]) == proposed for item in candidates):
            source_id = proposed
        else:
            return {
                "status": "CLARIFY",
                "operation": operation,
                "message": "指定的会议预约编号不在当前可编辑查询结果中，请先重新查询或选择列表中的预约。",
                "options": [],
            }
    else:
        ordinal = MEETING_ORDINAL.search(text)
        if ordinal:
            index = int(ordinal.group(1)) - 1
            if 0 <= index < len(candidates):
                source_id = int(candidates[index]["bookingId"])
        if source_id is None and len(candidates) == 1:
            source_id = int(candidates[0]["bookingId"])
        elif source_id is None and len(candidates) > 1:
            return {
                "status": "CLARIFY",
                "operation": operation,
                "message": "当前查询结果中有多条可编辑会议，请先指定预约编号。",
                "options": [
                    {
                        "bookingId": item.get("bookingId"),
                        "subject": item.get("subject"),
                        "startTime": item.get("startTime"),
                        "endTime": item.get("endTime"),
                    }
                    for item in candidates
                ],
            }
    if source_id is None:
        return {
            "status": "CLARIFY",
            "operation": operation,
            "message": "查询结果中没有可由您修改或取消的本人会议预约。",
            "options": [],
        }
    if source_id is None:
        return None
    return {
        "status": "RESOLVED",
        "operation": operation,
        "source_booking_id": source_id,
        "_authorized_source_fields": ["source_booking_id"],
    }


__all__ = [
    "meeting_follow_up_plan",
    "meeting_metadata_fallback_plan",
    "meeting_query_target_range",
    "normalize_meeting_query_candidate",
    "recover_meeting_write_action",
]
