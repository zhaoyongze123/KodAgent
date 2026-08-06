"""Inject the sole allowed batch confirmation call from durable preview facts."""

from __future__ import annotations

from typing import Any

from ..services.approval_batch_approval import confirmation_args, load_pending_approval_batch_context
from ..services.approval_core import approval_projection_metadata
from ..hitl.projection import project_confirmation_call
from ..hitl.auto_confirm import ConfiguredApprovalProjectionMiddleware


CONFIRM_TOOL_NAME = "confirm_approval_batch_action"
_PREVIEW_SOURCE_TOOLS = {"preview_approval_batch_action"}
_PREVIEW_DELEGATE_AGENTS = {"approvals_agent"}


class ApprovalBatchAutoConfirmMiddleware(ConfiguredApprovalProjectionMiddleware):
    """A pending batch preview is a terminal model-turn gate.

    The model may narrate the preview, but it cannot choose whether to expose
    a confirmation action or invoke a different write tool alongside it.
    """

    name = "ApprovalBatchAutoConfirmMiddleware"

    def __init__(self) -> None:
        super().__init__(name=self.name, projector=self._inject)

    @staticmethod
    def _inject(request: Any, response: Any) -> Any:
        return project_confirmation_call(
            request, response,
            source_tools=_PREVIEW_SOURCE_TOOLS,
            delegate_agents=_PREVIEW_DELEGATE_AGENTS,
            context_loader=load_pending_approval_batch_context,
            action_name=CONFIRM_TOOL_NAME,
            args_builder=lambda context, args: confirmation_args(context, args),
            identity_builder=lambda context: (
                context.origin_run_id, str(context.runtime.get("messageId") or ""),
                str(context.preview.get("previewId") or ""),
            ),
            projection_builder=lambda context, action: approval_projection_metadata(
                action=action, approval_id=context.preview.get("previewId"),
                draft_id=context.preview.get("previewId"), origin_run_id=context.origin_run_id,
                message_id=context.runtime.get("messageId"),
            ),
            call_id_prefix="auto-batch-confirm",
        )
