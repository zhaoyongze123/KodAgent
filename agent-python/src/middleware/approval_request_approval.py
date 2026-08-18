from __future__ import annotations

from ..services.approval_request_approval import confirmation_args, load_pending_approval_request_context
from ..services.approval_core import approval_projection_metadata
from ..hitl.projection import project_confirmation_call
from ..hitl.auto_confirm import ConfiguredApprovalProjectionMiddleware
from .approval_projection import delegated_approval_draft_receipt


class ApprovalRequestAutoConfirmMiddleware(ConfiguredApprovalProjectionMiddleware):
    name = "ApprovalRequestAutoConfirmMiddleware"

    def __init__(self) -> None:
        super().__init__(name=self.name, projector=self._apply)

    @staticmethod
    def _apply(request, response):
        receipt = delegated_approval_draft_receipt(request)
        if receipt is not None:
            if receipt.confirmation_type != "request":
                return response
            from ..tools.common import set_operation_context
            set_operation_context(receipt.operation_id)
        return project_confirmation_call(
            request, response,
            source_tools={"create_approval_request_draft", "create_approval_withdraw_draft"},
            delegated_eligible=receipt is not None,
            context_loader=load_pending_approval_request_context,
            action_name=lambda context: (
                "confirm_approval_withdraw_action"
                if context.approval.get("draftType") == "APPROVAL_WITHDRAW"
                else "confirm_approval_request_action"
            ),
            args_builder=lambda context, args: confirmation_args(context, args),
            identity_builder=lambda context: (
                str(context.runtime.get("runId") or ""),
                str(context.runtime.get("messageId") or ""),
                str(context.approval.get("approvalId") or ""),
            ),
            projection_builder=lambda context, action: approval_projection_metadata(
                action=action, approval_id=context.approval.get("approvalId"),
                draft_id=context.approval.get("draftId"), origin_run_id=context.runtime.get("runId"),
                message_id=context.runtime.get("messageId"),
            ),
            call_id_prefix="auto-approval-request",
        )


__all__ = ["ApprovalRequestAutoConfirmMiddleware"]
