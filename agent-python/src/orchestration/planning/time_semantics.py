"""Compile typed calendar semantics using the server business clock."""

from __future__ import annotations

from dataclasses import dataclass
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo


_BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")
_MAX_OFFSET_DAYS = 3660


@dataclass(frozen=True)
class TimeRangeResolution:
    start_time: str | None = None
    end_time: str | None = None
    error: str | None = None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _calendar_period(current: date, unit: str, offset: int) -> tuple[date, date] | None:
    if unit == "WEEK":
        start = current - timedelta(days=current.weekday()) + timedelta(days=offset * 7)
        return start, start + timedelta(days=6)
    if unit == "MONTH":
        month_index = current.year * 12 + (current.month - 1) + offset
        year, month_zero = divmod(month_index, 12)
        if not (1 <= year <= 9999):
            return None
        month = month_zero + 1
        start = date(year, month, 1)
        return start, date(year, month, monthrange(year, month)[1])
    return None


def resolve_schedule_time_range(
    value: Any,
    *,
    now: datetime | None = None,
) -> TimeRangeResolution:
    """Resolve the ``schedule.query.time_range`` contract to a closed interval.

    The model supplies *meaning*, never a guessed calendar date.  Calendar
    periods describe an aligned business-calendar interval, for example:

    ``{"kind":"CALENDAR_PERIOD", "unit":"WEEK", "offset":0,
    "precision":"DAY"}``

    This is the current Monday-through-Sunday calendar week.  ``offset`` is
    negative for prior periods and positive for following periods.  A sliding
    range uses a date-relative shape instead:

    ``{"kind":"RELATIVE", "anchor":"CURRENT_DATE", "precision":"DAY",
    "start_offset_days":-6, "end_offset_days":0}``

    This represents the most recent seven calendar days (inclusive).  The
    server's Asia/Shanghai business date is the sole anchor and the result is
    always an explicit ``yyyy-MM-dd HH:mm:ss`` interval for the executor.
    """
    if not isinstance(value, dict):
        return TimeRangeResolution(error="time_range 必须是对象")
    kind = str(value.get("kind") or "").strip().upper()
    anchor = str(value.get("anchor") or "").strip().upper()
    precision = str(value.get("precision") or "").strip().upper()
    start_offset = _integer(value.get("start_offset_days"))
    end_offset = _integer(value.get("end_offset_days"))
    current = (now.astimezone(_BUSINESS_TIMEZONE) if now and now.tzinfo else now or datetime.now(_BUSINESS_TIMEZONE)).date()
    if precision != "DAY":
        return TimeRangeResolution(error="time_range.precision 必须为 DAY")
    if kind == "CALENDAR_PERIOD":
        unit = str(value.get("unit") or "").strip().upper()
        offset = _integer(value.get("offset"))
        if unit not in {"WEEK", "MONTH"}:
            return TimeRangeResolution(error="CALENDAR_PERIOD 的 time_range.unit 必须为 WEEK 或 MONTH")
        if offset is None or abs(offset) > 1200:
            return TimeRangeResolution(error="CALENDAR_PERIOD 的 time_range.offset 必须是范围内的整数")
        calendar_range = _calendar_period(current, unit, offset)
        if calendar_range is None:
            return TimeRangeResolution(error="time_range 无法解析到有效日历区间")
        start_date, end_date = calendar_range
    elif kind == "RELATIVE":
        if anchor != "CURRENT_DATE":
            return TimeRangeResolution(error="RELATIVE 的 time_range.anchor 必须为 CURRENT_DATE")
        if start_offset is None or end_offset is None:
            return TimeRangeResolution(error="RELATIVE 的 time_range 必须提供整数 start_offset_days 和 end_offset_days")
        if abs(start_offset) > _MAX_OFFSET_DAYS or abs(end_offset) > _MAX_OFFSET_DAYS:
            return TimeRangeResolution(error=f"time_range 偏移天数必须在 -{_MAX_OFFSET_DAYS} 到 {_MAX_OFFSET_DAYS} 之间")
        if end_offset < start_offset:
            return TimeRangeResolution(error="time_range.end_offset_days 不能早于 start_offset_days")
        start_date = current + timedelta(days=start_offset)
        end_date = current + timedelta(days=end_offset)
    else:
        return TimeRangeResolution(error="time_range.kind 必须为 CALENDAR_PERIOD 或 RELATIVE")
    return TimeRangeResolution(
        start_time=f"{start_date.isoformat()} 00:00:00",
        end_time=f"{end_date.isoformat()} 23:59:59",
    )


__all__ = ["TimeRangeResolution", "resolve_schedule_time_range"]
