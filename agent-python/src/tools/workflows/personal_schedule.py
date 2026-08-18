from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from pydantic import Field

from ...tools.common import tool_success
from ...workflows.personal_schedule.graph import run_personal_schedule_workflow as _run_workflow


@tool
def run_personal_schedule_workflow(
    operation: Annotated[Literal["CREATE", "UPDATE", "CANCEL"], Field(description="日程操作：CREATE 新建，UPDATE 修改，CANCEL 取消。")],
    title: Annotated[str, Field(description="日程标题；CREATE 时通常必填。 ")] = "",
    start_time: Annotated[str, Field(description="开始时间，使用已解析的绝对时间，不传相对日期文本。 ")] = "",
    end_time: Annotated[str, Field(description="结束时间，必须晚于 start_time。 ")] = "",
    source_schedule_id: Annotated[int | None, Field(ge=1, description="要修改或取消的原日程编号；UPDATE 和 CANCEL 必填。")] = None,
    location: Annotated[str, Field(description="日程地点。 ")] = "",
    description: Annotated[str, Field(description="日程说明。 ")] = "",
    attendee_user_ids: Annotated[list[int] | None, Field(description="参会人用户编号列表；必须来自已授权的查询或计划结果。 ")] = None,
    other_participants: Annotated[str, Field(description="非系统用户的其他参与者说明。 ")] = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict[str, Any] | None, InjectedState] = None,
):
    """个人日程的唯一受控写入入口，只生成等待用户确认的草稿。

    函数会根据操作类型校验字段、读取 UPDATE/CANCEL 的目标日程并生成草稿。
    参数的中文含义写在每个 ``Field(description=...)`` 中；来自主 Agent
    WorkOrder 的 canonicalPlan 会在执行前覆盖模型参数，最终提交仍由主 Agent
    在确认卡恢复后完成。
    """
    outcome = _run_workflow(
        operation=operation, title=title, start_time=start_time, end_time=end_time,
        source_schedule_id=source_schedule_id, location=location,
        description=description, attendee_user_ids=attendee_user_ids or [],
        other_participants=other_participants, parent_state=state,
        tool_call_id=tool_call_id,
    )
    return tool_success(outcome.model_dump(mode="json"))
