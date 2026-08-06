"""Meeting follow-up recovery bound to authorized working-memory facts."""

from __future__ import annotations

from typing import Any

from ..patterns import (
    BOOKING_ID_IN_MESSAGE,
    MEETING_CANCEL_FOLLOW_UP,
    MEETING_ORDINAL,
    MEETING_UPDATE_FOLLOW_UP,
)


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


__all__ = ["meeting_follow_up_plan"]
