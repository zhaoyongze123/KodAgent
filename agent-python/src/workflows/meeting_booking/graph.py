"""LangGraph subgraph for the fixed meeting-room booking sequence.

The graph deliberately reuses the existing domain services. Operation is the
workflow fact source; LangGraph state only carries the current invocation and
the Java facade remains the authority for business records.
"""

from __future__ import annotations

import json
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from ...runtime.operation_payload import merge_operation_payload, operation_payload
from ...runtime.operation_runtime import (
    OperationRuntime,
    action_id_for,
    get_active_operation,
    reset_active_operation,
    set_active_operation,
)
from ...tools.common import ToolResponse, bind_agent_context, current_agent_context, emit, set_message_context, tool_failure
from ...tools.meeting.manage import (
    create_meeting_booking_cancellation_draft_service,
    get_my_meeting_booking_service,
)
from .service import (
    check_meeting_availability_batch_service,
    create_meeting_booking_draft_service,
    list_available_meeting_rooms_service,
    prepare_meeting_booking_request_service,
)
from ..runtime import WorkflowRuntime
from ..runtime_context import (
    get_workflow_runtime,
    reset_workflow_runtime,
    set_workflow_runtime,
)
from .contracts import MeetingBookingWorkflowOutcome, outcome_from_tool_error
from .state import MeetingBookingWorkflowState

# Compatibility names for existing graph test doubles. Production values are
# plain domain-service functions, never LangChain Tool objects.
prepare_meeting_booking_request = prepare_meeting_booking_request_service
list_available_meeting_rooms = list_available_meeting_rooms_service
check_meeting_availability_batch = check_meeting_availability_batch_service
create_meeting_booking_draft = create_meeting_booking_draft_service


def _stream_writer() -> Any:
    try:
        return get_stream_writer()
    except RuntimeError:
        return None


def _tool_data(response: Any) -> tuple[dict[str, Any] | None, Any | None]:
    if isinstance(response, str):
        try:
            response = ToolResponse.model_validate(json.loads(response))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, tool_failure("WORKFLOW_TOOL_FAILED", "会议预约工具返回了无效 JSON 结果").error
    if isinstance(response, ToolResponse):
        if not response.ok:
            return None, response.error
        return response.data if isinstance(response.data, dict) else {}, None
    if isinstance(response, dict):
        if response.get("ok") is False:
            return None, response.get("error")
        return response.get("data", response), None
    return None, tool_failure("WORKFLOW_TOOL_FAILED", "会议预约工具返回了无效结果").error


def _operation_id() -> str | None:
    operation = get_active_operation()
    if operation is not None:
        return operation.operation_id
    return str(current_agent_context().get("operationId") or "") or None


def _invoke_service(service: Any, payload: dict[str, Any]) -> Any:
    candidate = getattr(service, "func", None)
    return candidate(**payload) if callable(candidate) else service(**payload)


def _invoke_node(service: Any, state: MeetingBookingWorkflowState) -> dict[str, Any]:
    """Run a graph node under the parent Agent's trusted request context.

    The compiled meeting graph is a nested LangGraph invocation.  Its child
    RunnableConfig is not guaranteed to carry the Gateway metadata that
    identifies the current user turn.  Binding the serializable envelope at
    the node boundary keeps Operation reads/writes, Java Facade calls and
    gate checks on one identity without placing ContextVars in checkpointed
    state.
    """
    # Direct graph callers (tests and internal adapters) may not populate the
    # serialized field; preserve the already-bound parent ContextVar in that
    # case instead of replacing it with an all-empty envelope.
    context = state.get("runtime_context") or current_agent_context()
    with bind_agent_context(context):
        return service(state)


def _emit_node(state: MeetingBookingWorkflowState, name: str, text: str, *, status: str) -> None:
    runtime = get_workflow_runtime()
    if runtime is None:
        runtime = WorkflowRuntime("meeting_booking", writer=_stream_writer(), emit_fn=emit)
    if status == "started":
        runtime.node_started(name, text)
    elif status in {"completed", "needs_input"}:
        if status == "needs_input":
            runtime.blocked(name, text)
        else:
            runtime.node_completed(name, text)
    elif status == "blocked":
        runtime.blocked(name, text)
    else:
        runtime.failed(text, node=name)


