from __future__ import annotations

from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState

from ...tools.common import tool_success
from ...workflows.personal_schedule.graph import run_personal_schedule_workflow as _run_workflow


@tool
def run_personal_schedule_workflow(
    operation: str,
    title: str = "",
    start_time: str = "",
    end_time: str = "",
    source_schedule_id: int | None = None,
    location: str = "",
    description: str = "",
    attendee_user_ids: list[int] | None = None,
    other_participants: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict[str, Any] | None, InjectedState] = None,
):
    """按固定顺序校验、读取目标并生成个人日程草稿。"""
    outcome = _run_workflow(
        operation=operation, title=title, start_time=start_time, end_time=end_time,
        source_schedule_id=source_schedule_id, location=location,
        description=description, attendee_user_ids=attendee_user_ids or [],
        other_participants=other_participants, parent_state=state,
        tool_call_id=tool_call_id,
    )
    return tool_success(outcome.model_dump(mode="json"))
