"""Runtime gates for the meeting-booking workflow.

The model may choose a Tool, but it must not be able to bypass the validated
request boundary by calling a legacy room or draft Tool after preparation
failed.  These gates are intentionally small and deterministic; they do not
replace the model's natural-language reasoning.
"""

from __future__ import annotations

from typing import Any

from ..tools.common.contracts import ToolResponse, tool_failure
from ..tools.common.events import current_agent_context
from ..runtime.operation_payload import operation_snapshot, operation_payload


_TERMINAL_STATUSES = {"COMPLETED", "CANCELLED", "EXPIRED"}
_READY_STATUSES = {
    "REQUEST_READY",
    "CHECKING_AVAILABILITY",
    "AVAILABILITY_CHECKED",
    "DRAFT_CREATED",
    "WAITING_APPROVAL",
    "SUBMITTING",
}


def _same_message(task: Any, context: dict[str, str]) -> bool:
    prepared_message_id = str(task.get("prepareMessageId") or "")
    current_message_id = str(context.get("messageId") or "")
    return bool(prepared_message_id and current_message_id and prepared_message_id == current_message_id)


def meeting_request_gate(*, require_ready: bool = False) -> ToolResponse | None:
    """Return a typed rejection when a Tool would cross the request boundary.

    A missing task is allowed for read-only room queries that are not part of a
    booking.  Once this message has produced ``REQUEST_NEEDS_INPUT``, however,
    all booking-path Tools are blocked for that same message.  This is what
    prevents a weak model from turning one invalid prepare result into a long
    room/search/draft loop.
    """
    operation = operation_snapshot(required=False)
    payload = operation_payload(required=False)
    if operation is None or operation.status in {"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"}:
        if require_ready:
            return tool_failure(
                "REQUEST_NOT_READY",
                "当前轮尚未完成预约信息校验，不能继续执行此步骤",
                details="请先调用 prepare_meeting_booking_request",
            )
        return None
    context = current_agent_context()
    if _same_message(payload, context) and not (payload.get("preparedResult") or {}).get("valid", True):
        missing = (payload.get("preparedResult") or {}).get("missing_fields", [])
        errors = (payload.get("preparedResult") or {}).get("errors", [])
        details = "；".join(str(item) for item in [*missing, *errors] if item)
        return tool_failure(
            "REQUEST_NEEDS_INPUT",
            "预约信息尚未完整，请先向用户询问缺少的信息",
            details=details or "当前 Operation 的预约请求尚未完成校验",
        )
    if require_ready and not _same_message(payload, context):
        return tool_failure(
            "REQUEST_NOT_READY",
            "当前轮尚未完成预约信息校验，不能复用上一轮预约参数",
            details="请先调用 prepare_meeting_booking_request",
        )
    if require_ready and operation.status not in {"READY", "RUNNING", "WAITING_APPROVAL"}:
        return tool_failure(
            "REQUEST_NOT_READY",
            "当前预约请求尚未通过结构化校验，不能继续执行此步骤",
            details=f"当前 Operation 状态：{operation.status}",
        )
    return None