def _prepare(state: MeetingBookingWorkflowState) -> dict[str, Any]:
    _emit_node(state, "prepare_request", "正在整理会议主题、时间和参会人", status="started")
    source = state.get("source_result") or {}
    operation = str(state.get("operation") or "CREATE").upper()
    prepare_payload = {
        # For an UPDATE, omitted fields deliberately retain the Java-read
        # source values. The model only controls the fields it explicitly
        # supplied for this turn.
        "subject": state.get("subject") or source.get("subject") or "",
        "start_time": state.get("start_time") or source.get("startTime") or "",
        "end_time": state.get("end_time") or source.get("endTime") or "",
        "attendee_names": state.get("attendee_names"),
        "room_capacity": state.get("room_capacity"),
        "equipment": state.get("equipment"),
        "room_preference": state.get("room_preference", ""),
        "remark": state.get("remark", ""),
        "tool_call_id": f"{state.get('tool_call_id', 'workflow')}:prepare",
        "state": state.get("parent_state"),
    }
    if operation == "UPDATE":
        prepare_payload["source_attendee_user_ids"] = list(source.get("attendeeUserIds") or [])
    response = _invoke_service(prepare_meeting_booking_request, prepare_payload)
    data, error = _tool_data(response)
    if error:
        outcome = outcome_from_tool_error(error, operation_id=_operation_id())
        _emit_node(state, "prepare_request", outcome.message, status="failed")
        return {"outcome": outcome.model_dump(mode="json")}
    assert data is not None
    if data.get("valid") is False:
        status = "AMBIGUOUS_ENTITY" if data.get("candidates") else "NEEDS_INPUT"
        outcome = MeetingBookingWorkflowOutcome(
            status=status,
            message="请补充或确认预约信息后继续。",
            operation_id=str(data.get("operationId") or _operation_id() or ""),
            facts=data,
        )
        _emit_node(state, "prepare_request", outcome.message, status="needs_input")
        return {"prepare_result": data, "outcome": outcome.model_dump(mode="json")}
    operation_runtime = get_active_operation()
    if operation_runtime is not None and operation_runtime.operation.status == "COLLECTING_INFO":
        operation_runtime.transition("READY", event_type="operation.ready")
    if operation == "UPDATE":
        # Keep the Java-read source on the same Operation so the draft adapter
        # must emit UPDATE + sourceBookingId, never CREATE.
        try:
            merge_operation_payload({
                "meeting_operation": "UPDATE",
                "meeting_source_booking": source,
            })
        except Exception as exc:
            outcome = MeetingBookingWorkflowOutcome(
                status="FAILED", message="无法保存会议修改的来源预约信息。", operation_id=_operation_id(),
                error_code="MEETING_SOURCE_CONTEXT_SAVE_FAILED", retryable=True,
                facts={"details": str(exc)},
            )
            _emit_node(state, "prepare_request", outcome.message, status="failed")
            return {"prepare_result": data, "outcome": outcome.model_dump(mode="json")}
    _emit_node(state, "prepare_request", "预约信息已整理完成", status="completed")
    return {"prepare_result": data}


def _resolve_source(state: MeetingBookingWorkflowState) -> dict[str, Any]:
    operation = str(state.get("operation") or "CREATE").upper()
    if operation == "CREATE":
        return {}
    if operation not in {"UPDATE", "CANCEL"}:
        outcome = MeetingBookingWorkflowOutcome(
            status="NEEDS_INPUT",
            message="请说明要新建、修改还是取消会议预约。",
            operation_id=_operation_id(),
            error_code="MEETING_OPERATION_INVALID",
        )
        return {"outcome": outcome.model_dump(mode="json")}
    source_id = state.get("source_booking_id")
    if not source_id:
        # A write operation must name its source explicitly. Read results are
        # projections, not hidden mutation context.
        source_id = None
    try:
        source_id = int(source_id) if source_id is not None else None
    except (TypeError, ValueError):
        source_id = None
    if not source_id:
        outcome = MeetingBookingWorkflowOutcome(
            status="NEEDS_INPUT",
            message="请指定要修改或取消的会议预约；可先查询我的会议安排后选择预约编号。",
            operation_id=_operation_id(),
            error_code="MEETING_SOURCE_REQUIRED",
        )
        _emit_node(state, "resolve_source", outcome.message, status="needs_input")
        return {"outcome": outcome.model_dump(mode="json")}
    _emit_node(state, "resolve_source", "正在核验原会议预约", status="started")
    response = _invoke_service(get_my_meeting_booking_service, {
        "booking_id": source_id,
        "tool_call_id": f"{state.get('tool_call_id', 'workflow')}:source",
    })
    data, error = _tool_data(response)
    if error or data is None:
        outcome = outcome_from_tool_error(error, operation_id=_operation_id())
        outcome.message = "无法读取原会议预约，可能不存在或您无权修改。"
        outcome.error_code = str(getattr(error, "code", None) or "MEETING_SOURCE_READ_FAILED")
        _emit_node(state, "resolve_source", outcome.message, status="failed")
        return {"outcome": outcome.model_dump(mode="json")}
    if not data.get("editable"):
        outcome = MeetingBookingWorkflowOutcome(
            status="FAILED", message="只能修改或取消由您发起的会议预约。", operation_id=_operation_id(),
            error_code="MEETING_BOOKING_NOT_OWNER",
        )
        _emit_node(state, "resolve_source", outcome.message, status="failed")
        return {"outcome": outcome.model_dump(mode="json")}
    if str(data.get("status") or "") not in {"", "1"}:
        outcome = MeetingBookingWorkflowOutcome(
            status="FAILED", message="该会议预约已取消，不能再次修改或取消。", operation_id=_operation_id(),
            error_code="MEETING_BOOKING_ALREADY_CANCELLED",
        )
        _emit_node(state, "resolve_source", outcome.message, status="failed")
        return {"outcome": outcome.model_dump(mode="json")}
    _emit_node(state, "resolve_source", "已核验原会议预约", status="completed")
    return {"source_booking_id": source_id, "source_result": data}


