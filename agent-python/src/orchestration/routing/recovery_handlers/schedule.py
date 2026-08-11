"""Personal-schedule recovery bound to authorized calendar facts."""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..patterns import (
    DATE_QUERY,
    SCHEDULE_CANCEL_FOLLOW_UP,
    SCHEDULE_ID_IN_MESSAGE,
    SCHEDULE_ORDINAL,
    SCHEDULE_UPDATE_FOLLOW_UP,
)


def schedule_follow_up_plan(message: str, memory: Any) -> dict[str, Any] | None:
    """Bind a schedule write to the preceding Java-authorized calendar read."""
    if memory is None:
        return None
    text = str(message or "").strip()
    if re.search(r"会议|预约", text) and "日程" not in text:
        return None
    if SCHEDULE_CANCEL_FOLLOW_UP.search(text):
        operation = "CANCEL"
    elif SCHEDULE_UPDATE_FOLLOW_UP.search(text):
        operation = "UPDATE"
    else:
        return None
    facts = memory.facts if isinstance(getattr(memory, "facts", None), dict) else {}
    query = facts.get("schedule_query")
    if not isinstance(query, dict):
        return None
    raw = query.get("editableCandidates") or []
    candidates = [
        item for item in raw
        if isinstance(item, dict) and item.get("sourceType") == "PERSONAL_SCHEDULE"
        and bool(item.get("editable")) and item.get("sourceId") is not None
    ]
    source_id = None
    explicit = SCHEDULE_ID_IN_MESSAGE.search(text)
    if explicit:
        proposed = int(explicit.group(1))
        if any(int(item["sourceId"]) == proposed for item in candidates):
            source_id = proposed
        else:
            return {
                "status": "CLARIFY",
                "operation": operation,
                "message": "指定的日程编号不在当前可编辑查询结果中，请先重新查询或选择列表中的日程。",
                "options": [],
            }
    else:
        ordinal = SCHEDULE_ORDINAL.search(text)
        if ordinal:
            index = int(ordinal.group(1)) - 1
            if 0 <= index < len(candidates):
                source_id = int(candidates[index]["sourceId"])
        if source_id is None and len(candidates) == 1:
            source_id = int(candidates[0]["sourceId"])
        elif source_id is None and len(candidates) > 1:
            return {
                "status": "CLARIFY",
                "operation": operation,
                "message": "当前查询结果中有多条可编辑个人日程，请先指定日程编号。",
                "options": [
                    {
                        "sourceScheduleId": item.get("sourceId"),
                        "title": item.get("title"),
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
            "message": "查询结果中没有可由您修改或取消的个人日程。",
            "options": [],
        }
    return {
        "status": "RESOLVED",
        "operation": operation,
        "source_schedule_id": source_id,
        "_authorized_source_fields": ["source_schedule_id"],
    }


_SCHEDULE_WRITE_WORDS = r"创建|新增|修改|更改|取消|删除|撤销"


def schedule_query_target_range(
    message: str,
    *,
    now: datetime | None = None,
) -> tuple[str, str] | None:
    """Resolve a bounded calendar range from the trusted business clock.

    This is a typed recovery helper for a selected personal-calendar query.
    It does not choose a capability or action from arbitrary prose; callers
    use it only at the schedule query boundary.
    """
    text = str(message or "")
    personal_schedule_query = re.search(
        r"日程|日历|我有什么安排|我的安排|个人安排",
        text,
    )
    if not personal_schedule_query or re.search(_SCHEDULE_WRITE_WORDS, text):
        return None
    match = DATE_QUERY.search(text)
    if match:
        target = f"{int(match.group('year')):04d}-{int(match.group('month')):02d}-{int(match.group('day')):02d}"
        return target, target

    current = (now or datetime.now(ZoneInfo("Asia/Shanghai"))).date()
    relative_offsets = {
        "前天": -2,
        "昨天": -1,
        "今天": 0,
        "明天": 1,
        "后天": 2,
    }
    phrase = next((item for item in relative_offsets if item in text), None)
    if phrase is not None:
        target = (current + timedelta(days=relative_offsets[phrase])).isoformat()
        return target, target

    if re.search(r"本周|这周|本星期|这星期", text):
        start = current - timedelta(days=current.weekday())
        return start.isoformat(), (start + timedelta(days=6)).isoformat()

    if re.search(r"下周|下星期", text) and not re.search(r"下周[一二三四五六日天]", text):
        start = current + timedelta(days=7 - current.weekday())
        return start.isoformat(), (start + timedelta(days=6)).isoformat()

    if re.search(r"本月|这个月|当月", text):
        start = current.replace(day=1)
        end = current.replace(day=monthrange(current.year, current.month)[1])
        return start.isoformat(), end.isoformat()

    if re.search(r"下个月|下月", text):
        year = current.year + (1 if current.month == 12 else 0)
        month = 1 if current.month == 12 else current.month + 1
        start = current.replace(year=year, month=month, day=1)
        end = start.replace(day=monthrange(year, month)[1])
        return start.isoformat(), end.isoformat()

    weekday = re.search(r"(?:下周|下星期)([一二三四五六日天])", text)
    if not weekday:
        return None
    weekday_index = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}[weekday.group(1)]
    next_monday = current + timedelta(days=(7 - current.weekday()))
    target = (next_monday + timedelta(days=weekday_index)).isoformat()
    return target, target


def schedule_query_target_date(
    message: str,
    *,
    now: datetime | None = None,
) -> str | None:
    """Return a single target date for legacy one-day callers."""
    target_range = schedule_query_target_range(message, now=now)
    if target_range is None or target_range[0] != target_range[1]:
        return None
    return target_range[0]


def _replace_calendar_date(value: str, target_date: str) -> str | None:
    match = re.match(r"^\d{4}-\d{2}-\d{2}(?P<suffix>.*)$", str(value or "").strip())
    if not match:
        return None
    return f"{target_date}{match.group('suffix')}"


def normalize_schedule_query_candidate(
    message: str,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Recover a range only when the provider omitted all typed time fields.

    Model-proposed ``date``, explicit intervals and ``time_range`` are valid
    contracts. They must reach the compiler unchanged; this textual parser is
    solely a compatibility recovery for an empty provider envelope.
    """
    candidate = dict(candidate_plan) if isinstance(candidate_plan, dict) else {}
    intent = dict(query_intent) if isinstance(query_intent, dict) else {}
    normalized = {**candidate, **intent}
    operation = str(normalized.get("operation") or normalized.get("action") or "").strip().upper()
    operation = {"LIST": "QUERY", "SEARCH": "QUERY", "CALENDAR": "QUERY"}.get(operation, operation)
    if operation != "QUERY":
        return None
    time_keys = ("date", "start_time", "end_time", "startTime", "endTime", "time_range", "timeRange")
    if any(key in normalized and normalized.get(key) not in (None, "", {}, []) for key in time_keys):
        return None
    target_range = schedule_query_target_range(message, now=now)
    if target_range is None:
        return None
    normalized["entity"] = "personal_schedule"
    normalized["operation"] = "QUERY"
    normalized["action_id"] = "schedule.query"
    if target_range[0] == target_range[1]:
        normalized["date"] = target_range[0]
    else:
        normalized["start_time"] = f"{target_range[0]} 00:00:00"
        normalized["end_time"] = f"{target_range[1]} 23:59:59"
    return normalized


def schedule_metadata_fallback_plan(message: str) -> dict[str, Any] | None:
    """Recover an explicit one-day calendar read when a provider emits ``{}``."""
    target_range = schedule_query_target_range(message)
    if target_range is None:
        return None
    if target_range[0] == target_range[1]:
        candidate_plan = {
            "action_id": "schedule.query",
            "operation": "QUERY",
            "schedule_type": "personal",
            "date": target_range[0],
        }
    else:
        candidate_plan = {
            "action_id": "schedule.query",
            "operation": "QUERY",
            "schedule_type": "personal",
            "start_time": f"{target_range[0]} 00:00:00",
            "end_time": f"{target_range[1]} 23:59:59",
        }
    return {
        "capability_id": "schedule",
        "execution_class": "metadata_query",
        "candidate_plan": candidate_plan,
    }


__all__ = [
    "normalize_schedule_query_candidate",
    "schedule_follow_up_plan",
    "schedule_metadata_fallback_plan",
    "schedule_query_target_date",
    "schedule_query_target_range",
]
