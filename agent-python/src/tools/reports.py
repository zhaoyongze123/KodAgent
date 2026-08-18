"""Read-only cross-domain business reports.

Java owns authorization, filtering and aggregation. These tools only validate
the range and expose the backend result through the common card contract.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from .common import ToolResponse, bind_tool_call_id, emit, java_get, tool_failure, tool_success


def _range(start_time: str, end_time: str) -> tuple[str, str] | None:
    try:
        start = datetime.fromisoformat(start_time.strip().replace(" ", "T"))
        end = datetime.fromisoformat(end_time.strip().replace(" ", "T"))
    except (AttributeError, TypeError, ValueError):
        return None
    if end <= start:
        return None
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


def _run(tool_name: str, endpoint: str, start_time: str, end_time: str, message: str, call_id: str) -> ToolResponse:
    bind_tool_call_id(call_id)
    normalized = _range(start_time, end_time)
    if not normalized:
        return tool_failure("REPORT_RANGE_INVALID", "报表时间范围无效，结束时间必须晚于开始时间。")
    writer = get_stream_writer()
    emit(writer, "tool_started", message, toolName=tool_name, toolCallId=call_id)
    try:
        result = java_get(endpoint, {"startTime": normalized[0], "endTime": normalized[1]})
    except Exception as exc:
        emit(writer, "tool_failed", "报表查询失败，请稍后重试", toolName=tool_name, toolCallId=call_id, errorCode="REPORT_FACADE_UNAVAILABLE")
        return tool_failure("REPORT_FACADE_UNAVAILABLE", "报表查询暂时不可用", details=str(exc))
    if not isinstance(result, dict):
        return tool_failure("REPORT_RESULT_INVALID", "报表服务返回了无效结果。")
    presentation = {"blockType": "card", "cardType": "business_report", "reportType": tool_name.removesuffix("_report")}
    emit(writer, "tool_completed", "✅ 报表查询完成", toolName=tool_name, toolCallId=call_id, result=result, presentation=presentation)
    return tool_success(result, presentation)


@tool
def meeting_report(start_time: str, end_time: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """汇总当前用户指定范围内的会议数量、时长、会议室和日期分布。只读。"""
    return _run("meeting_report", "/agent/tools/meetings/report", start_time, end_time, "📊 正在汇总会议安排……", tool_call_id)


@tool
def schedule_report(start_time: str, end_time: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """汇总个人日程与会议占用、来源分布和冲突数量。只读。"""
    return _run("schedule_report", "/agent/tools/calendar/report", start_time, end_time, "📊 正在汇总日程占用……", tool_call_id)


@tool
def party_file_report(start_time: str, end_time: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """汇总当前用户可见党务文件的发布和已读分布。只读，不读取正文。"""
    return _run("party_file_report", "/agent/tools/party-files/report", start_time, end_time, "📊 正在汇总党务文件情况……", tool_call_id)


@tool
def approval_report(
    process_types: list[str] | None = None,
    amount_operator: str | None = None,
    amount: float | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    department: str | None = None,
    min_pending_days: int | None = None,
    sort_by: str = "CREATED_DESC",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """汇总当前用户待办审批，支持与待办查询相同的确定性条件。"""
    bind_tool_call_id(tool_call_id)
    params = {
        "processTypes": process_types,
        "amountOperator": amount_operator,
        "amount": amount,
        "createdFrom": created_from,
        "createdTo": created_to,
        "department": department,
        "minPendingDays": min_pending_days,
        "sortBy": sort_by,
    }
    params = {key: value for key, value in params.items() if value is not None}
    writer = get_stream_writer()
    emit(writer, "tool_started", "📊 正在汇总审批情况……", toolName="approval_report", toolCallId=tool_call_id)
    try:
        result = java_get("/agent/tools/approvals/report", params)
    except Exception as exc:
        emit(writer, "tool_failed", "审批报表查询失败，请稍后重试", toolName="approval_report",
             toolCallId=tool_call_id, errorCode="REPORT_FACADE_UNAVAILABLE")
        return tool_failure("REPORT_FACADE_UNAVAILABLE", "审批报表查询暂时不可用", details=str(exc))
    presentation = {"blockType": "card", "cardType": "business_report", "reportType": "approval"}
    emit(writer, "tool_completed", "✅ 审批报表查询完成", toolName="approval_report", toolCallId=tool_call_id,
         result=result, presentation=presentation)
    return tool_success(result, presentation)


__all__ = ["approval_report", "meeting_report", "schedule_report", "party_file_report"]
