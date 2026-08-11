"""Runtime audit events for generated DeepAgents tools.

Business tools already emit their own domain-aware lifecycle events.  This
middleware deliberately covers only DeepAgents' generated ``task`` tool.
Route and domain tools emit their own business-aware audit facts; adding a
generic lifecycle row for them exposes implementation names in the UI.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.errors import GraphBubbleUp

from ..tools.common.events import (
    bind_tool_call_id,
    current_agent_context,
    emit,
    sync_runtime_event_context,
)


TASK_TOOL_NAME = "task"

# Domain tools intentionally excluded because they already call emit().  This
# is documentation as well as a guard against a later broadening of the
# automatic allow-list.
MANUAL_EVENT_TOOL_NAMES = frozenset(
    {
        "report_progress",
        "prepare_meeting_booking_request",
        "list_available_meeting_rooms",
        "search_meeting_attendees",
        "get_current_meeting_user",
        "get_meeting_attendees_calendar",
        "check_meeting_room_conflict",
        "check_meeting_availability",
        "check_meeting_availability_batch",
        "create_meeting_booking_draft",
        "confirm_meeting_booking",
        "list_my_pending_approvals",
        "get_my_calendar",
        "search_party_files",
        "get_party_file_detail",
        "get_party_file_attachments",
        "get_party_file_attachment",
        "list_party_file_categories",
    }
)

_WHITESPACE = re.compile(r"\s+")
_SENSITIVE_TEXT = re.compile(
    r"(?i)(confirmation[_-]?token|identity[_-]?ticket|api[_-]?key|access[_-]?token|refresh[_-]?token)"
    r"\s*[:=]\s*(['\"]?)[^,}\s'\"]+\2"
)


def _call_value(call: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = call.get(key)
        if value is not None:
            return value
    return None


def _tool_name(request: Any) -> str:
    call = getattr(request, "tool_call", {}) or {}
    name = _call_value(call, "name")
    if name:
        return str(name)
    tool = getattr(request, "tool", None)
    return str(getattr(tool, "name", "") or "")


def _tool_call_id(request: Any) -> str:
    call = getattr(request, "tool_call", {}) or {}
    value = _call_value(call, "id", "tool_call_id", "toolCallId")
    return str(value) if value else f"audit:{current_agent_context()['runId']}:{time.time_ns()}"


def _is_audited_tool(name: str) -> bool:
    if name in MANUAL_EVENT_TOOL_NAMES:
        return False
    return name == TASK_TOOL_NAME


def _clean_text(value: Any, *, max_chars: int = 300) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, (int, float, bool)):
        text = str(value)
    else:
        text = ""
    text = _SENSITIVE_TEXT.sub(r"\1=***REDACTED***", text)
    text = text.strip()
    return _WHITESPACE.sub(" ", text)[:max_chars].strip()


def _summary_from_value(value: Any, *, max_chars: int = 300) -> str:
    """Extract a short human-readable sentence without persisting raw JSON."""
    if isinstance(value, ToolMessage):
        return _summary_from_value(value.content, max_chars=max_chars)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                return _summary_from_value(json.loads(text), max_chars=max_chars)
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return _clean_text(text, max_chars=max_chars)
    if isinstance(value, dict):
        # Prefer fields intentionally written for user-facing summaries. Do
        # not serialize the complete ToolResponse or its arbitrary data map.
        for key in ("summary", "message", "output", "text", "content"):
            if key in value:
                summary = _summary_from_value(value[key], max_chars=max_chars)
                if summary:
                    return summary
        for key in ("error", "result", "data"):
            if key in value:
                summary = _summary_from_value(value[key], max_chars=max_chars)
                if summary:
                    return summary
        return ""
    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            summary = _summary_from_value(item, max_chars=max_chars)
            if summary:
                return summary
    return ""


def _request_subagent_name(request: Any) -> str:
    args = (getattr(request, "tool_call", {}) or {}).get("args") or {}
    if not isinstance(args, dict):
        return "子 Agent"
    value = args.get("subagent_type") or args.get("subagentType") or args.get("name")
    return str(value).strip() if value else "子 Agent"


def _result_failed(result: Any) -> bool:
    if isinstance(result, ToolMessage):
        if str(getattr(result, "status", "") or "").lower() in {"error", "failed", "failure"}:
            return True
        return _result_failed(result.content)
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        return _result_failed(parsed)
    status = str(getattr(result, "status", "") or "").lower()
    if status in {"error", "failed", "failure"}:
        return True
    if isinstance(result, dict):
        if result.get("ok") is False:
            return True
        return str(result.get("status", "")).lower() in {"error", "failed", "failure"}
    return False


def _emit_started(name: str, call_id: str, request: Any) -> None:
    sync_runtime_event_context()
    bind_tool_call_id(call_id)
    writer = get_stream_writer()
    if name == TASK_TOOL_NAME:
        subagent = _request_subagent_name(request)
        emit(
            writer,
            "subagent.started",
            f"正在调用子 Agent：{subagent}",
            toolName=TASK_TOOL_NAME,
            subagentName=subagent,
            toolCallId=call_id,
        )
        return
    emit(
        writer,
        "tool.started",
        f"正在调用工具：{name}",
        toolName=name,
        toolCallId=call_id,
    )


def _emit_finished(name: str, call_id: str, request: Any, result: Any, duration_ms: int) -> None:
    writer = get_stream_writer()
    failed = _result_failed(result)
    if name == TASK_TOOL_NAME:
        subagent = _request_subagent_name(request)
        # The child ToolMessage is an internal handoff to the parent Agent.
        # Its natural-language final answer (or JSON) must never be copied
        # into a user-visible event: the parent synthesis is the sole final
        # answer owner. Keep only a content-free lifecycle checkpoint here;
        # child report_progress and workflow events are emitted independently.
        summary = (
            "领域任务执行失败"
            if failed
            else "领域任务已完成，正在整理结果"
        )
        emit(
            writer,
            "subagent.completed",
            summary,
            toolName=TASK_TOOL_NAME,
            subagentName=subagent,
            toolCallId=call_id,
            success=not failed,
            durationMs=duration_ms,
            summary=summary,
        )
        return
    summary = _summary_from_value(result, max_chars=300)
    summary = summary or f"工具 {name} 已完成"
    emit(
        writer,
        "tool.failed" if failed else "tool.completed",
        summary,
        toolName=name,
        toolCallId=call_id,
        success=not failed,
        durationMs=duration_ms,
        summary=summary,
    )


class ToolAuditMiddleware(AgentMiddleware):
    """Audit lifecycle of DeepAgents' generated ``task`` only.

    The middleware observes the call boundary, so it also covers tools that
    return a typed response without explicitly emitting an event.  It never
    logs arguments or full tool output. In particular, a generated ``task``
    stores only its lifecycle state; the child ToolMessage remains available
    to parent synthesis but is never a user-visible process narration.
    """

    name = "ToolAuditMiddleware"

    def wrap_tool_call(self, request, handler):
        name = _tool_name(request)
        if not _is_audited_tool(name):
            return handler(request)
        call_id = _tool_call_id(request)
        started_at = time.perf_counter()
        _emit_started(name, call_id, request)
        try:
            result = handler(request)
        except GraphBubbleUp:
            # HITL interrupts are control-flow, not failed tool executions.
            # Preserve the exception unchanged so LangGraph checkpoints and
            # exposes the interrupt to the caller.
            raise
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
            writer = get_stream_writer()
            emit(
                writer,
                "subagent.completed" if name == TASK_TOOL_NAME else "tool.failed",
                _clean_text(str(exc))[:300] or f"工具 {name} 执行失败",
                toolName=name,
                toolCallId=call_id,
                success=False,
                durationMs=duration_ms,
                errorCode="TOOL_EXECUTION_FAILED",
            )
            raise
        _emit_finished(name, call_id, request, result, max(1, int((time.perf_counter() - started_at) * 1000)))
        return result

    async def awrap_tool_call(self, request, handler):
        name = _tool_name(request)
        if not _is_audited_tool(name):
            return await handler(request)
        call_id = _tool_call_id(request)
        started_at = time.perf_counter()
        _emit_started(name, call_id, request)
        try:
            result = await handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            duration_ms = max(1, int((time.perf_counter() - started_at) * 1000))
            writer = get_stream_writer()
            emit(
                writer,
                "subagent.completed" if name == TASK_TOOL_NAME else "tool.failed",
                _clean_text(str(exc))[:300] or f"工具 {name} 执行失败",
                toolName=name,
                toolCallId=call_id,
                success=False,
                durationMs=duration_ms,
                errorCode="TOOL_EXECUTION_FAILED",
            )
            raise
        _emit_finished(name, call_id, request, result, max(1, int((time.perf_counter() - started_at) * 1000)))
        return result
