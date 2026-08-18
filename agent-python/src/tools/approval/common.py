"""Shared implementation helpers for approval Tool modules.

This module contains transport/presentation adapters only.  It does not own a
particular approval operation, which keeps the domain modules independent and
prevents circular imports during the migration from ``query.py``.
"""

from __future__ import annotations

from typing import Any

from langgraph.config import get_stream_writer

from ..common import (
    ToolResponse,
    bind_tool_call_id,
    emit,
    java_get,
    tool_failure,
    tool_success,
)


SUPPORTED_TYPES = {"leave": "请假", "trip": "出差"}


def bounded_approval_page(
    result: Any,
    requested_limit: int,
    *,
    collection_key: str,
) -> dict[str, Any]:
    """Apply a canonical page boundary to a Java response."""
    payload = dict(result) if isinstance(result, dict) else {}
    try:
        limit = max(1, min(int(requested_limit), 50))
    except (TypeError, ValueError):
        limit = 20
    values = payload.get(collection_key)
    if not isinstance(values, list):
        values = []
    server_count = len(values)
    bounded = values[:limit]
    payload[collection_key] = bounded
    payload["requestedLimit"] = limit
    payload["pageSize"] = limit
    payload["serverReturnedCount"] = server_count
    payload["returnedCount"] = len(bounded)
    payload["boundedByPlan"] = server_count > limit
    return payload


def approval_failure(
    writer: Any,
    tool_name: str,
    tool_call_id: str,
    message: str,
    exc: Exception,
) -> ToolResponse:
    emit(writer, "tool_failed", message, toolName=tool_name, toolCallId=tool_call_id,
         errorCode="APPROVAL_FACADE_UNAVAILABLE")
    return tool_failure("APPROVAL_FACADE_UNAVAILABLE", message, details=str(exc))


def request_payload(
    request_type: str,
    start_time: str,
    end_time: str,
    approval_type: int | None,
    reason: str,
) -> tuple[dict[str, Any] | None, ToolResponse | None]:
    normalized_type = request_type.strip().lower()
    if normalized_type not in SUPPORTED_TYPES:
        return None, tool_failure(
            "APPROVAL_TYPE_UNSUPPORTED",
            "当前 Agent 仅支持请假和出差审批；其他流程请在 OA 中发起。",
        )
    if not start_time.strip() or not end_time.strip() or approval_type is None or not reason.strip():
        return None, tool_failure(
            "APPROVAL_FIELDS_INCOMPLETE",
            "请补充开始时间、结束时间、类型和原因后再发起审批。",
        )
    return {
        "requestType": normalized_type,
        "startTime": start_time.strip(),
        "endTime": end_time.strip(),
        "type": approval_type,
        "reason": reason.strip(),
    }, None


def approval_read(
    tool_name: str,
    endpoint: str,
    params: dict[str, Any] | None = None,
    message: str = "正在查询审批记录",
    card_type: str = "approval_inbox",
    tool_call_id: str = "",
    page_limit: int | None = None,
) -> ToolResponse:
    """Shared read-only adapter for applications and history."""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    emit(writer, "tool_started", f"🔧 {message}……", toolName=tool_name, toolCallId=tool_call_id)
    try:
        result = java_get(endpoint, params or {})
    except Exception as exc:
        return approval_failure(writer, tool_name, tool_call_id, f"{message}失败，请稍后重试", exc)
    if page_limit is not None:
        result = bounded_approval_page(result, page_limit, collection_key="items")
    presentation = {"blockType": "card", "cardType": card_type}
    emit(writer, "tool_completed", f"✅ {message}完成", toolName=tool_name,
         toolCallId=tool_call_id, result=result, presentation=presentation)
    return tool_success(result, presentation)


__all__ = ["SUPPORTED_TYPES", "approval_failure", "approval_read", "bounded_approval_page", "request_payload"]
