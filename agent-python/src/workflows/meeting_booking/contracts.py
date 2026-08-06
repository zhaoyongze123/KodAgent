"""Stable input/output contracts for the meeting booking workflow."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


MeetingBookingWorkflowStatus = Literal[
    "NEEDS_INPUT",
    "AMBIGUOUS_ENTITY",
    "CONFLICT_BLOCKED",
    "DRAFT_READY",
    "FAILED",
]


class MeetingBookingWorkflowInput(BaseModel):
    """Structured request accepted by the workflow boundary.

    Fields remain optional while the preparation node supports the existing
    conversational extraction path.  A future caller can provide a complete
    object without changing the workflow registry contract.
    """

    operation: Literal["CREATE", "UPDATE", "CANCEL"] = Field(default="CREATE", description="会议操作")
    source_booking_id: int | None = Field(default=None, ge=1, description="待修改或取消的原预约编号")
    cancel_reason: str | None = Field(default=None, description="取消原因")
    subject: str | None = Field(default=None, description="会议主题")
    start_time: str | None = Field(default=None, description="开始时间")
    end_time: str | None = Field(default=None, description="结束时间")
    attendee_names: list[str] = Field(default_factory=list, description="参会人姓名或称谓")
    room_capacity: int | None = Field(default=None, ge=1, description="会议室最低容量")
    equipment: list[str] = Field(default_factory=list, description="所需设备")
    room_preference: str | None = Field(default=None, description="会议室偏好")
    remark: str | None = Field(default=None, description="预约备注")


class MeetingBookingWorkflowOutcome(BaseModel):
    """The only result shape exposed to the parent DeepAgent."""

    status: MeetingBookingWorkflowStatus
    message: str
    operation_id: str | None = None
    draft_id: str | None = None
    approval_id: str | None = None
    confirmation_token: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    retryable: bool = False


def outcome_from_tool_error(error: Any, *, operation_id: str | None = None) -> MeetingBookingWorkflowOutcome:
    code = str(getattr(error, "code", None) or "WORKFLOW_TOOL_FAILED")
    message = str(getattr(error, "message", None) or "会议预约流程执行失败，请稍后重试")
    return MeetingBookingWorkflowOutcome(
        status="FAILED",
        message=message,
        operation_id=operation_id,
        error_code=code,
        retryable=code in {"FACADE_UNAVAILABLE", "AVAILABILITY_STATE_UNAVAILABLE", "BOOKING_SUBMIT_FAILED"},
    )
