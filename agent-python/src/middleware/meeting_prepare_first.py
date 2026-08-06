"""Enforce prepare-before-booking tool ordering inside the meeting sub-agent."""

from __future__ import annotations

import json
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage


PREPARE_TOOL_NAME = "prepare_meeting_booking_request"
BOOKING_STEP_TOOL_NAMES = frozenset({
    "list_available_meeting_rooms",
    "get_meeting_attendees_calendar",
    "check_meeting_availability",
    "check_meeting_availability_batch",
    "create_meeting_booking_draft",
})


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    calls = getattr(message, "tool_calls", None)
    if isinstance(message, dict):
        calls = message.get("tool_calls")
    return [call for call in (calls or []) if isinstance(call, dict)]


def _message_type(message: Any) -> str:
    value = getattr(message, "type", None)
    if isinstance(message, dict):
        value = message.get("type") or message.get("role")
    return str(value or "").lower()


def _prepare_first_update(state: dict[str, Any]) -> dict[str, Any] | None:
    messages = list(state.get("messages") or [])
    if not messages or _message_type(messages[-1]) != "ai":
        return None
    calls = _tool_calls(messages[-1])
    if not calls or not any(call.get("name") == PREPARE_TOOL_NAME for call in calls):
        return None

    blocked_calls = [
        call for call in calls
        if call.get("name") in BOOKING_STEP_TOOL_NAMES
    ]
    if not blocked_calls:
        return None

    blocked_messages = [
        ToolMessage(
            content=json.dumps({
                "ok": False,
                "error": {
                    "code": "REQUEST_NOT_READY",
                    "message": "本轮必须先完成 prepare_meeting_booking_request；该并行调用已阻止，请等待 prepare 结果后再继续。",
                },
            }, ensure_ascii=False),
            tool_call_id=str(call.get("id") or f"blocked-{index}"),
            name=str(call.get("name") or "meeting_tool"),
            status="error",
            response_metadata={
                "guard": "meeting_prepare_first",
                "blockedBeforeHandler": True,
            },
        )
        for index, call in enumerate(blocked_calls)
    ]
    return {"messages": blocked_messages}


class MeetingPrepareFirstMiddleware(AgentMiddleware):
    """Allow prepare in a parallel batch but block every later booking Tool."""

    name = "MeetingPrepareFirstMiddleware"

    def after_model(self, state, runtime):
        return _prepare_first_update(state)

    async def aafter_model(self, state, runtime):
        return _prepare_first_update(state)
