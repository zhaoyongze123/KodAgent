"""Prepare a validated meeting request before room/calendar Tools run."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
import re
from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.config import get_stream_writer

from ...domain.meeting import MeetingBookingRequest
from ...services.meeting_request import (
    normalize_attendee_name,
    normalize_attendee_names,
    attendee_conflict_override_requested,
    authorized_current_user_message,
    contains_self_only_attendee_phrase,
    resolve_attendee_results,
    resolve_time_range,
    validate_meeting_request,
)
from ...runtime.operation_payload import merge_operation_payload, operation_payload
from ...runtime.operation_runtime import get_active_operation
from ..common import AGENT_TIMEZONE, ToolResponse, bind_tool_call_id, current_agent_context, emit, java_get, tool_failure, tool_success
from ..common.events import turn_id_from_context
from .support import facade_tool_failure


def prepare_meeting_booking_request_service(
    subject: str = "",
    start_time: str = "",
    end_time: str = "",
    attendee_names: list[str] | None = None,
    room_capacity: int | None = None,
    equipment: list[str] | None = None,
    room_preference: str = "",
    remark: str = "",
    # Only workflow code may provide this field after it has read an
    # applicant-owned source booking from Java.  It is deliberately not part
    # of the public LangChain tool schema, so a model cannot invent user IDs.
    source_attendee_user_ids: list[int] | None = None,
    tool_call_id: str = "",
    state: dict[str, Any] | None = None,
) -> ToolResponse:
    """将会议预约自然语言字段解析为可靠的结构化请求。

    该工具只做解析、人员解析和参数校验，不查询会议室占用，也不创建草稿。
    """
    bind_tool_call_id(tool_call_id)
    context = current_agent_context()
    turn_id = turn_id_from_context(context)
    original_message = _current_user_message(state)
    conflict_policy = (
        "allow_with_warning"
        if attendee_conflict_override_requested(
            authorized_current_user_message(state, expected_message_id=context.get("messageId"))
        )
        else "block"
    )
    attendee_names = normalize_attendee_names(attendee_names)
    subject, start_time, end_time, attendee_names = _fill_missing_fields_from_message(
        original_message,
        subject=subject,
        start_time=start_time,
        end_time=end_time,
        attendee_names=attendee_names,
        remark=remark,
    )
    writer = get_stream_writer()
    start, end, missing_time, time_errors = resolve_time_range(
        start_time, end_time, now=datetime.now(AGENT_TIMEZONE)
    )
    names = normalize_attendee_names(attendee_names)
    request_key = _request_key(
        subject=subject,
        start_time=start.strftime("%Y-%m-%d %H:%M:%S") if start else start_time,
        end_time=end.strftime("%Y-%m-%d %H:%M:%S") if end else end_time,
        attendee_names=names,
        room_capacity=room_capacity,
        equipment=equipment or [],
        room_preference=room_preference,
        remark=remark,
    )
    # The current Operation is the durable retry boundary. It replaces the
    # previous thread-wide task projection and keeps repeated model calls for
    # one message deterministic.
    existing = operation_payload(required=True)
    cached_message_id = str(existing.get("prepareMessageId") or "")
    cached_result = existing.get("preparedResult")
    if (
        turn_id
        and cached_message_id == turn_id
        and isinstance(cached_result, dict)
    ):
        reused = dict(cached_result)
        operation = get_active_operation()
        reused.update({
            "operationId": operation.operation_id if operation is not None else context.get("operationId", ""),
            "operationVersion": operation.operation.version if operation is not None else None,
            "reused": True,
        })
        return tool_success(reused)

    emit(writer, "tool_started", "🧩 正在整理预约时间和参会人信息……", toolName="prepare_meeting_booking_request")
    if source_attendee_user_ids is not None and not names:
        # A time/subject-only update keeps the already-authorized attendee
        # set.  The source came from Java in the workflow's resolve node.
        ids = list(dict.fromkeys(int(item) for item in source_attendee_user_ids))
        resolved_names = [str(item) for item in ids]
        candidates: list[dict[str, Any]] = []
        attendee_errors: list[str] = []
    else:
        current_user = None
        search_results: dict[str, list[dict]] = {}
        try:
            if "当前用户" in names:
                current_user = java_get("/agent/tools/users/me")
            for name in names:
                if name != "当前用户":
                    result = java_get("/agent/tools/users/search", {"keyword": name, "limit": 10})
                    search_results[name] = result.get("users", [])
        except Exception as exc:
            return facade_tool_failure(
                writer, "prepare_meeting_booking_request", "参会人解析失败，请检查参会人信息", exc, tool_call_id
            )

        ids, resolved_names, candidates, attendee_errors = resolve_attendee_results(
            names,
            current_user=current_user,
            search_results=search_results,
        )
    request = MeetingBookingRequest(
        subject=subject.strip() or None,
        start_time=start,
        end_time=end,
        attendee_user_ids=ids,
        attendee_user_names=resolved_names,
        room_capacity=room_capacity,
        equipment=equipment or [],
        room_preference=room_preference.strip() or None,
        remark=remark.strip(),
        conflict_policy=conflict_policy,
    )
    validation = validate_meeting_request(request)
    validation.missing_fields.extend(missing_time)
    validation.errors.extend(time_errors)
    validation.errors.extend(attendee_errors)
    validation.candidates = candidates
    validation.valid = not validation.missing_fields and not validation.errors and not candidates
    result = validation.model_dump(mode="json")
    result.update({
        "messageId": turn_id,
        "runId": context.get("runId", ""),
        "threadId": context.get("threadId", ""),
        "reused": False,
    })
    if not validation.valid:
        # Persist invalid outcomes as well.  This is a stable prompt for the
        # model to ask the user for the exact missing/ambiguous field and also
        # prevents repeated Java searches within this message ID.
        try:
            persisted = merge_operation_payload({
                "preparedResult": result,
                "prepareRequestKey": request_key,
                "prepareMessageId": turn_id,
                "meetingReplan": None,
                "prepareRunId": context.get("runId", ""),
                "prepareThreadId": context.get("threadId", ""),
                "prepareTenantId": context.get("tenantId", ""),
                "prepareUserId": context.get("userId", ""),
            })
            result.update({
                "operationId": persisted.operation_id if persisted else context.get("operationId", ""),
                "operationVersion": persisted.version if persisted else None,
            })
        except Exception as exc:
            return tool_failure(
                "OPERATION_STATE_SAVE_FAILED",
                "预约信息校验结果保存失败，请稍后重试。",
                details=str(exc), retryable=True,
            )
        emit(writer, "tool_completed", "⚠️ 预约信息尚未完整，需要补充或确认", toolName="prepare_meeting_booking_request")
        return tool_success(result)
    persisted = merge_operation_payload({
        "meeting_request": validation.request.model_dump(mode="json"),
        "preparedResult": result,
        "prepareRequestKey": request_key,
        "prepareMessageId": turn_id,
        "meetingReplan": None,
        "prepareRunId": context.get("runId", ""),
        "prepareThreadId": context.get("threadId", ""),
        "prepareTenantId": context.get("tenantId", ""),
        "prepareUserId": context.get("userId", ""),
    })
    emit(writer, "tool_completed", "✅ 预约信息已整理完成，可以查询会议室和日程", toolName="prepare_meeting_booking_request")
    result["operationId"] = persisted.operation_id if persisted else context.get("operationId", "")
    result["operationVersion"] = persisted.version if persisted else None
    result["reused"] = False
    return tool_success(result)


@tool
def prepare_meeting_booking_request(
    subject: str = "", start_time: str = "", end_time: str = "",
    attendee_names: list[str] | None = None, room_capacity: int | None = None,
    equipment: list[str] | None = None, room_preference: str = "", remark: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict[str, Any] | None, InjectedState] = None,
) -> ToolResponse:
    """Agent adapter for the pure meeting-request domain service."""
    return prepare_meeting_booking_request_service(
        subject=subject, start_time=start_time, end_time=end_time,
        attendee_names=attendee_names, room_capacity=room_capacity,
        equipment=equipment, room_preference=room_preference, remark=remark,
        tool_call_id=tool_call_id, state=state,
    )


def _current_user_message(state: dict[str, Any] | None) -> str:
    """Extract the current message used for deterministic field parsing."""
    if not isinstance(state, dict):
        return ""
    authorized = authorized_current_user_message(state)
    if authorized:
        return authorized
    messages = state.get("messages") or []
    for message in reversed(messages):
        role = getattr(message, "type", None) or getattr(message, "role", None)
        if isinstance(message, dict):
            role = message.get("type") or message.get("role")
        if role not in {"human", "user"}:
            continue
        content = getattr(message, "content", None)
        if isinstance(message, dict):
            content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            ).strip()
    return ""


def _fill_missing_fields_from_message(
    message: str,
    *,
    subject: str,
    start_time: str,
    end_time: str,
    attendee_names: list[str] | None,
    remark: str,
) -> tuple[str, str, str, list[str] | None]:
    """Fill only omitted model fields from the current raw user message.

    Explicit Tool arguments always win.  The fallback is deliberately narrow:
    it handles the common booking phrasing we can parse deterministically and
    leaves genuinely ambiguous requests invalid for the user to clarify.
    """
    text = (message or "").strip()
    if not text:
        return subject, start_time, end_time, attendee_names

    inferred_start, inferred_end, _, _ = resolve_time_range(text, "", now=datetime.now(AGENT_TIMEZONE))
    if not start_time and inferred_start:
        start_time = inferred_start.strftime("%Y-%m-%d %H:%M:%S")
    if not end_time and inferred_end:
        end_time = inferred_end.strftime("%Y-%m-%d %H:%M:%S")

    if not subject.strip():
        # The sub-agent passes a structured, multi-line human message.  The
        # label must consume its Chinese/English colon and stop at this line;
        # otherwise the old regex returned ``：自动化验收会议``.
        labelled_subject = re.search(
            r"(?m)^[ \t>*-]*(?:会议主题|主题)[ \t]*[:：][ \t]*([^\r\n，,。；;]+)",
            text,
        )
        if labelled_subject:
            subject = labelled_subject.group(1).strip()
        else:
            match = re.search(r"主题\s*(?:是|为|叫做)?\s*([^，,。；;\n]+)", text)
            if match:
                subject = match.group(1).strip().lstrip("：:").strip()
        # Some older sub-agent prompts put the topic in remark only.  This is
        # a fallback for an empty explicit subject, never an override.
        if not subject.strip() and remark.strip():
            subject = remark.strip()

    if not attendee_names:
        # For a self-only request, canonicalize to 当前用户.  If names are
        # explicitly present, parse only the short list around 参加/参会 and
        # let Java resolve identity and ambiguity.
        attendee_match = re.search(
            r"(?m)^[ \t>*-]*(?:参会人|参加人|参会人员|attendees?)[ \t]*[:：][ \t]*([^\r\n]+)",
            text,
            re.IGNORECASE,
        )
        participant_text = attendee_match.group(1).strip() if attendee_match else text
        # When the model receives the original one-line request rather than
        # the structured sub-agent summary, the self-only value is embedded in
        # prose.  Match the complete phrase so "帮我预约" is not mistaken for
        # a self-only attendee, while "只有我参加" still resolves to /me.
        if contains_self_only_attendee_phrase(participant_text):
            attendee_names = ["当前用户"]
        else:
            names_match = re.search(r"(?:我和|与|和)\s*([^，,。；]+?)\s*(?:参加|参会|出席)", text)
            if names_match:
                raw_names = re.split(r"和|、|及|与", names_match.group(1))
                attendee_names = ["当前用户", *[item.strip() for item in raw_names if item.strip()]]

    return subject, start_time, end_time, attendee_names


def _request_key(**values: object) -> str:
    """Build a per-message idempotency key from normalized request fields."""
    context = current_agent_context()
    payload = {
        "messageId": turn_id_from_context(context),
        "subject": str(values.get("subject") or "").strip(),
        "startTime": str(values.get("start_time") or "").strip(),
        "endTime": str(values.get("end_time") or "").strip(),
        "attendeeNames": list(values.get("attendee_names") or []),
        "roomCapacity": values.get("room_capacity"),
        "equipment": sorted(str(item).strip() for item in (values.get("equipment") or [])),
        "roomPreference": str(values.get("room_preference") or "").strip(),
        "remark": str(values.get("remark") or "").strip(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