def _create_cancellation_draft(state: MeetingBookingWorkflowState) -> dict[str, Any]:
    _emit_node(state, "create_cancellation_draft", "正在生成会议取消草稿", status="started")
    response = _invoke_service(create_meeting_booking_cancellation_draft_service, {
        "booking_id": state.get("source_booking_id"),
        "cancel_reason": str(state.get("cancel_reason") or ""),
        "tool_call_id": f"{state.get('tool_call_id', 'workflow')}:cancel-draft",
    })
    data, error = _tool_data(response)
    if error or data is None or not data.get("requires_confirmation"):
        outcome = outcome_from_tool_error(error, operation_id=_operation_id())
        outcome.message = str((data or {}).get("message") or outcome.message)
        outcome.error_code = str(getattr(error, "code", None) or "CANCEL_DRAFT_NOT_CREATED")
        _emit_node(state, "create_cancellation_draft", outcome.message, status="failed")
        return {"outcome": outcome.model_dump(mode="json")}
    outcome = MeetingBookingWorkflowOutcome(
        status="DRAFT_READY", message="会议取消草稿已生成，等待用户确认。",
        operation_id=str(data.get("operationId") or _operation_id() or ""),
        draft_id=str(data.get("draftId") or ""), approval_id=str(data.get("approvalId") or ""),
        confirmation_token=str(data.get("confirmation_token") or ""), facts=data,
    )
    operation_runtime = get_active_operation()
    if operation_runtime is not None:
        if data.get("approvalId"):
            operation_runtime.bind_approval(str(data["approvalId"]))
        if operation_runtime.operation.status == "COLLECTING_INFO":
            operation_runtime.transition("READY", event_type="operation.ready")
        if operation_runtime.operation.status == "READY":
            operation_runtime.transition("RUNNING", event_type="operation.running")
        if operation_runtime.operation.status == "RUNNING":
            operation_runtime.transition("WAITING_APPROVAL", event_type="operation.waiting_approval")
    _emit_node(state, "create_cancellation_draft", outcome.message, status="completed")
    return {"draft_result": data, "outcome": outcome.model_dump(mode="json")}


