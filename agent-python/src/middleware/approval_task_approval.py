from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage

from ..services.approval_task_approval import confirmation_args, load_pending_approval_task_context
from ..services.approval_core import approval_projection_metadata
from ..hitl.projection import project_confirmation_call
from ..hitl.auto_confirm import ConfiguredApprovalProjectionMiddleware


_PREVIEW_SOURCE_TOOLS = {"preview_approval_task_action"}
_PREVIEW_DELEGATE_AGENTS = {"approvals_agent"}


class ApprovalTaskAutoConfirmMiddleware(ConfiguredApprovalProjectionMiddleware):
    name = "ApprovalTaskAutoConfirmMiddleware"

    def __init__(self) -> None:
        super().__init__(name=self.name, projector=self._apply)

    @staticmethod
    def _apply(request, response):
        return project_confirmation_call(
            request, response,
            source_tools=_PREVIEW_SOURCE_TOOLS,
            delegate_agents=_PREVIEW_DELEGATE_AGENTS,
            context_loader=load_pending_approval_task_context,
            action_name="confirm_approval_task_action",
            args_builder=lambda context, args: confirmation_args(context, args),
            identity_builder=lambda context: (
                str(context.runtime.get("runId") or ""),
                str(context.runtime.get("messageId") or ""),
                str(context.approval.get("approvalId") or ""),
            ),
            projection_builder=lambda context, action: approval_projection_metadata(
                action=action, approval_id=context.approval.get("approvalId"),
                draft_id=context.approval.get("draftId"),
                origin_run_id=context.runtime.get("runId"), message_id=context.runtime.get("messageId"),
            ),
            call_id_prefix="auto-approval-task",
        )


__all__ = ["ApprovalTaskAutoConfirmMiddleware"]
