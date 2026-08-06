"""Bridge durable personal-schedule drafts into the official HITL middleware."""

from __future__ import annotations

from copy import copy
from dataclasses import replace
from hashlib import sha256
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

from ..services.personal_schedule_approval import (
    load_pending_personal_schedule_context,
    load_personal_schedule_confirmation,
    personal_schedule_confirmation_args,
)
from ..services.approval_core import PROJECTION_METADATA_KEY, approval_projection_metadata
from .approval_projection import is_delegated_draft_projection_turn, is_draft_projection_turn


CONFIRM_TOOL_NAME = "confirm_personal_schedule"

_DRAFT_SOURCE_TOOLS = {
    "create_personal_schedule_draft",
    "run_personal_schedule_workflow",
}
_DRAFT_DELEGATE_AGENTS = {"schedules_agent"}


def _replace_response_messages(response: Any, messages: list[Any]) -> Any:
    try:
        return replace(response, result=messages)
    except TypeError:
        updated = copy(response)
        updated.result = messages
        return updated


def _copy_ai_message(
    message: AIMessage, calls: list[dict[str, Any]], *, projection: dict[str, str] | None = None,
) -> AIMessage:
    update: dict[str, Any] = {"tool_calls": calls}
    if projection is not None:
        update["additional_kwargs"] = {
            **(message.additional_kwargs or {}),
            PROJECTION_METADATA_KEY: projection,
        }
    return message.model_copy(deep=True, update=update)


def _stable_confirm_call_id(context: Any) -> str:
    identity = "\x1f".join((context.origin_run_id, str(context.runtime.get("messageId") or ""), str(context.draft.get("approvalId") or "")))
    return f"auto-schedule-confirm-{sha256(identity.encode('utf-8')).hexdigest()[:24]}"


def _enrich_or_inject(request: Any, response: Any) -> Any:
    """Use a trusted pending draft to deterministically manufacture one call.

    The model's narration may still be useful to the transcript, but it must
    not decide whether a write-draft gets an ApprovalCard.  Any pending draft
    replaces same-turn calls so no unrelated side effect can run before the
    user decides.
    """
    pending, pending_error = load_pending_personal_schedule_context()
    messages = getattr(response, "result", None)
    if not messages:
        return response
    target_index = next((index for index in range(len(messages) - 1, -1, -1) if isinstance(messages[index], AIMessage)), None)
    if target_index is None:
        return response
    updated = list(messages)
    target = messages[target_index]
    if (
        pending is not None
        and pending_error is None
        and (
            is_draft_projection_turn(request, _DRAFT_SOURCE_TOOLS)
            or is_delegated_draft_projection_turn(request, _DRAFT_DELEGATE_AGENTS)
        )
    ):
        call = {
            "name": CONFIRM_TOOL_NAME,
            "args": personal_schedule_confirmation_args(pending, {}),
            "id": _stable_confirm_call_id(pending),
            "type": "tool_call",
        }
        updated[target_index] = _copy_ai_message(
            target,
            [call],
            projection=approval_projection_metadata(
                action=CONFIRM_TOOL_NAME,
                approval_id=pending.draft.get("approvalId"),
                draft_id=pending.draft.get("draftId"),
                origin_run_id=pending.origin_run_id,
                message_id=pending.runtime.get("messageId"),
            ),
        )
        return _replace_response_messages(response, updated)

    # Settled/resume calls must retain their model-generated call id, but card
    # fields are always rebuilt from Java facts rather than model arguments.
    changed = False
    for index, message in enumerate(messages):
        if not isinstance(message, AIMessage) or not message.tool_calls:
            continue
        calls: list[dict[str, Any]] = []
        call_changed = False
        for call in message.tool_calls:
            if call.get("name") != CONFIRM_TOOL_NAME:
                calls.append(call)
                continue
            args = dict(call.get("args") or {})
            context, error = load_personal_schedule_confirmation(
                str(args.get("draft_id") or args.get("draftId") or ""),
                str(args.get("approval_id") or args.get("approvalId") or ""),
            )
            if error or context is None:
                calls.append(call)
                continue
            calls.append({**call, "args": personal_schedule_confirmation_args(context, args)})
            call_changed = True
        if call_changed:
            updated[index] = _copy_ai_message(message, calls)
            changed = True
    return _replace_response_messages(response, updated) if changed else response


class PersonalScheduleApprovalArgsMiddleware(AgentMiddleware):
    """Inject/enrich schedule confirmation calls before official HITL scans tools."""

    name = "PersonalScheduleApprovalArgsMiddleware"

    def wrap_model_call(self, request, handler):
        return _enrich_or_inject(request, handler(request))

    async def awrap_model_call(self, request, handler):
        return _enrich_or_inject(request, await handler(request))
