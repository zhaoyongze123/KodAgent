"""Single source of truth for Agent meeting-booking time semantics.

The OA meeting table stores a concrete interval, not a recurrence rule.  The
Agent therefore accepts one same-day interval at 15-minute granularity,
between 15 minutes and 8 hours.  Repeated submissions are handled by the
durable draft idempotency key; an already active overlapping room booking is a
business conflict, never a silently duplicated booking.
"""

from __future__ import annotations

from datetime import datetime, timedelta

MIN_DURATION = timedelta(minutes=15)
MAX_DURATION = timedelta(hours=8)
SLOT_MINUTES = 15
ALLOW_CROSS_DAY = False
ALLOW_RECURRING = False


def validate_interval(start: datetime | None, end: datetime | None) -> list[str]:
    errors: list[str] = []
    if start is None or end is None:
        return errors
    if end <= start:
        errors.append("结束时间必须晚于开始时间")
        return errors
    if not ALLOW_CROSS_DAY and start.date() != end.date():
        errors.append("会议室预约暂不支持跨天")
    if start.second or end.second or start.minute % SLOT_MINUTES or end.minute % SLOT_MINUTES:
        errors.append("会议时间必须按 15 分钟粒度设置")
    duration = end - start
    if duration < MIN_DURATION or duration > MAX_DURATION or duration.total_seconds() % (SLOT_MINUTES * 60):
        errors.append("会议时长必须为 15 分钟至 8 小时，且按 15 分钟递增")
    return list(dict.fromkeys(errors))
