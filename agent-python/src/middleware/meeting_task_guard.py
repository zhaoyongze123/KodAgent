"""Prevent duplicate meeting sub-agent launches in one user turn.

DeepAgents exposes synchronous sub-agents through its generated ``task`` Tool.
The meeting sub-agent has its own Tool limits, but those counters are rebuilt
when the parent invokes it again.  This middleware guards the parent boundary
using the current message boundary, so it does not affect other domains or a
new user turn.
"""

from __future__ import annotations

import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ..tools.common.events import current_agent_context, turn_id_from_context


_MEETING_MARKERS = re.compile(r"会议室|预约会议|预约.*会议|参会人|会议安排|meeting_rooms_agent", re.I)


def _message_type(message: Any) -> str:
    value = getattr(message, "type", None)
    if isinstance(message, dict):
        value = message.get("type") or message.get("role")
    return str(value or "").lower()


def _message_content(message: Any) -> str:
    value = getattr(message, "content", "")
    if isinstance(message, dict):
        value = message.get("content", "")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(
            str(item.get("text", "")) if isinstance(item, dict) else str(item)
            for item in value
        )
    return str(value or "")


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    calls = getattr(message, "tool_calls", None)
    if isinstance(message, dict):
        calls = message.get("tool_calls")
    return [call for call in (calls or []) if isinstance(call, dict)]


def _is_meeting_task(call: dict[str, Any]) -> bool:
    args = call.get("args") or {}
    if not isinstance(args, dict):
        return bool(_MEETING_MARKERS.search(str(args)))
    text = " ".join(
        str(args.get(key) or "")
        for key in ("subagent_type", "subagentType", "description", "task")
    )
    return bool(_MEETING_MARKERS.search(text))


def _latest_user_index(messages: list[Any]) -> int:
    for index in range(len(messages) - 1, -1, -1):
        if _message_type(messages[index]) in {"human", "user"}:
            return index
    return -1


def _guard_task_calls(state: dict[str, Any]) -> dict[str, Any] | None:
    messages = list(state.get("messages") or [])
    if not messages:
        return None
    current_user_index = _latest_user_index(messages)
    if current_user_index < 0:
        return None
    current_user_text = _message_content(messages[current_user_index])
    # A meeting task launched from a non-meeting user turn is not restricted.
    # The subagent_type marker is preferred, while the text fallback supports
    # providers that omit structured args during streaming.
    meeting_turn = bool(_MEETING_MARKERS.search(current_user_text))
    last = messages[-1]
    current_calls = _tool_calls(last)
    if _message_type(last) != "ai" or not current_calls:
        return None

    previous_meeting_tasks = 0
    for message in messages[current_user_index + 1 : -1]:
        previous_meeting_tasks += sum(
            1 for call in _tool_calls(message)
            if call.get("name") == "task" and _is_meeting_task(call)
        )

    blocked: list[ToolMessage] = []
    for call in current_calls:
        args = call.get("args") or {}
        # Structured task calls identify their domain through subagent_type.
        # Only fall back to the user-turn domain when a provider omitted the
        # entire args object; this avoids treating an approvals task as a
        # meeting task merely because the user message mentions a meeting.
        inferred_meeting = _is_meeting_task(call) or (meeting_turn and not args)
        if call.get("name") != "task" or not inferred_meeting:
            continue
        context = current_agent_context()
        turn_id = turn_id_from_context(context)
        if previous_meeting_tasks >= 1:
            blocked.append(
                ToolMessage(
                    content=(
                        "当前用户轮次已重复进入会议子 Agent，已阻止继续循环调用。"
                        "请使用最新结构化结果继续，或明确说明仍缺少的字段；"
                        "不要要求用户重复发送同一条指令。"
                    ),
                    tool_call_id=str(call.get("id") or "task"),
                    name="task",
                    status="error",
                    response_metadata={
                        "guard": "meeting_task_once_per_message",
                        "domain": "meeting_booking",
                        "guardKey": f"{context.get('runId')}:{turn_id}:meeting_booking",
                        "runId": context.get("runId"),
                        "messageId": context.get("messageId") or turn_id,
                    },
                )
            )
        else:
            previous_meeting_tasks += 1

    if not blocked:
        return None
    return {"messages": blocked}


class MeetingTaskCallGuardMiddleware(AgentMiddleware):
    """Limit only meeting ``task`` calls within the current user turn."""

    name = "MeetingTaskCallGuardMiddleware"

    def after_model(self, state, runtime):
        return _guard_task_calls(state)

    async def aafter_model(self, state, runtime):
        return _guard_task_calls(state)
