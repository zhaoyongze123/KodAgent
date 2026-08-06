"""Domain operations used by the personal-schedule StateGraph.

The graph calls these functions directly.  The public LangChain Tool in
``tools.schedule.drafts`` is only an adapter for model-facing calls.
"""

from __future__ import annotations

from typing import Any

from ...runtime.operation_payload import merge_operation_payload
from ...runtime.operation_runtime import get_active_operation
from ...tools.common import (
    ToolResponse,
    current_agent_context,
    emit,
    java_get,
    java_post,
    normalize_local_datetime,
    tool_failure,
    tool_success,
)


def get_personal_schedule_service(schedule_id: int, *, tool_call_id: str = "") -> ToolResponse:
    writer = None
    emit(writer, "tool_started", "正在读取个人日程详情……", toolName="get_personal_schedule", toolCallId=tool_call_id)
    try:
        event = java_get(f"/agent/tools/calendar/personal-schedules/{int(schedule_id)}")
    except Exception as exc:
        emit(writer, "tool_failed", "个人日程详情读取失败", toolName="get_personal_schedule", toolCallId=tool_call_id, errorCode="SCHEDULE_NOT_FOUND")
        return tool_failure("SCHEDULE_NOT_FOUND", "个人日程不存在或无权访问", details=str(exc))
    return tool_success(event, {"blockType": "card", "cardType": "calendar"})


def create_personal_schedule_draft_service(
    *, operation: str, title: str = "", start_time: str = "", end_time: str = "",
    source_schedule_id: int | None = None, location: str = "", description: str = "",
    attendee_user_ids: list[int] | None = None, other_participants: str = "",
    runtime_context: dict[str, Any] | None = None, tool_call_id: str = "",
) -> ToolResponse:
    action = operation.strip().upper()
    if action not in {"CREATE", "UPDATE", "CANCEL"}:
        return tool_failure("SCHEDULE_OPERATION_INVALID", "操作必须是 CREATE、UPDATE 或 CANCEL")
    if action in {"UPDATE", "CANCEL"} and not source_schedule_id:
        return tool_failure("SCHEDULE_TARGET_REQUIRED", "修改或取消个人日程前必须先确认唯一的日程 ID")
    context = dict(runtime_context or current_agent_context())
    operation_runtime = get_active_operation()
    if operation_runtime is None:
        return tool_failure("OPERATION_REQUIRED", "个人日程草稿缺少 Operation 绑定，请重新发起操作")
    context["operationId"] = operation_runtime.operation_id
    if any(not context.get(key) for key in ("runId", "threadId", "messageId")):
        return tool_failure("SCHEDULE_CONTEXT_INVALID", "当前日程草稿缺少 Agent 运行上下文")
    payload = {
        "operation": action,
        "sourceScheduleId": source_schedule_id,
        "title": title.strip(),
        "startTime": normalize_local_datetime(start_time) if start_time else None,
        "endTime": normalize_local_datetime(end_time) if end_time else None,
        "location": location.strip() or None,
        "description": description.strip() or None,
        "attendeeUserIds": list(dict.fromkeys(attendee_user_ids or [])),
        "otherParticipants": other_participants.strip() or None,
        "allowConflictOverride": False,
        **context,
    }
    payload["idempotencyKey"] = f"{operation_runtime.operation_id}:{context['messageId']}:personal-schedule:{action}:{source_schedule_id or 'new'}"
    emit(None, "tool_started", "📝 正在生成个人日程草稿……", toolName="create_personal_schedule_draft", toolCallId=tool_call_id)
    try:
        saved = java_post("/agent/tools/calendar/personal-schedules/drafts", payload)
    except Exception as exc:
        emit(None, "tool_failed", "个人日程草稿生成失败", toolName="create_personal_schedule_draft", toolCallId=tool_call_id, errorCode="SCHEDULE_DRAFT_SAVE_FAILED")
        return tool_failure("SCHEDULE_DRAFT_SAVE_FAILED", "个人日程草稿保存失败", details=str(exc))
    draft_id = str(saved.get("draftId") or "")
    approval_id = str(saved.get("approvalId") or "")
    draft = saved.get("draft") if isinstance(saved.get("draft"), dict) else payload
    if not draft_id or not approval_id:
        return tool_failure("SCHEDULE_DRAFT_ID_MISSING", "Java 未返回有效的日程草稿或确认 ID")
    draft = dict(draft)
    for field, value in context.items():
        if field in {"tenantId", "userId", "threadId", "messageId", "runId", "originRunId", "resumeRunId", "operationId"} and not draft.get(field) and value is not None:
            draft[field] = value
    draft.update({"draftId": draft_id, "approvalId": approval_id})
    try:
        operation_runtime.bind_approval(approval_id)
        if operation_runtime.operation.status == "COLLECTING_INFO":
            operation_runtime.transition("READY", event_type="operation.ready")
        if operation_runtime.operation.status == "READY":
            operation_runtime.transition("RUNNING", event_type="operation.running")
        if operation_runtime.operation.status == "RUNNING":
            operation_runtime.transition("WAITING_APPROVAL", event_type="operation.waiting_approval")
        persisted = merge_operation_payload({
            "personal_schedule_draft": draft,
            "confirmation_token": draft_id,
            "approvalId": approval_id,
        })
    except Exception as exc:
        return tool_failure(
            "OPERATION_STATE_SAVE_FAILED",
            "个人日程草稿状态保存失败，请稍后重试。",
            details=str(exc), retryable=True,
        )
    emit(None, "draft.created", "📝 个人日程草稿已生成，等待用户确认", toolName="create_personal_schedule_draft", toolCallId=tool_call_id, draftId=draft_id, approvalId=approval_id, operationId=operation_runtime.operation_id, draft=draft)
    return tool_success({"requires_confirmation": True, "confirmation_token": draft_id, "draftId": draft_id, "approvalId": approval_id, "operationId": operation_runtime.operation_id, "operationVersion": persisted.version if persisted else operation_runtime.operation.version, "draft": draft})
