from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import ToolResponse, bind_tool_call_id, emit, java_get, normalize_local_datetime, tool_failure, tool_success
from .support import facade_tool_failure, post_meeting_tool


@tool
def search_meeting_attendees(keyword: str, limit: int = 10, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """按姓名或部门搜索启用用户，返回预约参会人员候选，不会修改用户数据。"""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    emit(writer, "tool_started", f"👥 正在查询参会人员：{keyword}……", toolName="search_meeting_attendees", toolCallId=tool_call_id)
    try:
        result = java_get("/agent/tools/users/search", {"keyword": keyword, "limit": min(max(limit, 1), 20)})
    except Exception as exc:
        return facade_tool_failure(
            writer, "search_meeting_attendees", "参会人员查询失败，请稍后重试", exc, tool_call_id
        )
    emit(writer, "tool_completed", f"✅ 参会人员查询完成，共找到 {len(result.get('users', []))} 人", toolName="search_meeting_attendees", toolCallId=tool_call_id)
    return tool_success(result)


@tool
def get_current_meeting_user(tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """获取当前登录用户的真实用户 ID 和姓名；用户说“我”时必须使用此工具。"""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    emit(writer, "tool_started", "👤 正在获取当前用户身份……", toolName="get_current_meeting_user", toolCallId=tool_call_id)
    try:
        result = java_get("/agent/tools/users/me")
    except Exception as exc:
        return facade_tool_failure(
            writer, "get_current_meeting_user", "当前用户身份获取失败，请重新登录", exc, tool_call_id
        )
    emit(writer, "tool_completed", f"✅ 当前用户身份已确认：{result.get('nickname', '当前用户')}", toolName="get_current_meeting_user", toolCallId=tool_call_id)
    return tool_success(result)


@tool
def get_meeting_attendees_calendar(user_ids: list[int], start_time: str, end_time: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """查询指定参会人员在时间范围内的日程，用于判断是否适合预约会议。"""
    bind_tool_call_id(tool_call_id)
    if not user_ids:
        return tool_failure("INVALID_ARGUMENT", "至少需要一个参会人员")
    try:
        start = normalize_local_datetime(start_time)
        end = normalize_local_datetime(end_time)
    except ValueError as exc:
        return tool_failure("INVALID_DATETIME", str(exc))
    return post_meeting_tool(
        "📅 正在查询参会人员安排……",
        "/agent/tools/calendar/users",
        {"userIds": list(dict.fromkeys(user_ids))[:20], "startTime": start, "endTime": end},
        tool_name="get_meeting_attendees_calendar",
        tool_call_id=tool_call_id,
        response_type="list",
    )
