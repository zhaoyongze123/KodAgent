"""Runtime audit events for parent and generated DeepAgents tools.

Business tools already emit their own domain-aware lifecycle events.  This
middleware deliberately covers only the tools that do not emit events today:
the parent conversation/task tools and DeepAgents' generated ``task`` tool.
Keeping the allow-list explicit is important: adding a generic wrapper around
every Tool would duplicate the meeting/approval/calendar audit stream.
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
    publish_narration,
    sync_runtime_event_context,
)
from ..presentation.narration import stream_model_output_scope


TASK_TOOL_NAME = "task"

# These tools are present in the main graph and currently have no explicit
# tool.started/tool.completed/tool.failed event of their own.
PARENT_TOOL_NAMES = frozenset(
    {
        "route_conversation",
    }
)

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
    return name == TASK_TOOL_NAME or name in PARENT_TOOL_NAMES


def _clean_text(value: Any, *, preserve_markdown: bool = False, max_chars: int = 300) -> str:
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
    if preserve_markdown:
        # Task results are user-facing process正文.  Keep Markdown structure
        # while bounding the audit event size so a huge child response cannot
        # grow the event stream without limit.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text[:max_chars].rstrip()
    return _WHITESPACE.sub(" ", text)[:max_chars].strip()


def _summary_from_value(value: Any, *, preserve_markdown: bool = False, max_chars: int = 300) -> str:
    """Extract a short human-readable sentence without persisting raw JSON."""
    if isinstance(value, ToolMessage):
        return _summary_from_value(value.content, preserve_markdown=preserve_markdown, max_chars=max_chars)
    if isinstance(value, str):
        text = value.strip()
        if text.startswith(("{", "[")):
            try:
                return _summary_from_value(
                    json.loads(text), preserve_markdown=preserve_markdown, max_chars=max_chars
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        return _clean_text(text, preserve_markdown=preserve_markdown, max_chars=max_chars)
    if isinstance(value, dict):
        # Prefer fields intentionally written for user-facing summaries. Do
        # not serialize the complete ToolResponse or its arbitrary data map.
        for key in ("summary", "message", "output", "text", "content"):
            if key in value:
                summary = _summary_from_value(value[key], preserve_markdown=preserve_markdown, max_chars=max_chars)
                if summary:
                    return summary
        for key in ("error", "result", "data"):
            if key in value:
                summary = _summary_from_value(value[key], preserve_markdown=preserve_markdown, max_chars=max_chars)
                if summary:
                    return summary
        return ""
    if isinstance(value, (list, tuple)):
        for item in reversed(value):
            summary = _summary_from_value(item, preserve_markdown=preserve_markdown, max_chars=max_chars)
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
    preserve_markdown = name == TASK_TOOL_NAME
    summary = _summary_from_value(result, preserve_markdown=preserve_markdown, max_chars=8000 if preserve_markdown else 300)
    if name == TASK_TOOL_NAME:
        subagent = _request_subagent_name(request)
        has_child_summary = bool(summary)
        summary = summary or f"子 Agent {subagent} 已完成"
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
        # A child model's final response is streamed through the canonical
        # narration entry. Do not append a second generic completion row.
        # Keep the lifecycle event above as the durable audit fact. If there
        # is no readable child output, retain a short fallback narration.
        if not has_child_summary:
            try:
                publish_narration(
                    writer,
                    stage="agent_message",
                    message=f"子 Agent {subagent} 已{'失败' if failed else '完成'}",
                    tool_call_id=f"{call_id}:completion",
                )
            except Exception:
                # A post-completion narration outage must not convert a
                # completed child workflow into a failed business tool.
                pass
        return
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
    """Audit lifecycle of parent tools and DeepAgents' generated ``task``.

    The middleware observes the call boundary, so it also covers tools that
    return a typed response without explicitly emitting an event.  It never
    logs arguments or full tool output; only a selected readable summary is
    persisted through the existing event writer/Java audit path.
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
            if name == TASK_TOOL_NAME:
                with stream_model_output_scope():
                    result = handler(request)
            else:
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
            if name == TASK_TOOL_NAME:
                with stream_model_output_scope():
                    result = await handler(request)
            else:
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
