from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.config import get_stream_writer

from ..common import ToolResponse, bind_tool_call_id, current_agent_context, emit, normalize_local_datetime, save_meeting_draft, tool_failure, tool_success
from ...domain.meeting import MeetingBookingRequest
from ...runtime.operation_payload import merge_operation_payload, operation_payload
from ...runtime.operation_runtime import get_active_operation
from .state import AvailabilityCheckError, get_availability_check
from ...services.meeting_draft_idempotency import current_meeting_draft_replay
from ...services.meeting_gate import meeting_request_gate


_REQUEST_CONTEXT_FIELDS = {
    "prepareMessageId": "messageId",
    "prepareRunId": "runId",
    "prepareThreadId": "threadId",
    "prepareTenantId": "tenantId",
    "prepareUserId": "userId",
}


def _canonical_booking_facts(
    *,
    availability_token: str,
    model_room_id: int,
    model_start_time: str,
    model_end_time: str,
    model_user_ids: list[int],
) -> tuple[dict[str, Any] | None, ToolResponse | None]:
    """Load the validated request/check pair for the current user message.

    The model arguments are intentionally not used as business facts. They
    are only an assertion from the model; the prepared request and the short
    lived availability record are authoritative.
    """
    context = current_agent_context()
    facts = operation_payload(required=True)
    if not facts:
        return None, tool_failure("REQUEST_NOT_READY", "当前轮没有已校验的会议预约请求，请先执行预约信息整理")

    for fact_field, context_field in _REQUEST_CONTEXT_FIELDS.items():
        if not facts.get(fact_field) or str(facts.get(fact_field)) != str(context.get(context_field) or ""):
            return None, tool_failure(
                "REQUEST_CONTEXT_INVALID",
                "预约校验上下文已失效，请重新整理本轮预约信息",
                details=f"{fact_field} 与当前 {context_field} 不一致",
            )

    try:
        request = MeetingBookingRequest.model_validate(facts.get("meeting_request") or {})
    except Exception as exc:
        return None, tool_failure("REQUEST_NOT_READY", "当前轮预约信息不是有效的结构化请求", details=str(exc))
    if not request.subject or not request.start_time or not request.end_time or not request.attendee_user_ids:
        return None, tool_failure("REQUEST_NOT_READY", "当前轮预约信息尚未完整，请先重新整理预约请求")

    canonical_start = normalize_local_datetime(request.start_time.isoformat())
    canonical_end = normalize_local_datetime(request.end_time.isoformat())
    availability_fact = facts.get("meeting_availability") or {}
    stored_token = str(
        facts.get("availabilityToken")
        or availability_fact.get("availabilityToken")
        or ""
    )
    token = availability_token.strip() or stored_token
    if not token:
        return None, tool_failure("AVAILABILITY_CHECK_REQUIRED", "缺少当前轮可预约性检查 Token，请先重新检查会议室")
    if stored_token and token != stored_token:
        return None, tool_failure("AVAILABILITY_CONTEXT_INVALID", "可预约性检查 Token 不是当前轮已验证的结果")

    try:
        canonical_room_id = int(availability_fact.get("meetingRoomId"))
    except (TypeError, ValueError):
        return None, tool_failure("AVAILABILITY_CHECK_REQUIRED", "当前轮没有已验证的会议室，请重新检查可用性")

    canonical_ids = list(dict.fromkeys(int(user_id) for user_id in request.attendee_user_ids))
    try:
        availability = get_availability_check(
            token,
            meeting_room_id=canonical_room_id,
            user_ids=canonical_ids,
            start_time=canonical_start,
            end_time=canonical_end,
        )
    except AvailabilityCheckError as exc:
        return None, tool_failure("AVAILABILITY_CHECK_REQUIRED", str(exc))

    # Keep model fields available only as diagnostics.  None of them can
    # override the canonical request/check values below.
    assertion_mismatches = {}
    if model_room_id and int(model_room_id) != canonical_room_id:
        assertion_mismatches["meeting_room_id"] = {"model": model_room_id, "canonical": canonical_room_id}
    if model_user_ids and list(dict.fromkeys(model_user_ids)) != canonical_ids:
        assertion_mismatches["attendee_user_ids"] = {"model": model_user_ids, "canonical": canonical_ids}
    if model_start_time and model_start_time != canonical_start:
        assertion_mismatches["start_time"] = {"model": model_start_time, "canonical": canonical_start}
    if model_end_time and model_end_time != canonical_end:
        assertion_mismatches["end_time"] = {"model": model_end_time, "canonical": canonical_end}

    return {
        "subject": request.subject.strip(),
        "meetingRoomId": canonical_room_id,
        "meetingRoomName": str(availability.get("meetingRoomName") or availability_fact.get("meetingRoomName") or ""),
        "startTime": canonical_start,
        "endTime": canonical_end,
        "attendeeUserIds": canonical_ids,
        "attendeeUserNames": availability.get("attendeeUserNames") or availability_fact.get("attendeeUserNames") or [str(user_id) for user_id in canonical_ids],
        "remark": request.remark.strip(),
        "conflictPolicy": request.conflict_policy,
        "availability": availability,
        "assertionMismatches": assertion_mismatches,
    }, None


