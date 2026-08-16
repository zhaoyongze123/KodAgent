"""Deterministic reject continuation for personal-schedule HITL resumes."""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, ToolMessage

from ..services.personal_schedule_approval import (
    approval_status,
    load_personal_schedule_confirmation,
)
from ..tools.common import tool_failure


CONFIRM_TOOL_NAME = "confirm_personal_schedule"


class PersonalScheduleApprovalResumeMiddleware(AgentMiddleware):
    """Never let a rejected card reach the schedule commit Tool.

    Server-side resumes can replay the original model message under a new run.
    This middleware derives the terminal narration from Java's REJECTED
    approval instead of trusting a model to narrate or retry the action.
    """

    name = "PersonalScheduleApprovalResumeMiddleware"

    @staticmethod
    def _rejected_context(state: Any):
        messages = (state or {}).get("messages") or []
        rejected = next((item for item in reversed(messages) if isinstance(item, ToolMessage) and item.name == CONFIRM_TOOL_NAME and item.status == "error"), None)
        if rejected is None:
            return None
        for message in reversed(messages):
            if not isinstance(message, AIMessage):
                continue
            for call in message.tool_calls or []:
                if str(call.get("id") or "") != str(rejected.tool_call_id or ""):
                    continue
                args = call.get("args") or {}
                context, _ = load_personal_schedule_confirmation(
                    str(args.get("draft_id") or args.get("draftId") or ""),
                    str(args.get("approval_id") or args.get("approvalId") or ""),
                )
                return context if context is not None and approval_status(context) == "REJECTED" else None
        return None

    def wrap_tool_call(self, request, handler):
        call = request.tool_call or {}
        if call.get("name") != CONFIRM_TOOL_NAME:
            return handler(request)
        args = call.get("args") or {}
        context, _ = load_personal_schedule_confirmation(str(args.get("draft_id") or args.get("draftId") or ""), str(args.get("approval_id") or args.get("approvalId") or ""))
        if context is not None and approval_status(context) == "REJECTED":
            return ToolMessage(content=tool_failure("APPROVAL_REJECTED", "用户已取消个人日程操作").to_tool_content(), name=CONFIRM_TOOL_NAME, tool_call_id=str(call.get("id") or ""), status="error")
        return handler(request)

    async def awrap_tool_call(self, request, handler):
        call = request.tool_call or {}
        if call.get("name") != CONFIRM_TOOL_NAME:
            return await handler(request)
        args = call.get("args") or {}
        context, _ = load_personal_schedule_confirmation(str(args.get("draft_id") or args.get("draftId") or ""), str(args.get("approval_id") or args.get("approvalId") or ""))
        if context is not None and approval_status(context) == "REJECTED":
            return ToolMessage(content=tool_failure("APPROVAL_REJECTED", "用户已取消个人日程操作").to_tool_content(), name=CONFIRM_TOOL_NAME, tool_call_id=str(call.get("id") or ""), status="error")
        return await handler(request)
