"""Server-resume safety boundary for meeting approval decisions."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

from ..services.meeting_approval import (
    approval_status,
    load_confirmation_context,
)
from ..tools.common import tool_failure


CONFIRM_TOOL_NAME = "confirm_meeting_booking"


class MeetingApprovalResumeMiddleware(AgentMiddleware):
    """Short-circuit a rejected replay without entering the confirm Tool.

    LangGraph Server can represent ``Command(resume=...)`` as a new Run.  If
    that Run replays the model tool call after the original checkpoint frame
    has already been settled, the official HITL node is no longer present to
    manufacture its rejected ToolMessage.  This boundary restores that exact
    no-side-effect behavior.  Approved calls always go through the real Tool,
    whose durable marker and Java claim still enforce one successful submit.
    """

    name = "MeetingApprovalResumeMiddleware"

    @staticmethod
    def _rejected_context(state: Any):
        """Return the durable rejected context for the current HITL exchange."""
        messages = (state or {}).get("messages") or []
        if not messages or not isinstance(messages[-1], AIMessage):
            return None
        rejected = next(
            (
                message for message in reversed(messages)
                if isinstance(message, ToolMessage)
                and message.name == CONFIRM_TOOL_NAME
                and message.status == "error"
            ),
            None,
        )
        if rejected is None:
            return None
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls or []:
                if str(call.get("id") or "") != str(rejected.tool_call_id or ""):
                    continue
                args = call.get("args") or {}
                context, _ = load_confirmation_context(
                    str(args.get("confirmation_token") or ""),
                    str(args.get("draft_id") or args.get("draftId") or ""),
                    str(args.get("approval_id") or args.get("approvalId") or ""),
                )
                if context is not None and approval_status(context) == "REJECTED":
                    return context
                return None
        return None

    def wrap_tool_call(self, request, handler):
        tool_call = request.tool_call or {}
        if tool_call.get("name") != CONFIRM_TOOL_NAME:
            return handler(request)

        args = tool_call.get("args") or {}
        context, error = load_confirmation_context(
            str(args.get("confirmation_token") or ""),
            str(args.get("draft_id") or args.get("draftId") or ""),
            str(args.get("approval_id") or args.get("approvalId") or ""),
        )
        if context is not None and approval_status(context) == "REJECTED":
            response = tool_failure("APPROVAL_REJECTED", "用户已取消会议室预约")
            return ToolMessage(
                content=response.to_tool_content(),
                name=CONFIRM_TOOL_NAME,
                tool_call_id=str(tool_call.get("id") or ""),
                status="error",
            )
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        tool_call = request.tool_call or {}
        if tool_call.get("name") != CONFIRM_TOOL_NAME:
            return await handler(request)

        args = tool_call.get("args") or {}
        context, error = load_confirmation_context(
            str(args.get("confirmation_token") or ""),
            str(args.get("draft_id") or args.get("draftId") or ""),
            str(args.get("approval_id") or args.get("approvalId") or ""),
        )
        if context is not None and approval_status(context) == "REJECTED":
            response = tool_failure("APPROVAL_REJECTED", "用户已取消会议室预约")
            return ToolMessage(
                content=response.to_tool_content(),
                name=CONFIRM_TOOL_NAME,
                tool_call_id=str(tool_call.get("id") or ""),
                status="error",
            )
        return await handler(request)
