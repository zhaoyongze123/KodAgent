"""Last transport gate before any approval-confirmation ToolNode execution."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from ..services.approval_core import PROJECTION_METADATA_KEY
from ..tools.common import current_agent_context, tool_failure


_CONFIRMATION_TOOLS = frozenset({
    "confirm_meeting_booking",
    "confirm_personal_schedule",
    "confirm_approval_batch_action",
    "confirm_approval_task_action",
    "confirm_approval_request_action",
    "confirm_approval_withdraw_action",
    "confirm_create_party_file",
    "confirm_update_party_file",
    "confirm_delete_party_file",
})


def _is_code_projected_confirmation(request: Any, tool_call: dict[str, Any]) -> bool:
    """Require the exact checkpointed call created by an approval projector."""
    call_id = str(tool_call.get("id") or "").strip()
    name = str(tool_call.get("name") or "").strip()
    if not call_id or not name:
        return False
    state = getattr(request, "state", None) or {}
    messages = state.get("messages") if isinstance(state, dict) else None
    if not isinstance(messages, list):
        return False
    for message in reversed(messages):
        calls = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
        if not any(isinstance(call, dict) and str(call.get("id") or "") == call_id for call in calls or []):
            continue
        metadata = message.get("additional_kwargs") if isinstance(message, dict) else getattr(message, "additional_kwargs", None)
        proof = metadata.get(PROJECTION_METADATA_KEY) if isinstance(metadata, dict) else None
        return isinstance(proof, dict) and str(proof.get("action") or "") == name
    return False


class ApprovalResumeGateMiddleware(AgentMiddleware):
    """Deny model-authored or non-resumed ``confirm_*`` ToolNode calls.

    An initial code-projected call is consumed by HumanInTheLoopMiddleware and
    pauses the graph.  Only the *same* checkpointed call, on a run carrying a
    resume identity, may subsequently reach the business tool.  Plain user
    messages never form a decision and therefore cannot cancel or submit a
    draft merely because an old interrupt is still visible in the thread.
    """

    name = "ApprovalResumeGateMiddleware"

    @staticmethod
    def _blocked(tool_call: dict[str, Any]) -> ToolMessage:
        response = tool_failure(
            "HITL_RESUME_REQUIRED",
            "确认操作只能通过审批卡的确认或取消按钮恢复，普通文本不会执行或取消草稿。",
        )
        return ToolMessage(
            content=response.to_tool_content(),
            name=str(tool_call.get("name") or ""),
            tool_call_id=str(tool_call.get("id") or ""),
            status="error",
        )

    def wrap_tool_call(self, request, handler):
        tool_call = dict(request.tool_call or {})
        if str(tool_call.get("name") or "") not in _CONFIRMATION_TOOLS:
            return handler(request)
        resume_run_id = str(current_agent_context().get("resumeRunId") or "").strip()
        if not resume_run_id or not _is_code_projected_confirmation(request, tool_call):
            return self._blocked(tool_call)
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        tool_call = dict(request.tool_call or {})
        if str(tool_call.get("name") or "") not in _CONFIRMATION_TOOLS:
            return await handler(request)
        resume_run_id = str(current_agent_context().get("resumeRunId") or "").strip()
        if not resume_run_id or not _is_code_projected_confirmation(request, tool_call):
            return self._blocked(tool_call)
        return await handler(request)


__all__ = ["ApprovalResumeGateMiddleware"]
