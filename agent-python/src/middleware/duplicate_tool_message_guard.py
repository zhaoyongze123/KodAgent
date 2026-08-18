"""Filter duplicate placeholder ToolMessages before provider submission.

The agent-chat-ui frontend injects ``do-not-render-*`` placeholder
ToolMessages via ``ensureToolCallsHaveResponses`` when it suspects an AI
tool call lacks a following ToolMessage. If the real ToolMessage response
exists elsewhere in the message stream (e.g. due to streaming event
ordering), the placeholder becomes a *duplicate* response for the same
``tool_call_id``, which causes OpenAI-compatible providers to reject the
request with "tool messages must be preceded by a tool call message".

This middleware strips placeholder ToolMessages whose ``tool_call_id``
already has a real (non-placeholder) ToolMessage response in the request.
It operates on the model-request copy only — checkpoint state is untouched.
"""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

_DO_NOT_RENDER_PREFIX = "do-not-render-"


def _is_placeholder(message: ToolMessage) -> bool:
    msg_id = getattr(message, "id", None) or ""
    return isinstance(msg_id, str) and msg_id.startswith(_DO_NOT_RENDER_PREFIX)


def _filter_duplicate_placeholders(messages: list) -> list:
    """Remove placeholder ToolMessages that duplicate a real response."""
    real_tool_call_ids: set[str] = set()
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        if _is_placeholder(msg):
            continue
        tcid = getattr(msg, "tool_call_id", None)
        if tcid:
            real_tool_call_ids.add(tcid)

    if not real_tool_call_ids:
        return messages

    filtered = [
        msg
        for msg in messages
        if not (isinstance(msg, ToolMessage) and _is_placeholder(msg) and getattr(msg, "tool_call_id", None) in real_tool_call_ids)
    ]
    return filtered


class DuplicateToolMessageGuardMiddleware(AgentMiddleware):
    """Strip duplicate ``do-not-render-*`` ToolMessages before model calls."""

    name = "DuplicateToolMessageGuardMiddleware"

    def wrap_model_call(self, request, handler):
        filtered = _filter_duplicate_placeholders(list(request.messages))
        if len(filtered) == len(request.messages):
            return handler(request)
        return handler(request.override(messages=filtered))

    async def awrap_model_call(self, request, handler):
        filtered = _filter_duplicate_placeholders(list(request.messages))
        if len(filtered) == len(request.messages):
            return await handler(request)
        return await handler(request.override(messages=filtered))
