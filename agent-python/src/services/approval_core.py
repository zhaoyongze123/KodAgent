"""Shared, domain-neutral invariants for approval/HITL bindings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


IDENTITY_FIELDS = ("tenantId", "userId", "threadId", "messageId")
RESUME_STATUSES = frozenset({"INTERRUPT_PENDING", "RESUME_APPROVED", "COMPLETED", "CANCELLED"})
PROJECTION_METADATA_KEY = "kodagent.approval_projection"


@dataclass(frozen=True)
class ApprovalBinding:
    draft: dict[str, Any]
    approval: dict[str, Any]
    runtime: dict[str, str]
    origin_run_id: str
    resume_run_id: str


def identity_mismatch(
    record: Mapping[str, Any], runtime: Mapping[str, Any], *, fields: tuple[str, ...] = IDENTITY_FIELDS
) -> str | None:
    """Return the first identity field that is absent or mismatched."""

    for field in fields:
        actual, expected = record.get(field), runtime.get(field)
        if not actual or not expected or str(actual) != str(expected):
            return field
    return None


def resume_runtime(runtime: Mapping[str, str], origin_run_id: str) -> tuple[dict[str, str], str]:
    """Build explicit origin/resume identifiers without changing the source map."""

    current_run_id = str(runtime.get("runId") or "")
    resume_run_id = current_run_id if current_run_id and current_run_id != origin_run_id else ""
    return {**runtime, "originRunId": origin_run_id, "resumeRunId": resume_run_id}, resume_run_id


def approval_projection_metadata(
    *, action: str, approval_id: Any, draft_id: Any, origin_run_id: Any, message_id: Any,
) -> dict[str, str]:
    """Build the code-owned origin proof attached to an injected ToolCall.

    This is graph provenance, not a user or model supplied tool argument. It
    binds the native ToolCall stored in the checkpoint to the draft projection
    frame that immediately followed a successful draft/preview result.
    """
    return {
        "action": str(action or ""),
        "approvalId": str(approval_id or ""),
        "draftId": str(draft_id or ""),
        "originRunId": str(origin_run_id or ""),
        "messageId": str(message_id or ""),
    }


def has_trusted_approval_projection(
    request: Any, *, action: str, approval_id: Any, draft_id: Any,
    origin_run_id: Any, message_id: Any,
) -> bool:
    """Verify that the current confirmation ToolCall was code-projected.

    A persisted PENDING approval is intentionally not evidence by itself.
    The matching call must be in an AI checkpoint message carrying our
    private provenance metadata.  Thus a later user text, a replayed model
    decision, or a model-invented call cannot mint a new HITL pause.
    """
    tool_call = getattr(request, "tool_call", None) or {}
    call_id = str(tool_call.get("id") or "") if isinstance(tool_call, Mapping) else ""
    if not call_id:
        return False
    expected = approval_projection_metadata(
        action=action,
        approval_id=approval_id,
        draft_id=draft_id,
        origin_run_id=origin_run_id,
        message_id=message_id,
    )
    state = getattr(request, "state", None) or {}
    messages = state.get("messages") if isinstance(state, Mapping) else None
    if not isinstance(messages, (list, tuple)):
        return False
    for message in reversed(messages):
        calls = getattr(message, "tool_calls", None)
        metadata = getattr(message, "additional_kwargs", None)
        if not isinstance(calls, list) or not isinstance(metadata, Mapping):
            continue
        if not any(isinstance(call, Mapping) and str(call.get("id") or "") == call_id for call in calls):
            continue
        proof = metadata.get(PROJECTION_METADATA_KEY)
        if not isinstance(proof, Mapping):
            return False
        return all(str(proof.get(key) or "") == value for key, value in expected.items())
    return False


__all__ = [
    "ApprovalBinding",
    "IDENTITY_FIELDS",
    "PROJECTION_METADATA_KEY",
    "RESUME_STATUSES",
    "approval_projection_metadata",
    "has_trusted_approval_projection",
    "identity_mismatch",
    "resume_runtime",
]
