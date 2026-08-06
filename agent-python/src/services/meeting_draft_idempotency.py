"""Idempotent replay rules for the meeting booking draft boundary."""

from __future__ import annotations

from typing import Any

from ..runtime.operation_payload import operation_payload, operation_snapshot
from ..tools.common.events import current_agent_context


_CONTEXT_KEYS = ("runId", "messageId", "threadId", "tenantId", "userId")


def current_meeting_draft_replay() -> dict[str, Any] | None:
    """Return a persisted draft only when it belongs to this exact request.

    A draft is replayable only for the same LangGraph run and user message.
    This prevents a later booking request, another run, or another thread from
    inheriting an older approval payload.
    """
    context = current_agent_context()
    if not context.get("runId") or not context.get("messageId"):
        return None
    try:
        operation = operation_snapshot(required=False)
        payload = operation_payload(required=False)
    except Exception:
        return None
    if operation is None or operation.status != "WAITING_APPROVAL":
        return None

    draft = payload.get("meeting_booking_draft")
    token = str(payload.get("confirmation_token") or "")
    if not isinstance(draft, dict) or not token:
        return None

    # The draft is written with the full runtime envelope.  Requiring every
    # boundary field means incomplete/legacy memory cannot be replayed by
    # accident and cross-user/thread reuse is impossible.
    if any(str(draft.get(key) or "") != str(context.get(key) or "") for key in _CONTEXT_KEYS):
        return None

    approval_id = str(payload.get("approvalId") or draft.get("approvalId") or "")
    if not approval_id:
        return None
    replay_draft = {**draft, "draftId": token, "approvalId": approval_id}
    return {
        "requires_confirmation": True,
        "confirmation_token": token,
        "draftId": token,
        "approvalId": approval_id,
        "draft": replay_draft,
        "message": "预约草稿已生成，用户确认后才能正式提交。",
        "idempotentReplay": True,
        "operationId": operation.operation_id,
        "operationVersion": operation.version,
    }
