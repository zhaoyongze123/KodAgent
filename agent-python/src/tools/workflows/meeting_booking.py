"""Parent-Agent Tool for the deterministic meeting booking workflow."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from ...tools.common import tool_success
from ...workflows.meeting_booking.graph import run_meeting_booking_workflow as _run_workflow


@tool
def run_meeting_booking_workflow(
    operation: Annotated[
        Literal["CREATE", "UPDATE", "CANCEL", "BOOK"],
        Field(description="会议操作：CREATE/BOOK 为新建，UPDATE 为修改已有预约，CANCEL 为取消已有预约。"),
    ] = "CREATE",
    source_booking_id: Annotated[
        int | None,
        Field(ge=1, description="要修改或取消的原会议预约编号；仅 UPDATE 和 CANCEL 必填，必须来自已授权的预约查询结果。"),
    ] = None,
    cancel_reason: Annotated[str, Field(description="取消原因；仅 CANCEL 使用。留空表示未补充原因。")] = "",
    subject: Annotated[str, Field(description="会议主题；新建会议通常必填，修改会议时留空表示保持原主题。")] = "",
    start_time: Annotated[str, Field(description="会议开始时间。使用已解析的绝对时间，推荐 yyyy-MM-dd HH:mm:ss；不要传相对时间。")] = "",
    end_time: Annotated[str, Field(description="会议结束时间。使用已解析的绝对时间，必须晚于 start_time。")] = "",
    attendee_names: Annotated[
        list[str] | None,
        Field(description="参会人姓名或称谓列表。工作流会确定性解析为用户 ID；不传表示由准备步骤补充或沿用原预约。"),
    ] = None,
    room_capacity: Annotated[
        int | None,
        Field(ge=1, description="会议室最低容纳人数；不传表示不按容量筛选。"),
    ] = None,
    equipment: Annotated[
        list[str] | None,
        Field(description="所需设备名称列表，例如投影仪、视频会议；不传表示无设备约束。"),
    ] = None,
    room_preference: Annotated[str, Field(description="会议室偏好，例如 A 座或靠近前台；不保证一定满足。")] = "",
    remark: Annotated[str, Field(description="写入预约草稿的备注。")] = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict[str, Any] | None, InjectedState] = None,
):
    """会议预约的唯一受控写入入口：新建、修改或取消后只生成待确认草稿。

    本函数负责的完整流程是：整理请求 -> 查询候选会议室 -> 批量检查会议室
    与参会人冲突 -> 生成草稿。调用者不能跳过中间步骤，也不能直接提交预约；
    ``confirm_meeting_booking`` 仅由主 Agent 在用户点击确认卡后调用。

    参数中文含义见每个 ``Field(description=...)``。对于主 Agent 下发的
    ``KODAGENT_WORK_ORDER``，中间件会以其中的 canonicalPlan 覆盖这些参数，
    因此模型填写的值不能篡改已编译的业务事实。
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
