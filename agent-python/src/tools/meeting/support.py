from typing import Any

from langgraph.config import get_stream_writer

from ..common import (
    JavaFacadeBusinessError,
    JavaFacadeConnectionError,
    JavaFacadeHttpError,
    JavaFacadeJsonDecodeError,
    JavaFacadeResponseTypeError,
    ToolResponse,
    emit,
    java_post,
    java_post_list,
    tool_failure,
    tool_success,
)


def map_facade_error(exc: Exception) -> tuple[str, str, dict[str, Any]]:
    if isinstance(exc, JavaFacadeConnectionError):
        return "MEETING_FACADE_UNAVAILABLE", "无法连接会议服务，请稍后重试", {"kind": "connection"}
    if isinstance(exc, JavaFacadeHttpError):
        return "MEETING_FACADE_HTTP_ERROR", "会议服务返回 HTTP 错误", {
            "kind": "http", "statusCode": exc.status_code, "path": exc.path,
        }
    if isinstance(exc, JavaFacadeBusinessError):
        return "MEETING_FACADE_BUSINESS_ERROR", exc.message, {
            "kind": "business", "facadeCode": str(exc.code), "path": exc.path,
        }
    if isinstance(exc, JavaFacadeJsonDecodeError):
        return "MEETING_FACADE_INVALID_JSON", "会议服务返回了无法解析的数据", {
            "kind": "json_decode", "statusCode": exc.status_code,
            "contentType": exc.content_type, "path": exc.path,
        }
    if isinstance(exc, JavaFacadeResponseTypeError):
        return "MEETING_FACADE_INVALID_RESPONSE", "会议服务返回了不符合契约的数据类型", {
            "kind": "response_type", "path": exc.path,
            "expectedType": exc.expected_type, "actualType": exc.actual_type,
        }
    return "MEETING_FACADE_INTERNAL_ERROR", "会议服务处理失败，请稍后重试", {
        "kind": "internal", "exceptionType": type(exc).__name__,
    }


def facade_tool_failure(
    writer: Any,
    tool_name: str,
    message: str,
    exc: Exception,
    tool_call_id: str = "",
) -> ToolResponse:
    error_code, user_message, details = map_facade_error(exc)
    event = {"toolName": tool_name, "errorCode": error_code, "details": details}
    if tool_call_id:
        event["toolCallId"] = tool_call_id
    emit(writer, "tool_failed", message, **event)
    return tool_failure(error_code, user_message, details=details)


def post_meeting_tool(
    start_message: str,
    path: str,
    payload: dict[str, Any],
    tool_name: str,
    tool_call_id: str = "",
    response_type: str = "object",
) -> ToolResponse:
    writer = get_stream_writer()
    emit(writer, "tool_started", start_message, toolName=tool_name, toolCallId=tool_call_id)
    try:
        result = java_post_list(path, payload) if response_type == "list" else java_post(path, payload)
    except Exception as exc:
        return facade_tool_failure(
            writer, tool_name, "会议预约查询失败，请稍后重试", exc, tool_call_id
        )
    emit(writer, "tool_completed", "会议预约查询完成", toolName=tool_name, toolCallId=tool_call_id)
    return tool_success(result)