def _list_rooms(state: MeetingBookingWorkflowState) -> dict[str, Any]:
    operation_runtime = get_active_operation()
    if operation_runtime is not None and operation_runtime.operation.status == "READY":
        operation_runtime.transition("RUNNING", event_type="operation.running")
    _emit_node(state, "list_candidate_rooms", "正在查询启用的会议室", status="started")
    response = _invoke_service(list_available_meeting_rooms, {
        "tool_call_id": f"{state.get('tool_call_id', 'workflow')}:rooms",
    })
    data, error = _tool_data(response)
    if error:
        outcome = outcome_from_tool_error(error, operation_id=_operation_id())
        _emit_node(state, "list_candidate_rooms", outcome.message, status="failed")
        return {"outcome": outcome.model_dump(mode="json")}
    assert data is not None
    rooms = data.get("rooms") or []
    # A plain reschedule retains the original room.  Changing a room is an
    # explicit request (room_preference/capacity/equipment), not an accidental
    # consequence of the recommendation sort order.
    source = state.get("source_result") or {}
    if (
        str(state.get("operation") or "CREATE").upper() == "UPDATE"
        and source.get("meetingRoomId") is not None
        and not state.get("room_preference")
        and not state.get("room_capacity")
        and not state.get("equipment")
    ):
        # The Java Facade's room-list contract historically returned ``id``;
        # the workflow's internal contract uses ``meetingRoomId``.  Normalize
        # both forms before retaining the source room for a plain reschedule.
        # Without this, every UPDATE was reduced to an empty candidate list
        # even when the source room was free at the requested time.
        source_room_id = str(source.get("meetingRoomId"))
        retained_rooms = []
        for room in rooms:
            if not isinstance(room, dict):
                continue
            room_id = room.get("meetingRoomId", room.get("id"))
            if str(room_id) == source_room_id:
                retained_rooms.append({**room, "meetingRoomId": room_id})
        rooms = retained_rooms
        data = {**data, "rooms": rooms}
    if not rooms:
        outcome = MeetingBookingWorkflowOutcome(
            status="CONFLICT_BLOCKED",
            message="当前没有可用的会议室候选。",
            operation_id=_operation_id(),
            facts={"rooms": []},
            error_code="NO_MEETING_ROOMS",
            retryable=True,
        )
        _emit_node(state, "list_candidate_rooms", outcome.message, status="blocked")
        return {"rooms_result": data, "outcome": outcome.model_dump(mode="json")}
    _emit_node(state, "list_candidate_rooms", f"已找到 {len(rooms)} 个会议室候选", status="completed")
    return {"rooms_result": data}


def _request_facts() -> dict[str, Any] | None:
    request = operation_payload(required=True).get("meeting_request")
    return request if isinstance(request, dict) else None


def _check_availability(state: MeetingBookingWorkflowState) -> dict[str, Any]:
    request = _request_facts()
    rooms_data = state.get("rooms_result") or {}
    rooms = rooms_data.get("rooms") or []
    if not request or not rooms:
        outcome = MeetingBookingWorkflowOutcome(
            status="FAILED",
            message="预约流程缺少已校验的请求或会议室候选。",
            operation_id=_operation_id(),
            error_code="WORKFLOW_STATE_INVALID",
        )
        return {"outcome": outcome.model_dump(mode="json")}

    _emit_node(state, "check_availability", "正在批量检查会议室和参会人日程", status="started")
    response = _invoke_service(check_meeting_availability_batch, {
        "meeting_rooms": rooms,
        "user_ids": list(request.get("attendee_user_ids") or []),
        "start_time": str(request.get("start_time") or ""),
        "end_time": str(request.get("end_time") or ""),
        "required_capacity": request.get("room_capacity"),
        "tool_call_id": f"{state.get('tool_call_id', 'workflow')}:availability",
    })
    data, error = _tool_data(response)
    if error:
        outcome = outcome_from_tool_error(error, operation_id=_operation_id())
        _emit_node(state, "check_availability", outcome.message, status="failed")
        return {"outcome": outcome.model_dump(mode="json")}
    assert data is not None
    recommended = data.get("recommended")
    if not data.get("canCreateDraft") or not isinstance(recommended, dict):
        outcome = MeetingBookingWorkflowOutcome(
            status="CONFLICT_BLOCKED",
            message="当前时间没有满足条件且无冲突的会议室，暂未生成预约草稿。",
            operation_id=_operation_id(),
            facts=data,
            error_code="NO_AVAILABLE_MEETING_ROOM",
            retryable=True,
        )
        _emit_node(state, "check_availability", outcome.message, status="blocked")
        return {"availability_result": data, "outcome": outcome.model_dump(mode="json")}
    _emit_node(state, "check_availability", "可预约性检查完成，已确定推荐会议室", status="completed")
    return {"availability_result": data}