def create_meeting_booking_draft_service(
    subject: str, meeting_room_id: int, start_time: str, end_time: str,
    attendee_user_ids: list[int] | None = None, remark: str = "",
    meeting_room_name: str = "",
    availability_token: str = "", allow_conflict_override: bool = False,
    tool_call_id: str = "",
    state: dict[str, Any] | None = None,
) -> ToolResponse:
    """生成预约草稿。默认要求可预约性检查无冲突；只有用户明确要求忽略冲突时才能覆盖。"""
    bind_tool_call_id(tool_call_id)
    blocked = meeting_request_gate(require_ready=True)
    if blocked:
        return blocked
    replay = current_meeting_draft_replay()
    if replay:
        # Middleware normally handles this before the Tool node.  Keep the
        # same guard inside the handler so a direct call or an older runtime
        # cannot save the same Java draft twice.
        return tool_success(replay)
    canonical, failure = _canonical_booking_facts(
        availability_token=availability_token,
        model_room_id=meeting_room_id,
        model_start_time=start_time,
        model_end_time=end_time,
        model_user_ids=list(attendee_user_ids or []),
    )
    if failure:
        return failure
    assert canonical is not None
    availability = canonical.pop("availability")
    assertion_mismatches = canonical.pop("assertionMismatches")
    room_conflict = bool(availability["roomConflicts"])
    attendee_conflict = bool(availability["attendeeConflicts"])
    # The model boolean is intentionally ignored.  Only the canonical request
    # persisted by prepare/update can authorize attendee conflicts.  A room
    # conflict remains a hard stop regardless of policy or model arguments.
    conflict_override_authorized = canonical.get("conflictPolicy") == "allow_with_warning"
    if room_conflict or (attendee_conflict and not conflict_override_authorized):
        emit(get_stream_writer(), "conflict_blocked", "⚠️ 检测到参会人或会议室冲突，未生成普通预约草稿", toolName="create_meeting_booking_draft", toolCallId=tool_call_id, success=False)
        return tool_success({"blocked": True, "requires_conflict_decision": attendee_conflict and not room_conflict, "message": "会议室或参会人存在冲突，未生成预约草稿。", "attendeeConflicts": availability["attendeeConflicts"], "roomConflicts": availability["roomConflicts"]})
    draft = {
        **canonical,
        "hasConflictOverride": attendee_conflict and conflict_override_authorized,
        "modelAssertionMismatches": assertion_mismatches,
        # Java creates the durable approval record from the same business
        # context, so a resumed approval cannot be detached from its Run.
        **current_agent_context(),
    }
    # A request edited after a committed booking is an UPDATE, not a second
    # CREATE.  The source facts come from the Agent facade detail endpoint and
    # are re-checked by Java at commit time.
    task_facts = operation_payload(required=True)
    operation = str(task_facts.get("meeting_operation") or "CREATE").upper()
    draft["operation"] = operation
    if operation == "UPDATE":
        source = task_facts.get("meeting_source_booking") or {}
        source_id = source.get("bookingId")
        if source_id is None:
            return tool_failure("SOURCE_BOOKING_REQUIRED", "修改会议前必须先选择本人创建的原会议预约")
        draft.update({
            "sourceBookingId": int(source_id),
            "sourceStartTime": str(source.get("startTime") or ""),
            "sourceEndTime": str(source.get("endTime") or ""),
            "sourceSubject": str(source.get("subject") or ""),
        })
    active_operation = get_active_operation()
    if active_operation is None:
        return tool_failure("OPERATION_REQUIRED", "会议预约草稿缺少 Operation 绑定，请重新发起预约")
    draft["operationId"] = active_operation.operation_id
    draft["idempotencyKey"] = f"{active_operation.operation_id}:{draft.get('messageId') or 'draft'}:{operation}:{draft.get('sourceBookingId') or ''}"
    try:
        saved = save_meeting_draft(draft)
    except Exception as exc:
        return tool_failure("DRAFT_SAVE_FAILED", "预约草稿保存失败，请稍后重试", details=str(exc))
    token = saved.get("draftId") or saved.get("id")
    if not token:
        return tool_failure("DRAFT_ID_MISSING", "Java 未返回有效 draftId")
    approval_id = saved.get("approvalId")
    if not approval_id:
        return tool_failure("APPROVAL_ID_MISSING", "Java 未返回有效 approvalId")
    draft["draftId"] = str(token)
    draft["approvalId"] = approval_id
    active_operation.bind_approval(str(approval_id))
    if active_operation.operation.status == "COLLECTING_INFO":
        active_operation.transition("READY", event_type="operation.ready")
    if active_operation.operation.status == "READY":
        active_operation.transition("RUNNING", event_type="operation.running")
    if active_operation.operation.status == "RUNNING":
        active_operation.transition("WAITING_APPROVAL", event_type="operation.waiting_approval")
    persisted = merge_operation_payload({
        "meeting_booking_draft": draft,
        "confirmation_token": token,
        "approvalId": approval_id,
        "meeting_operation": operation,
        "meeting_replan": None,
    })
    operation_version = persisted.version if persisted else active_operation.operation.version
    writer = get_stream_writer()
    emit(writer, "draft.created", "📝 预约草稿已生成，等待用户确认", toolName="create_meeting_booking_draft", toolCallId=tool_call_id, draftId=token, approvalId=approval_id, operationId=active_operation.operation_id, draft=draft)
    return tool_success({"requires_confirmation": True, "confirmation_token": token, "draftId": token, "approvalId": approval_id,
                         "operationId": active_operation.operation_id, "operationVersion": operation_version,
                         "draft": draft,
                         "message": "预约草稿已生成，用户确认后才能正式提交。"})


@tool
def create_meeting_booking_draft(
    subject: str, meeting_room_id: int, start_time: str, end_time: str,
    attendee_user_ids: list[int] | None = None, remark: str = "",
    meeting_room_name: str = "", availability_token: str = "",
    allow_conflict_override: bool = False,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
    state: Annotated[dict[str, Any] | None, InjectedState] = None,
) -> ToolResponse:
    """Agent adapter for the durable meeting-draft service."""
    return create_meeting_booking_draft_service(
        subject=subject, meeting_room_id=meeting_room_id, start_time=start_time,
        end_time=end_time, attendee_user_ids=attendee_user_ids, remark=remark,
        meeting_room_name=meeting_room_name, availability_token=availability_token,
        allow_conflict_override=allow_conflict_override, tool_call_id=tool_call_id,
        state=state,
    )
