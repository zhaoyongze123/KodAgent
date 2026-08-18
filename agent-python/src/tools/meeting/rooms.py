from typing import Annotated

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import ToolResponse, bind_tool_call_id, emit, java_get, tool_failure, tool_success
from ...services.meeting_gate import meeting_request_gate
from .support import facade_tool_failure


def list_available_meeting_rooms_service(tool_call_id: str = "") -> ToolResponse:
    """查询当前启用的会议室，只读，不会预定会议室。"""
    bind_tool_call_id(tool_call_id)
    # Room listing is a read-only capability and must remain usable in a new
    # turn even when the previous turn is WAITING_APPROVAL.  Batch checking
    # and draft creation still require a current-turn REQUEST_READY task.
    blocked = meeting_request_gate()
    if blocked:
        return blocked
    writer = get_stream_writer()
    emit(writer, "tool_started", "正在查询可用会议室……", toolName="list_available_meeting_rooms", toolCallId=tool_call_id)
    try:
        result = java_get("/agent/tools/meetings/rooms")
    except Exception as exc:
        return facade_tool_failure(
            writer, "list_available_meeting_rooms", "会议室查询失败，请稍后重试", exc, tool_call_id
        )
    emit(writer, "tool_completed", f"会议室查询完成，共获取 {len(result.get('rooms', []))} 个会议室", toolName="list_available_meeting_rooms", toolCallId=tool_call_id)
    return tool_success(result)


@tool
def list_available_meeting_rooms(tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """Agent adapter for the read-only room service."""
    return list_available_meeting_rooms_service(tool_call_id=tool_call_id)
