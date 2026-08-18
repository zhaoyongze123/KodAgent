"""Read and cancellation tools for meetings created by the current user.

All irreversible operations still become a durable meeting draft and use the
same ``confirm_meeting_booking`` HITL boundary as creation and rescheduling.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ...runtime.operation_payload import merge_operation_payload
from ...runtime.operation_runtime import get_active_operation
from ..common import (
    ToolResponse,
    bind_tool_call_id,
    current_agent_context,
    emit,
    java_get,
    save_meeting_draft,
    tool_failure,
    tool_success,
)
from .support import facade_tool_failure


def list_my_meeting_bookings_service(start_time: str, end_time: str, tool_call_id: str = "") -> ToolResponse:
    """List only meetings visible to the current authenticated user."""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    try:
        result = java_get("/agent/tools/meetings/my", {"startTime": start_time, "endTime": end_time})
    except Exception as exc:
        return facade_tool_failure(writer, "list_my_meeting_bookings", "会议安排查询失败，请稍后重试", exc, tool_call_id)
    return tool_success(result)


@tool
def list_my_meeting_bookings(
    start_time: str,
    end_time: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """查询当前用户在指定时间范围内可见的会议；返回 bookingId 和是否可编辑。"""
    return list_my_meeting_bookings_service(start_time, end_time, tool_call_id)


def get_my_meeting_booking_service(booking_id: int, tool_call_id: str = "") -> ToolResponse:
    bind_tool_call_id(tool_call_id)
    try:
        result = java_get(f"/agent/tools/meetings/{int(booking_id)}")
        return tool_success(result)
    except Exception as exc:
        return tool_failure("MEETING_BOOKING_READ_FAILED", "无法读取该会议预约，可能不存在或您无权查看", details=str(exc))


@tool
def get_my_meeting_booking(
    booking_id: int,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取单个会议预约详情。只有申请人可修改或取消。"""
    return get_my_meeting_booking_service(booking_id, tool_call_id)


def create_meeting_booking_cancellation_draft_service(
    booking_id: int | None = None,
    cancel_reason: str = "",
    tool_call_id: str = "",
) -> ToolResponse:
    """Create a cancellation draft for an applicant-owned meeting booking."""
    bind_tool_call_id(tool_call_id)
    operation = get_active_operation()
    if operation is None:
        return tool_failure("OPERATION_REQUIRED", "会议取消缺少 Operation 绑定，请重新发起取消操作")
    source_id = int(booking_id) if booking_id is not None else None
    if source_id is None:
        return tool_failure("SOURCE_BOOKING_REQUIRED", "请先指定要取消的会议预约，或先查询我的会议安排")
    try:
        source = java_get(f"/agent/tools/meetings/{source_id}")
    except Exception as exc:
        return tool_failure("MEETING_BOOKING_READ_FAILED", "无法读取要取消的会议预约", details=str(exc))
    if not source.get("editable"):
        return tool_failure("MEETING_BOOKING_NOT_OWNER", "只能取消由您发起的会议预约")
    if str(source.get("status") or "") not in {"", "1"}:
        return tool_failure("MEETING_BOOKING_ALREADY_CANCELLED", "该会议预约已取消，不能重复取消")
    context = current_agent_context()
    draft = {
        "operation": "CANCEL",
        "sourceBookingId": source_id,
        "sourceStartTime": str(source.get("startTime") or ""),
        "sourceEndTime": str(source.get("endTime") or ""),
        "sourceSubject": str(source.get("subject") or ""),
        # Keep a readable snapshot for the card. Java does not trust these
        # fields at commit and re-reads the source booking as the authority.
        "subject": str(source.get("subject") or ""),
        "meetingRoomId": source.get("meetingRoomId"),
        "meetingRoomName": str(source.get("meetingRoomName") or ""),
        "startTime": str(source.get("startTime") or ""),
        "endTime": str(source.get("endTime") or ""),
        "attendeeUserIds": list(source.get("attendeeUserIds") or []),
        "remark": str(source.get("remark") or ""),
        "cancelReason": cancel_reason.strip() or "用户取消会议预约",
        **context,
        "operationId": operation.operation_id,
        "idempotencyKey": f"{operation.operation_id}:{context.get('messageId')}:CANCEL:{source_id}",
    }
    try:
        saved = save_meeting_draft(draft)
    except Exception as exc:
        return tool_failure("DRAFT_SAVE_FAILED", "会议取消草稿保存失败，请稍后重试", details=str(exc))
    draft_id = str(saved.get("draftId") or saved.get("id") or "")
    approval_id = str(saved.get("approvalId") or "")
    if not draft_id or not approval_id:
        return tool_failure("APPROVAL_ID_MISSING", "Java 未返回会议取消草稿的审批标识")
    persisted = saved.get("draft") if isinstance(saved.get("draft"), dict) else draft
    persisted.update({"draftId": draft_id, "approvalId": approval_id})
    operation.bind_approval(approval_id)
    if operation.operation.status == "COLLECTING_INFO":
        operation.transition("READY", event_type="operation.ready")
    if operation.operation.status == "READY":
        operation.transition("RUNNING", event_type="operation.running")
    if operation.operation.status == "RUNNING":
        operation.transition("WAITING_APPROVAL", event_type="operation.waiting_approval")
    persisted_operation = merge_operation_payload({
        "meeting_booking_draft": persisted,
        "meeting_operation": "CANCEL",
        "meeting_source_booking": source,
        "confirmation_token": draft_id,
        "approvalId": approval_id,
    })
    emit(get_stream_writer(), "draft.created", "📝 会议取消草稿已生成，等待用户确认", toolName="create_meeting_booking_cancellation_draft", toolCallId=tool_call_id, draftId=draft_id, approvalId=approval_id, operationId=operation.operation_id)
    return tool_success({
        "requires_confirmation": True,
        "confirmation_token": draft_id,
        "draftId": draft_id,
        "approvalId": approval_id,
        "operationId": operation.operation_id,
        "operationVersion": persisted_operation.version if persisted_operation else operation.operation.version,
        "draft": persisted,
        "message": "会议取消草稿已生成，用户确认后才会取消原预约。",
    })


@tool
def create_meeting_booking_cancellation_draft(
    booking_id: int | None = None,
    cancel_reason: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """生成取消本人会议预约的草稿；不会立刻取消，必须由确认卡片批准。"""
    return create_meeting_booking_cancellation_draft_service(booking_id, cancel_reason, tool_call_id)
