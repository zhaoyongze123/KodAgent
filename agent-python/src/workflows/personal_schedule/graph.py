from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from ...runtime.operation_runtime import (
    OperationRuntime,
    action_id_for,
    get_active_operation,
    reset_active_operation,
    set_active_operation,
)
from ...tools.common import AGENT_TIMEZONE, ToolResponse, bind_agent_context, emit, set_message_context, tool_failure
from ...tools.common.http_client import normalize_local_datetime
from ...tools.common.events import current_agent_context
from .service import create_personal_schedule_draft_service, get_personal_schedule_service

# Compatibility names for existing workflow test doubles; production values
# are plain domain-service callables, never LangChain Tool objects.
get_personal_schedule = get_personal_schedule_service
create_personal_schedule_draft = create_personal_schedule_draft_service
from ..runtime import WorkflowRuntime
from ..runtime_context import (
    get_workflow_runtime,
    reset_workflow_runtime,
    set_workflow_runtime,
)
from .contracts import PersonalScheduleWorkflowOutcome
from .state import PersonalScheduleWorkflowState


def _stream_writer() -> Any:
    try:
        return get_stream_writer()
    except RuntimeError:
        return None


def _schedule_runtime_required() -> bool:
    """All schedule writes use the durable Operation boundary."""
    return True


def _tool_data(response: Any) -> tuple[dict[str, Any] | None, Any | None]:
    if isinstance(response, str):
        try:
            response = ToolResponse.model_validate(json.loads(response))
        except (TypeError, ValueError, json.JSONDecodeError):
            return None, tool_failure("WORKFLOW_TOOL_FAILED", "日程工具返回了无效结果").error
    if isinstance(response, ToolResponse):
        return (response.data if response.ok and isinstance(response.data, dict) else None), response.error
    if isinstance(response, dict):
        return (response.get("data", response) if response.get("ok", True) else None), response.get("error")
    return None, tool_failure("WORKFLOW_TOOL_FAILED", "日程工具返回了无效结果").error


def _invoke_service(service: Any, payload: dict[str, Any]) -> Any:
    """Call a domain service directly; retain the tiny ``.func`` test seam."""
    candidate = getattr(service, "func", None)
    return candidate(**payload) if callable(candidate) else service(**payload)


def _normalize_schedule_datetime(value: Any) -> str:
    """Normalize Java calendar values before sending them to draft APIs.

    Calendar reads may serialize timestamps as epoch milliseconds while the
    draft facade accepts ``yyyy-MM-dd HH:mm:ss``. This conversion belongs at
    the workflow boundary so CREATE, UPDATE and CANCEL share one contract.
    """
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value) / 1000, tz=AGENT_TIMEZONE).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    text = str(value).strip()
    if text.isdigit():
        return datetime.fromtimestamp(int(text) / 1000, tz=AGENT_TIMEZONE).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    return normalize_local_datetime(text)


def _emit(state: PersonalScheduleWorkflowState, node: str, text: str, status: str) -> None:
    runtime = get_workflow_runtime()
    if runtime is None:
        runtime = WorkflowRuntime("personal_schedule", writer=_stream_writer(), emit_fn=emit)
    if status == "started":
        runtime.node_started(node, text)
    elif status == "completed":
        runtime.node_completed(node, text)
    elif status == "blocked":
        runtime.blocked(node, text)
    else:
        runtime.failed(text, node=node)


def _validate(state: PersonalScheduleWorkflowState) -> dict[str, Any]:
    operation = str(state.get("operation") or "").upper()
    _emit(state, "validate_request", "正在校验个人日程操作和字段", "started")
    if operation not in {"CREATE", "UPDATE", "CANCEL"}:
        outcome = PersonalScheduleWorkflowOutcome(status="NEEDS_INPUT", message="请说明要创建、修改还是取消日程。", error_code="SCHEDULE_OPERATION_INVALID")
        _emit(state, "validate_request", outcome.message, "blocked")
        return {"outcome": outcome.model_dump(mode="json")}
    if operation in {"UPDATE", "CANCEL"} and not state.get("source_schedule_id"):
        outcome = PersonalScheduleWorkflowOutcome(status="NEEDS_INPUT", message="修改或取消日程前请提供唯一的日程 ID。", error_code="SCHEDULE_TARGET_REQUIRED")
        _emit(state, "validate_request", outcome.message, "blocked")
        return {"outcome": outcome.model_dump(mode="json")}
    if operation == "CREATE" and (not str(state.get("title") or "").strip() or not str(state.get("start_time") or "").strip() or not str(state.get("end_time") or "").strip()):
        outcome = PersonalScheduleWorkflowOutcome(status="NEEDS_INPUT", message="请补充日程标题、开始时间和结束时间。", error_code="SCHEDULE_FIELDS_INCOMPLETE")
        _emit(state, "validate_request", outcome.message, "blocked")
        return {"outcome": outcome.model_dump(mode="json")}
    operation_runtime = get_active_operation()
    if operation_runtime is not None and operation_runtime.operation.status == "COLLECTING_INFO":
        operation_runtime.transition("READY", event_type="operation.ready")
    _emit(state, "validate_request", "日程字段校验完成", "completed")
    return {}