def _create_draft(state: MeetingBookingWorkflowState) -> dict[str, Any]:
    request = _request_facts() or {}
    availability = (state.get("availability_result") or {}).get("recommended") or {}
    response = _invoke_service(create_meeting_booking_draft, {
        "subject": str(request.get("subject") or ""),
        "meeting_room_id": int(availability.get("meetingRoomId")),
        "meeting_room_name": str(availability.get("meetingRoomName") or ""),
        "start_time": str(request.get("start_time") or ""),
        "end_time": str(request.get("end_time") or ""),
        "attendee_user_ids": list(request.get("attendee_user_ids") or []),
        "remark": str(request.get("remark") or ""),
        "availability_token": str(availability.get("availabilityToken") or ""),
        "allow_conflict_override": request.get("conflict_policy") == "allow_with_warning",
        "tool_call_id": f"{state.get('tool_call_id', 'workflow')}:draft",
        "state": state.get("parent_state"),
    })
    data, error = _tool_data(response)
    if error:
        outcome = outcome_from_tool_error(error, operation_id=_operation_id())
        _emit_node(state, "create_draft", outcome.message, status="failed")
        return {"outcome": outcome.model_dump(mode="json")}
    assert data is not None
    if not data.get("requires_confirmation"):
        outcome = MeetingBookingWorkflowOutcome(
            status="FAILED",
            message=str(data.get("message") or "预约草稿未生成。"),
            operation_id=str(data.get("operationId") or _operation_id() or ""),
            facts=data,
            error_code="DRAFT_NOT_CREATED",
        )
        _emit_node(state, "create_draft", outcome.message, status="failed")
        return {"draft_result": data, "outcome": outcome.model_dump(mode="json")}
    outcome = MeetingBookingWorkflowOutcome(
        status="DRAFT_READY",
        message="预约草稿已生成，等待用户确认。",
        operation_id=str(data.get("operationId") or _operation_id() or ""),
        draft_id=str(data.get("draftId") or ""),
        approval_id=str(data.get("approvalId") or ""),
        confirmation_token=str(data.get("confirmation_token") or ""),
        facts=data,
    )
    operation_runtime = get_active_operation()
    if operation_runtime is not None:
        if data.get("approvalId"):
            operation_runtime.bind_approval(str(data["approvalId"]))
        if operation_runtime.operation.status == "RUNNING":
            operation_runtime.transition("WAITING_APPROVAL", event_type="operation.waiting_approval")
    _emit_node(state, "create_draft", outcome.message, status="completed")
    return {"draft_result": data, "outcome": outcome.model_dump(mode="json")}


def _route_after_prepare(state: MeetingBookingWorkflowState) -> str:
    return "end" if state.get("outcome") else "list_rooms"


def _route_after_source(state: MeetingBookingWorkflowState) -> str:
    if state.get("outcome"):
        return "end"
    return "cancel" if str(state.get("operation") or "CREATE").upper() == "CANCEL" else "prepare"


def _route_after_rooms(state: MeetingBookingWorkflowState) -> str:
    return "end" if state.get("outcome") else "check_availability"


def _route_after_availability(state: MeetingBookingWorkflowState) -> str:
    return "end" if state.get("outcome") else "create_draft"


def build_meeting_booking_graph(*, checkpointer: Any = None):
    graph = StateGraph(MeetingBookingWorkflowState)
    # Keep the context binding outside the individual business nodes so every
    # read of Operation payload (including helper functions) observes the same
    # request envelope, not only the final service call.
    graph.add_node("resolve_source", lambda state: _invoke_node(_resolve_source, state))
    graph.add_node("prepare_request", lambda state: _invoke_node(_prepare, state))
    graph.add_node("list_candidate_rooms", lambda state: _invoke_node(_list_rooms, state))
    graph.add_node("check_availability", lambda state: _invoke_node(_check_availability, state))
    graph.add_node("create_draft", lambda state: _invoke_node(_create_draft, state))
    graph.add_node("create_cancellation_draft", lambda state: _invoke_node(_create_cancellation_draft, state))
    graph.add_edge(START, "resolve_source")
    graph.add_conditional_edges(
        "resolve_source",
        _route_after_source,
        {"prepare": "prepare_request", "cancel": "create_cancellation_draft", "end": END},
    )
    graph.add_conditional_edges(
        "prepare_request",
        _route_after_prepare,
        {"list_rooms": "list_candidate_rooms", "end": END},
    )
    graph.add_conditional_edges(
        "list_candidate_rooms",
        _route_after_rooms,
        {"check_availability": "check_availability", "end": END},
    )
    graph.add_conditional_edges(
        "check_availability",
        _route_after_availability,
        {"create_draft": "create_draft", "end": END},
    )
    graph.add_edge("create_draft", END)
    graph.add_edge("create_cancellation_draft", END)
    return graph.compile(checkpointer=checkpointer)


_MEETING_BOOKING_GRAPH = build_meeting_booking_graph()


