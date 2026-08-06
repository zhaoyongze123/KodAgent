"""Personal-schedule recovery bound to authorized calendar facts."""

from __future__ import annotations

import re
from typing import Any

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


def schedule_metadata_fallback_plan(message: str) -> dict[str, Any] | None:
    """Recover an explicit one-day calendar read when a provider emits ``{}``."""
    text = str(message or "")
    if not re.search(r"日程|日历", text) or re.search(r"创建|新增|修改|更改|取消|删除|撤销", text):
        return None
    match = DATE_QUERY.search(text)
    if not match:
        return None
    target = f"{int(match.group('year')):04d}-{int(match.group('month')):02d}-{int(match.group('day')):02d}"
    return {
        "capability_id": "schedule",
        "execution_class": "metadata_query",
        "candidate_plan": {
            "action_id": "schedule.query",
            "operation": "QUERY",
            "schedule_type": "personal",
            "date": target,
        },
    }


__all__ = ["schedule_follow_up_plan", "schedule_metadata_fallback_plan"]
