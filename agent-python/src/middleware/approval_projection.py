"""Shared eligibility rules for projecting a durable draft into HITL.

The business service persists a draft/preview first.  The next model turn may
turn that *just-created* result into an official LangGraph interrupt.  A
pending row alone is deliberately insufficient: otherwise any later free-form
message (for example, ``确认``) could cause an old draft to re-enter the ReAct
loop and manufacture another confirmation call.

This module owns only the graph-side projection condition.  Java remains the
authority for the durable approval state and the confirmation tools still
validate an official resume before committing a business write.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from ..orchestration.delegated_receipt import (
    DelegatedMeetingDraftReceipt,
    parse_meeting_draft_receipt,
)


def _messages_from_request(request: Any) -> list[Any]:
    state = getattr(request, "state", None)
    if state is None and isinstance(request, dict):
        state = request.get("state")
    if not isinstance(state, dict):
        return []
    messages = state.get("messages") or []
    return list(messages) if isinstance(messages, Iterable) and not isinstance(messages, (str, bytes, dict)) else []


def _tool_name(message: Any) -> str:
    if isinstance(message, dict):
        return str(message.get("name") or message.get("tool_name") or "")
    return str(getattr(message, "name", None) or getattr(message, "tool_name", None) or "")


def _tool_succeeded(message: ToolMessage) -> bool:
    """Require an explicit successful draft/preview result when available.

    The tool name is the primary workflow fact.  Parsing the standard
    ``ToolResponse`` envelope adds defence against projecting a card after a
    failed draft call, while retaining compatibility with legacy tool messages
    whose content is not JSON.
    """
    content = message.get("content", "") if isinstance(message, dict) else message.content
    if not isinstance(content, str):
        return True
    try:
        payload = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return True
    if not isinstance(payload, dict):
        return True
    if payload.get("ok") is False:
        return False
    data = payload.get("data")
    if isinstance(data, dict) and data.get("status") not in (None, "DRAFT_READY"):
        # Workflow outcomes that are not a successful draft (NEEDS_INPUT,
        # FAILED, etc.) cannot open a confirmation boundary.
        return False
    return True


def _is_draft_ready_message(message: Any) -> bool:
    """Recognize a structured draft result even if message.name was lost.

    LangGraph Server can rehydrate a ToolMessage from a checkpoint without
    preserving the optional ``name`` attribute.  The durable result envelope
    still carries the authoritative ``data.status=DRAFT_READY`` marker, which
    is safe to use together with the pending Java/Redis approval binding.
    """
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    if not isinstance(content, str):
        return False
    try:
        payload = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    data = payload.get("data") if isinstance(payload, dict) else None
    return isinstance(data, dict) and str(data.get("status") or "").upper() == "DRAFT_READY"


def is_draft_projection_turn(request: Any, source_tools: set[str]) -> bool:
    """Whether this model call immediately follows an eligible draft tool.

    This is intentionally based on the current graph frame, not Redis or a
    historical thread scan.  A user message always becomes the last state
    message, so it cannot reopen a pending approval.  Checkpoint replay of
    the same draft frame remains safe: the later HITL predicate owns the
    exact durable marker and does not emit a second pause event.
    """
    messages = _messages_from_request(request)
    if not messages:
        return False
    last = messages[-1]
    is_tool_message = isinstance(last, ToolMessage) or isinstance(last, dict)
    if not is_tool_message or not _tool_succeeded(last):
        return False
    return _tool_name(last) in source_tools or _is_draft_ready_message(last)


def _tool_call_for_message(messages: list[Any], message: ToolMessage) -> dict[str, Any] | None:
    """Find the parent ToolCall that owns a ToolMessage.

    DeepAgents' generated ``task`` tool intentionally returns only a child
    agent's final text to the parent.  It creates the parent ``ToolMessage``
    without a name, so ``ToolMessage.name`` is not a reliable way to identify
    this gateway boundary.  The ToolCall id, however, is part of LangGraph's
    checkpoint contract and is preserved end-to-end.
    """
    tool_call_id = str(
        (message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", ""))
        or ""
    )
    if not tool_call_id:
        return None
    for previous in reversed(messages[:-1]):
        if not isinstance(previous, AIMessage) and not isinstance(previous, dict):
            continue
        calls = previous.get("tool_calls") if isinstance(previous, dict) else previous.tool_calls
        for call in calls or []:
            if isinstance(call, dict) and str(call.get("id") or "") == tool_call_id:
                return call
    return None


def is_delegated_draft_projection_turn(request: Any, delegate_agents: set[str]) -> bool:
    """Whether the immediate parent gateway result came from a draft-capable child.

    A child graph's internal ToolMessages never cross the generic DeepAgents
    ``task`` boundary; only its final text is returned.  Making the model's
    text the proof would be unsafe and brittle.  Instead this recognizes the
    *code-owned parent task result* by its ToolCall id and selected registered
    child type.  The approval middleware still loads and verifies the durable
    Java/Redis draft with the current tenant/user/thread/message binding before
    it injects an interrupt.  Thus a later user message, an arbitrary child
    narration, or an old PENDING draft can never mint a new card.
    """
    messages = _messages_from_request(request)
    if not messages or not (isinstance(messages[-1], ToolMessage) or isinstance(messages[-1], dict)):
        return False
    last = messages[-1]
    if not _tool_succeeded(last):
        return False
    call = _tool_call_for_message(messages, last)
    if not isinstance(call, dict) or str(call.get("name") or "") not in {"task", "task_tool"}:
        return False
    args = call.get("args") or {}
    if not isinstance(args, dict):
        return False
    return str(args.get("subagent_type") or args.get("subagentType") or "") in delegate_agents


def delegated_meeting_draft_receipt(request: Any) -> DelegatedMeetingDraftReceipt | None:
    """Return the validated receipt from the immediate meeting ``task`` result.

    The task call id proves which parent call owns the ToolMessage; the child
    type pins its domain; and the strict receipt schema proves the result was
    emitted by the meeting execution middleware.  No model-authored text and
    no pending-operation lookup participates in this decision.
    """
    messages = _messages_from_request(request)
    if not messages or not (isinstance(messages[-1], ToolMessage) or isinstance(messages[-1], dict)):
        return None
    last = messages[-1]
    if not _tool_succeeded(last):
        return None
    call = _tool_call_for_message(messages, last)
    if not isinstance(call, dict) or str(call.get("name") or "") not in {"task", "task_tool"}:
        return None
    args = call.get("args") or {}
    if not isinstance(args, dict):
        return None
    if str(args.get("subagent_type") or args.get("subagentType") or "") != "meeting_rooms_agent":
        return None
    content = last.get("content", "") if isinstance(last, dict) else last.content
    return parse_meeting_draft_receipt(content)


def is_delegated_meeting_draft_projection_turn(request: Any) -> bool:
    """Whether this frame contains one trusted meeting draft receipt."""
    return delegated_meeting_draft_receipt(request) is not None


__all__ = [
    "delegated_meeting_draft_receipt",
    "is_delegated_draft_projection_turn",
    "is_delegated_meeting_draft_projection_turn",
    "is_draft_projection_turn",
]
