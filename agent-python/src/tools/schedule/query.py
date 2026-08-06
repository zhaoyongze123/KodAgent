from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import ToolResponse, bind_tool_call_id, emit, java_get, normalize_local_datetime, tool_failure, tool_success


@tool
def get_my_calendar(start_time: str, end_time: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """查询当前用户指定时间范围内的日历，时间格式为 yyyy-MM-dd HH:mm:ss。"""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    emit(writer, "tool_started", "🔧 正在查询个人日历……", toolName="get_my_calendar", toolCallId=tool_call_id)
    try:
        normalized_start = normalize_local_datetime(start_time)
        normalized_end = normalize_local_datetime(end_time)
        result = java_get("/agent/tools/calendar/my", {"startTime": normalized_start, "endTime": normalized_end})
    except Exception as exc:
        emit(writer, "tool_failed", "日历查询失败，请稍后重试", toolName="get_my_calendar", toolCallId=tool_call_id, errorCode="SCHEDULE_FACADE_UNAVAILABLE")
        return tool_failure("SCHEDULE_FACADE_UNAVAILABLE", "日历查询暂时不可用", details=str(exc))
    presentation = {"blockType": "card", "cardType": "calendar"}
    emit(
        writer,
        "tool_completed",
        f"✅ 日历查询完成，共获取 {len(result.get('events', []))} 条日程",
        toolName="get_my_calendar",
        toolCallId=tool_call_id,
        result=result,
        presentation=presentation,
    )
    return tool_success(result, presentation)


@tool
def find_calendar_conflicts(start_time: str, end_time: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """查询时间范围并确定性找出个人日程与会议重叠，只读。"""
    bind_tool_call_id(tool_call_id)
    try:
        normalized_start = normalize_local_datetime(start_time)
        normalized_end = normalize_local_datetime(end_time)
        result = java_get("/agent/tools/calendar/my", {"startTime": normalized_start, "endTime": normalized_end})
    except Exception as exc:
        return tool_failure("SCHEDULE_FACADE_UNAVAILABLE", "日历查询暂时不可用", details=str(exc))
    from datetime import datetime
    events = result.get("events", []) if isinstance(result, dict) else []
    parsed = []
    for event in events:
        try:
            start = datetime.fromisoformat(str(event.get("startTime")).replace(" ", "T"))
            end = datetime.fromisoformat(str(event.get("endTime")).replace(" ", "T"))
            parsed.append((start, end, event))
        except (TypeError, ValueError):
            continue
    conflicts = []
    for index, (start, end, event) in enumerate(parsed):
        for other_start, other_end, other in parsed[index + 1:]:
            if start < other_end and other_start < end:
                conflicts.append({"first": event, "second": other})
    return tool_success({"events": events, "conflicts": conflicts, "conflictCount": len(conflicts)}, {"blockType": "card", "cardType": "calendar"})
