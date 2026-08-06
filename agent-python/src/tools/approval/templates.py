"""Approval tools for the domain boundary."""

from __future__ import annotations

from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import (
    ToolResponse, bind_tool_call_id, current_agent_context, emit, java_get,
    java_post, tool_failure, tool_success,
)
from .common import (
    approval_failure as _approval_failure,
    approval_read as _approval_read,
    request_payload as _request_payload,
)

@tool
def list_startable_approval_types(
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """列出当前用户可由 Agent 发起的请假、出差审批模板。只读。"""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    tool_name = "list_startable_approval_types"
    emit(writer, "tool_started", "🔧 正在查询可发起的审批模板……", toolName=tool_name, toolCallId=tool_call_id)
    try:
        result = java_get("/agent/tools/approvals/types")
    except Exception as exc:
        return _approval_failure(writer, tool_name, tool_call_id, "审批模板查询失败，请稍后重试", exc)
    emit(writer, "tool_completed", "✅ 已获取可发起的审批模板", toolName=tool_name, toolCallId=tool_call_id,
         result=result, presentation={"blockType": "card", "cardType": "approval_template"})
    return tool_success(result, {"blockType": "card", "cardType": "approval_template"})
@tool
def preview_approval_request(
    request_type: str,
    start_time: str,
    end_time: str,
    approval_type: int | None,
    reason: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """预览请假或出差的真实审批链，不会创建流程实例。"""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    tool_name = "preview_approval_request"
    payload, failure = _request_payload(request_type, start_time, end_time, approval_type, reason)
    if failure:
        return failure
    emit(writer, "tool_started", "🔧 正在预览审批链路……", toolName=tool_name, toolCallId=tool_call_id)
    try:
        result = java_post("/agent/tools/approvals/preview", payload or {})
    except Exception as exc:
        return _approval_failure(writer, tool_name, tool_call_id, "审批链预览失败，请稍后重试", exc)
    data = {"request": payload, "preview": result}
    emit(writer, "tool_completed", "✅ 已生成审批链预览，等待你的确认", toolName=tool_name, toolCallId=tool_call_id,
         result=data, presentation={"blockType": "card", "cardType": "approval_preview"})
    return tool_success(data, {"blockType": "card", "cardType": "approval_preview"})


__all__ = ["list_startable_approval_types", "preview_approval_request"]