def run_meeting_booking_workflow(
    *,
    operation: str = "CREATE",
    source_booking_id: int | None = None,
    cancel_reason: str = "",
    subject: str = "",
    start_time: str = "",
    end_time: str = "",
    attendee_names: list[str] | None = None,
    room_capacity: int | None = None,
    equipment: list[str] | None = None,
    room_preference: str = "",
    remark: str = "",
    parent_state: dict[str, Any] | None = None,
    tool_call_id: str = "",
) -> MeetingBookingWorkflowOutcome:
    """Run the deterministic meeting workflow for the current user message."""
    operation = str(operation or "CREATE").upper()
    if operation in {"BOOK", "CREATE_DRAFT"}:
        operation = "CREATE"
    # Capture the parent Agent envelope before invoking the child graph.  A
    # nested graph can otherwise lose messageId (and the tenant/user scope),
    # causing REQUEST_READY to be rejected by meeting_request_gate on the
    # immediately following availability node.
    runtime_context = current_agent_context()
    current_user_message = parent_state.get("current_user_message") if isinstance(parent_state, dict) else None
    if not runtime_context.get("messageId") and isinstance(current_user_message, dict):
        message_id = str(current_user_message.get("messageId") or "").strip()
        if message_id:
            runtime_context["messageId"] = message_id
            set_message_context(message_id)
    operation_runtime = OperationRuntime.start(
        action_id=action_id_for("meeting", operation),
        capability_id="meeting",
        # Meeting writes are fully migrated to Operation/Effect.  A missing
        # runtime is a deployment error, never permission to call the legacy
        # Java commit endpoint.
        required=True,
        payload={
            "operation": operation,
            "sourceBookingId": source_booking_id,
            "cancelReason": cancel_reason,
            "subject": subject,
            "startTime": start_time,
            "endTime": end_time,
            "attendeeNames": attendee_names or [],
            "roomCapacity": room_capacity,
            "equipment": equipment or [],
            "roomPreference": room_preference,
            "remark": remark,
        },
    )
    if operation_runtime is not None:
        runtime_context = current_agent_context()
    runtime = WorkflowRuntime("meeting_booking", writer=_stream_writer(), emit_fn=emit)
    runtime.started("会议预约工作流开始执行")
    runtime_token = set_workflow_runtime(runtime)
    operation_token = set_active_operation(operation_runtime)
    result: dict[str, Any] | None = None
    try:
        result = _MEETING_BOOKING_GRAPH.invoke(
            {
                "operation": operation,
                "source_booking_id": source_booking_id,
                "cancel_reason": cancel_reason,
                "subject": subject,
                "start_time": start_time,
                "end_time": end_time,
                "attendee_names": attendee_names,
                "room_capacity": room_capacity,
                "equipment": equipment,
                "room_preference": room_preference,
                "remark": remark,
                "parent_state": parent_state or {},
                "runtime_context": runtime_context,
                "tool_call_id": tool_call_id,
            },
        )
    except Exception as exc:
        if operation_runtime is not None:
            try:
                operation_runtime.record_outcome({
                    "status": "FAILED",
                    "message": str(exc),
                    "errorCode": type(exc).__name__,
                })
            except Exception:
                raise
        runtime.failed(str(exc), errorType=type(exc).__name__)
        raise
    finally:
        reset_active_operation(operation_token)
        reset_workflow_runtime(runtime_token)
    outcome = result.get("outcome") if isinstance(result, dict) else None
    if not isinstance(outcome, dict):
        outcome = MeetingBookingWorkflowOutcome(
            status="FAILED",
            message="会议预约工作流未返回结果。",
            operation_id=_operation_id(),
            error_code="WORKFLOW_NO_OUTCOME",
        )
        runtime.failed(outcome.message)
        if operation_runtime is not None:
            try:
                operation_runtime.record_outcome(outcome.model_dump(mode="json"))
            finally:
                operation_runtime.close()
        return outcome
    validated = MeetingBookingWorkflowOutcome.model_validate(outcome)
    if operation_runtime is not None:
        try:
            operation_runtime.record_outcome(validated.model_dump(mode="json"))
        finally:
            operation_runtime.close()
    if validated.status == "FAILED":
        runtime.failed(validated.message)
    elif validated.status in {"NEEDS_INPUT", "AMBIGUOUS_ENTITY", "CONFLICT_BLOCKED", "DRAFT_READY"}:
        runtime.completed("会议预约工作流已返回结果", outcomeStatus=validated.status)
    return validated
