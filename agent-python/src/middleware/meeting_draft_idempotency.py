"""Prevent duplicate meeting-draft Tool Calls from losing the first result."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from ..services.meeting_draft_idempotency import current_meeting_draft_replay
from ..tools.common.contracts import tool_success


CREATE_DRAFT_TOOL_NAME = "create_meeting_booking_draft"


def _message_type(message: Any) -> str:
    value = getattr(message, "type", None)
    if isinstance(message, dict):
        value = message.get("type") or message.get("role")
    return str(value or "").lower()


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    calls = getattr(message, "tool_calls", None)
    if isinstance(message, dict):
        calls = message.get("tool_calls")
    return [call for call in (calls or []) if isinstance(call, dict)]


def _ignored_duplicate(call_id: str) -> ToolMessage:
    content = tool_success({
        "ignored": True,
        "idempotent": True,
        "message": "同一条 AIMessage 已放行第一个 create_meeting_booking_draft；重复调用已忽略，继续使用第一个结果。",
    }).to_tool_content()
    return ToolMessage(
        content=content,
        tool_call_id=call_id,
        name=CREATE_DRAFT_TOOL_NAME,
        status="success",
        response_metadata={
            "guard": "meeting_draft_idempotency",
            "reason": "duplicate_in_same_ai_message",
            "blockedBeforeHandler": True,
        },
    )


def _replayed(call_id: str, data: dict[str, Any]) -> ToolMessage:
    return ToolMessage(
        content=tool_success(data).to_tool_content(),
        tool_call_id=call_id,
        name=CREATE_DRAFT_TOOL_NAME,
        status="success",
        response_metadata={
            "guard": "meeting_draft_idempotency",
            "reason": "replay_current_message_and_run",
            "blockedBeforeHandler": True,
        },
    )


def _idempotency_update(state: dict[str, Any]) -> dict[str, Any] | None:
    messages = list(state.get("messages") or [])
    if not messages or _message_type(messages[-1]) != "ai":
        return None
    calls = [call for call in _tool_calls(messages[-1]) if call.get("name") == CREATE_DRAFT_TOOL_NAME]
    if not calls:
        return None

    replay = current_meeting_draft_replay()
    if replay:
        # The durable result already exists.  No call in this model response
        # may reach save_meeting_draft, including the first call of a batch.
        return {"messages": [_replayed(str(call.get("id") or f"replay-{index}"), replay)
                              for index, call in enumerate(calls)]}

    # With no persisted result, exactly the first call is allowed to reach the
    # Tool node.  LangGraph pairs these ToolMessages with the later calls and
    # executes only the remaining unpaired first call.
    duplicates = calls[1:]
    if not duplicates:
        return None
    return {"messages": [_ignored_duplicate(str(call.get("id") or f"duplicate-{index}"))
                          for index, call in enumerate(duplicates, start=1)]}


class MeetingDraftIdempotencyMiddleware(AgentMiddleware):
    """Handle duplicate draft calls without generic limit errors."""

    name = "MeetingDraftIdempotencyMiddleware"

    def after_model(self, state, runtime):
        return _idempotency_update(state)

    async def aafter_model(self, state, runtime):
        return _idempotency_update(state)