def _load_source(state: PersonalScheduleWorkflowState) -> dict[str, Any]:
    if str(state.get("operation") or "").upper() == "CREATE":
        return {}
    _emit(state, "load_source", "正在读取待修改的个人日程", "started")
    with bind_agent_context(state.get("runtime_context") or {}):
        response = _invoke_service(get_personal_schedule, {
            "schedule_id": int(state["source_schedule_id"]),
            "tool_call_id": f"{state.get('tool_call_id', 'workflow')}:source",
        })
    data, error = _tool_data(response)
    if error or data is None:
        code = str(getattr(error, "code", None) or "SCHEDULE_SOURCE_READ_FAILED")
        message = str(getattr(error, "message", None) or "原日程读取失败，无法继续修改。")
        outcome = PersonalScheduleWorkflowOutcome(
            status="FAILED", message=message, error_code=code,
            retryable=code in {"FACADE_UNAVAILABLE", "TOOL_EXECUTION_FAILED"},
        )
        _emit(state, "load_source", outcome.message, "failed")
        return {"outcome": outcome.model_dump(mode="json")}
    _emit(state, "load_source", "已读取原日程", "completed")
    return {"source_result": data}


def _create_draft(state: PersonalScheduleWorkflowState) -> dict[str, Any]:
    _emit(state, "create_draft", "正在生成个人日程草稿", "started")
    operation = str(state.get("operation") or "").upper()
    source = state.get("source_result") or {}
    # An UPDATE can change a single field such as time. Keep the Java-read
    # owner facts for every omitted field; otherwise an incomplete model call
    # would either erase attendees or fail backend validation after source
    # selection had already succeeded.
    def value(field: str, source_field: str | None = None) -> Any:
        current = state.get(field)
        return current if current not in (None, "", []) else source.get(source_field or field)

    with bind_agent_context(state.get("runtime_context") or {}):
        response = _invoke_service(create_personal_schedule_draft, {
            "operation": operation,
            "title": str(value("title") or ""),
            "start_time": _normalize_schedule_datetime(value("start_time", "startTime")),
            "end_time": _normalize_schedule_datetime(value("end_time", "endTime")),
            "source_schedule_id": state.get("source_schedule_id"),
            "location": str(value("location") or ""),
            "description": str(value("description") or ""),
            "attendee_user_ids": list(value("attendee_user_ids", "attendeeUserIds") or []),
            "other_participants": str(value("other_participants", "otherParticipants") or ""),
            "runtime_context": state.get("runtime_context") or {},
            "tool_call_id": f"{state.get('tool_call_id', 'workflow')}:draft",
        })
    data, error = _tool_data(response)
    if error or data is None or not data.get("requires_confirmation"):
        code = str(getattr(error, "code", None) or "SCHEDULE_DRAFT_FAILED")
        message = str(getattr(error, "message", None) or "个人日程草稿生成失败。")
        outcome = PersonalScheduleWorkflowOutcome(
            status="FAILED", message=message, error_code=code,
            retryable=code in {"FACADE_UNAVAILABLE", "SCHEDULE_DRAFT_SAVE_FAILED", "TOOL_EXECUTION_FAILED"},
        )
        _emit(state, "create_draft", outcome.message, "failed")
        return {"outcome": outcome.model_dump(mode="json")}
    outcome = PersonalScheduleWorkflowOutcome(
        status="DRAFT_READY", message="个人日程草稿已生成，等待用户确认。",
        draft_id=str(data.get("draftId") or ""), approval_id=str(data.get("approvalId") or ""),
        confirmation_token=str(data.get("confirmation_token") or ""), facts=data,
    )
    operation_runtime = get_active_operation()
    if operation_runtime is not None:
        if data.get("approvalId"):
            operation_runtime.bind_approval(str(data["approvalId"]))
        if operation_runtime.operation.status == "READY":
            operation_runtime.transition("RUNNING", event_type="operation.running")
        if operation_runtime.operation.status == "RUNNING":
            operation_runtime.transition("WAITING_APPROVAL", event_type="operation.waiting_approval")
    _emit(state, "create_draft", outcome.message, "completed")
    return {"draft_result": data, "outcome": outcome.model_dump(mode="json")}


