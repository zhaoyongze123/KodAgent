"""Prepare trusted confirmation arguments for DeepAgents' official HITL layer."""

from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

from ..services.meeting_approval import (
    PendingApprovalContext,
    confirmation_card_args,
    load_confirmation_context,
    load_pending_approval_context,
)
from ..services.approval_core import PROJECTION_METADATA_KEY, approval_projection_metadata
from ..workflows.registry import confirmation_route
from .approval_projection import is_delegated_draft_projection_turn, is_draft_projection_turn
from ..hitl.auto_confirm import ConfiguredApprovalProjectionMiddleware


CONFIRM_TOOL_NAME = (confirmation_route("meeting_booking") or {}).get(
    "toolName", "confirm_meeting_booking"
)

_DRAFT_SOURCE_TOOLS = {
    "create_meeting_booking_draft",
    "create_meeting_booking_cancellation_draft",
    "run_meeting_booking_workflow",
}
_DRAFT_DELEGATE_AGENTS = {"meeting_rooms_agent"}


def _replace_response_messages(response: Any, messages: list[Any]) -> Any:
    try:
        return replace(response, result=messages)
    except TypeError:
        # ModelResponse is a dataclass in the supported LangChain runtime.
        # Keep compatibility with small test doubles without mutating the
        # original response object.
        from copy import copy

        updated = copy(response)
        updated.result = messages
        return updated


def _copy_ai_message(
    message: AIMessage, tool_calls: list[dict[str, Any]], *, projection: dict[str, str] | None = None,
) -> AIMessage:
    update: dict[str, Any] = {"tool_calls": tool_calls}
    if projection is not None:
        update["additional_kwargs"] = {
            **(message.additional_kwargs or {}),
            PROJECTION_METADATA_KEY: projection,
        }
    return message.model_copy(deep=True, update=update)


def _enrich_model_response(response: Any) -> Any:
    """Enrich model-authored confirmation calls without mutating messages."""
    messages = getattr(response, "result", None)
    if not messages:
        return response
    updated_messages = list(messages)
    response_changed = False
    for index, message in enumerate(messages):
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        changed = False
        enriched_calls = []
        for tool_call in message.tool_calls:
            if tool_call.get("name") != CONFIRM_TOOL_NAME:
                enriched_calls.append(tool_call)
                continue
            args = dict(tool_call.get("args") or {})
            context, error = load_confirmation_context(
                str(args.get("confirmation_token") or ""),
                str(args.get("draft_id") or args.get("draftId") or ""),
                str(args.get("approval_id") or args.get("approvalId") or ""),
            )
            if error or context is None:
                enriched_calls.append(tool_call)
                continue
            enriched = dict(tool_call)
            enriched["args"] = confirmation_card_args(context, args)
            enriched_calls.append(enriched)
            changed = True
        if changed:
            updated_messages[index] = _copy_ai_message(message, enriched_calls)
            response_changed = True
    return _replace_response_messages(response, updated_messages) if response_changed else response


def _stable_confirm_call_id(context: PendingApprovalContext) -> str:
    identity = "\x1f".join(
        (
            context.origin_run_id,
            str(context.runtime.get("messageId") or ""),
            str(context.draft.get("approvalId") or ""),
        )
    )
    return f"auto-confirm-{sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def _upsert_pending_confirmation(request: Any, response: Any) -> Any:
    """Project only the immediately preceding draft result into official HITL."""
    if not (
        is_draft_projection_turn(request, _DRAFT_SOURCE_TOOLS)
        or is_delegated_draft_projection_turn(request, _DRAFT_DELEGATE_AGENTS)
    ):
        return _enrich_model_response(response)
    context, error = load_pending_approval_context(request)
    if error or context is None:
        # Preserve the previous behavior for explicit settled/resume calls.
        return _enrich_model_response(response)

    messages = getattr(response, "result", None)
    if not messages:
        return response
    target_index = next(
        (index for index in range(len(messages) - 1, -1, -1) if isinstance(messages[index], AIMessage)),
        None,
    )
    if target_index is None:
        return response

    target = messages[target_index]
    canonical_call = {
        "name": CONFIRM_TOOL_NAME,
        "args": confirmation_card_args(context, {}),
        "id": _stable_confirm_call_id(context),
        "type": "tool_call",
    }

    updated_messages = list(messages)
    # A WAITING_APPROVAL task is a terminal workflow gate for this model turn.
    # Preserving another model-authored call here would allow an unrelated
    # query or write to run alongside the confirmation interrupt.  The only
    # executable action until the user decides is the trusted canonical call.
    projection = approval_projection_metadata(
        action=CONFIRM_TOOL_NAME,
        approval_id=context.draft.get("approvalId"),
        draft_id=context.draft.get("draftId"),
        origin_run_id=context.origin_run_id,
        message_id=context.runtime.get("messageId"),
    )
    updated_messages[target_index] = _copy_ai_message(
        target, [canonical_call], projection=projection,
    )
    return _replace_response_messages(response, updated_messages)


class MeetingApprovalArgsMiddleware(AgentMiddleware):
    """Enrich only trusted pending/approved calls before official HITL runs."""

    name = "MeetingApprovalArgsMiddleware"

    def wrap_model_call(self, request, handler):
        return _enrich_model_response(handler(request))

    async def awrap_model_call(self, request, handler):
        return _enrich_model_response(await handler(request))


class MeetingApprovalAutoConfirmMiddleware(ConfiguredApprovalProjectionMiddleware):
    """Project a just-created meeting draft into one official HITL interrupt.

    It is not an auto-confirmation mechanism.  In particular, a persisted
    PENDING draft from an earlier turn is never enough to inject a tool call.
    """

    name = "MeetingApprovalAutoConfirmMiddleware"

    def __init__(self) -> None:
        super().__init__(name=self.name, projector=_upsert_pending_confirmation)
