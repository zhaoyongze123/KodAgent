"""Parent-Agent Tool for the deterministic meeting booking workflow."""

from __future__ import annotations

from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState

from ...tools.common import tool_success
from ...workflows.meeting_booking.graph import run_meeting_booking_workflow as _run_workflow


@tool
def run_meeting_booking_workflow(
    operation: str = "CREATE",
    source_booking_id: int | None = None,
    cancel_reason: str = "",
    subject: str = "",
    start_time: str = "",
    end_time: str = "",
    attendee_names: list[str] | None = None,
    room_capacity: int | None = None,
    equipment: list[str] | None = None,
    room_preference: str = "",
    remark: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict[str, Any] | None, InjectedState] = None,
):
    """按固定顺序执行会议新建、修改或取消，并生成确认草稿。

    这些字段是工作流的唯一业务输入。模型只负责在本次调用中提取字段，
    后续节点不得重新从自然语言猜测或改变预约条件。
    """
    outcome = _run_workflow(
        operation=operation,
        source_booking_id=source_booking_id,
        cancel_reason=cancel_reason,
        subject=subject,
        start_time=start_time,
        end_time=end_time,
        attendee_names=attendee_names,
        room_capacity=room_capacity,
        equipment=equipment,
        room_preference=room_preference,
        remark=remark,
        parent_state=state,
        tool_call_id=tool_call_id,
    )
    return tool_success(outcome.model_dump(mode="json"))