def _next(state: PersonalScheduleWorkflowState) -> str:
    return "end" if state.get("outcome") else "source"


def build_personal_schedule_graph(*, checkpointer: Any = None):
    graph = StateGraph(PersonalScheduleWorkflowState)
    graph.add_node("validate_request", _validate)
    graph.add_node("load_source", _load_source)
    graph.add_node("create_draft", _create_draft)
    graph.add_edge(START, "validate_request")
    graph.add_conditional_edges("validate_request", _next, {"source": "load_source", "end": END})
    graph.add_conditional_edges("load_source", lambda state: "end" if state.get("outcome") else "draft", {"draft": "create_draft", "end": END})
    graph.add_edge("create_draft", END)
    return graph.compile(checkpointer=checkpointer)


_GRAPH = build_personal_schedule_graph()


def run_personal_schedule_workflow(**kwargs: Any) -> PersonalScheduleWorkflowOutcome:
    # Capture the parent Agent envelope before invoking the child graph.  A
    # nested graph may run with a partial RunnableConfig, so downstream Java
    # tools must use this explicit trusted snapshot for identity/idempotency.
    runtime_context = current_agent_context()
    parent_state = kwargs.get("parent_state")
    current_user_message = parent_state.get("current_user_message") if isinstance(parent_state, dict) else None
    if not runtime_context.get("messageId") and isinstance(current_user_message, dict):
        message_id = str(current_user_message.get("messageId") or "").strip()
        if message_id:
            runtime_context["messageId"] = message_id
            set_message_context(message_id)
    input_state = dict(kwargs)
    input_state["runtime_context"] = runtime_context
    operation = str(kwargs.get("operation") or "").upper()
    operation_runtime = None
    if operation in {"CREATE", "UPDATE", "CANCEL"}:
        operation_runtime = OperationRuntime.start(
            action_id=action_id_for("schedule", operation),
            capability_id="schedule",
            # Keep Operation identity aligned with the Java draft idempotency
            # boundary. A retry of the same target reopens the same Operation;
            # a different existing target cannot collide with it.
            operation_key=f"{operation}:{kwargs.get('source_schedule_id') or 'new'}",
            required=_schedule_runtime_required(),
            payload={
                "operation": operation,
                "sourceScheduleId": kwargs.get("source_schedule_id"),
                "title": kwargs.get("title") or "",
                "startTime": kwargs.get("start_time") or "",
                "endTime": kwargs.get("end_time") or "",
                "location": kwargs.get("location") or "",
                "description": kwargs.get("description") or "",
                "attendeeUserIds": list(kwargs.get("attendee_user_ids") or []),
                "otherParticipants": kwargs.get("other_participants") or "",
            },
        )
    if operation_runtime is not None:
        runtime_context = {**runtime_context, "operationId": operation_runtime.operation_id}
        input_state["runtime_context"] = runtime_context
    runtime = WorkflowRuntime("personal_schedule", writer=_stream_writer(), emit_fn=emit)
    runtime.started("个人日程工作流开始执行")
    runtime_token = set_workflow_runtime(runtime)
    operation_token = set_active_operation(operation_runtime)
    try:
        result = _GRAPH.invoke(input_state)
    except Exception as exc:
        if operation_runtime is not None:
            try:
                operation_runtime.record_outcome({
                    "status": "FAILED",
                    "message": str(exc),
                    "errorCode": type(exc).__name__,
                })
            except Exception:
                pass
            finally:
                operation_runtime.close()
        runtime.failed(str(exc), errorType=type(exc).__name__)
        raise
    finally:
        reset_active_operation(operation_token)
        reset_workflow_runtime(runtime_token)
    raw = result.get("outcome") if isinstance(result, dict) else None
    outcome = PersonalScheduleWorkflowOutcome.model_validate(raw or {"status": "FAILED", "message": "日程工作流未返回结果。", "error_code": "WORKFLOW_NO_OUTCOME"})
    if outcome.status == "FAILED":
        runtime.failed(outcome.message)
    else:
        runtime.completed("个人日程工作流已返回结果", outcomeStatus=outcome.status)
    if operation_runtime is not None:
        try:
            operation_runtime.record_outcome(outcome.model_dump(mode="json"))
        finally:
            operation_runtime.close()
    return outcome
