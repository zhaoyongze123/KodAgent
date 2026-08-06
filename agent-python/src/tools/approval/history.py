"""Approval tools for the domain boundary."""

from __future__ import annotations

from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import (
    ToolResponse, bind_tool_call_id, current_agent_context, emit, java_get,
    java_post, tool_failure, tool_success,
)
from .common import approval_read as _approval_read

@tool
def list_my_approval_applications(
    page_no: int = 1,
    page_size: int = 20,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """查询当前用户自己发起的审批流程，只读。"""
    return _approval_read(
        "list_my_approval_applications", "/agent/tools/approvals/applications",
        {"pageNo": max(1, page_no), "pageSize": min(50, max(1, page_size))},
        "正在查询我发起的审批", "approval_applications", tool_call_id,
        page_limit=min(50, max(1, page_size)),
    )


@tool
def get_my_approval_application(
    process_instance_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取当前用户自己发起的一条审批流程详情，只读。"""
    if not str(process_instance_id or "").strip():
        return tool_failure("APPROVAL_PROCESS_ID_REQUIRED", "请提供要查看的审批流程编号。")
    return _approval_read(
        "get_my_approval_application", f"/agent/tools/approvals/applications/{process_instance_id.strip()}",
        message="正在读取审批流程详情", card_type="approval_application", tool_call_id=tool_call_id,
    )


@tool
def list_my_approval_history(
    page_no: int = 1,
    page_size: int = 20,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """查询当前用户已经处理过的审批任务，只读。"""
    return _approval_read(
        "list_my_approval_history", "/agent/tools/approvals/history",
        {"pageNo": max(1, page_no), "pageSize": min(50, max(1, page_size))},
        "正在查询已办审批", "approval_history", tool_call_id,
        page_limit=min(50, max(1, page_size)),
    )


__all__ = [
    "list_my_approval_applications",
    "get_my_approval_application",
    "list_my_approval_history",
]
