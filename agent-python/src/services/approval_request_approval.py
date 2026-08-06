"""HITL binding for leave/trip application drafts and process withdrawal drafts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..runtime.operation_runtime import OperationRuntime
from ..tools.common import ToolResponse, current_agent_context, emit, java_get, mark_run_paused, mark_run_resumed, set_operation_context, tool_failure
from .approval_core import has_trusted_approval_projection

SUPPORTED_TYPES = {"APPROVAL_REQUEST", "APPROVAL_REQUEST_GENERIC", "APPROVAL_WITHDRAW"}


@dataclass(frozen=True)
class ApprovalRequestContext:
    approval: dict[str, Any]
    runtime: dict[str, str]


def _load(approval_id: str) -> tuple[ApprovalRequestContext | None, ToolResponse | None]:
    if not approval_id.strip():
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批确认上下文缺少 approvalId。")
    try:
        approval = java_get(f"/agent/approvals/{approval_id.strip()}")
    except Exception as exc:
        return None, tool_failure("APPROVAL_NOT_FOUND", "审批确认不存在、已过期或无权访问。", details=str(exc))
    runtime = dict(current_agent_context())
    operation_id = str(approval.get("operationId") or "").strip()
    current_operation_id = str(runtime.get("operationId") or "").strip()
    if not operation_id:
        return None, tool_failure(
            "OPERATION_REQUIRED",
            "审批申请确认缺少 Operation 绑定，旧版直接提交路径已关闭，请重新生成草稿。",
        )
    if current_operation_id and current_operation_id != operation_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批申请与当前 Operation 不匹配。")
    try:
        operation_runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception as exc:
        return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "审批申请的持久化操作不可用。", details=str(exc), retryable=True)
    if operation_runtime is None:
        return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "审批申请缺少可用的 Operation Runtime。", retryable=True)
    try:
        if operation_runtime.operation.action_id not in {"approval.request.create", "approval.request.withdraw"}:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批申请绑定的 Action 不匹配。")
        if operation_runtime.operation.approval_id and operation_runtime.operation.approval_id != approval_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批申请绑定了其他 Approval。")
    finally:
        operation_runtime.close()
    set_operation_context(operation_id)
    runtime["operationId"] = operation_id
    for field in ("runId", "threadId", "messageId"):
        if not runtime.get(field) or str(runtime[field]) != str(approval.get(field) or ""):
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", f"审批不属于当前 {field}。")
    if str(approval.get("draftType") or "") not in SUPPORTED_TYPES:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "该审批不是申请或撤回草稿。")
    return ApprovalRequestContext(approval=approval, runtime=runtime), None


def load_pending_approval_request_context() -> tuple[ApprovalRequestContext | None, ToolResponse | None]:
    operation_id = str(current_agent_context().get("operationId") or "").strip()
    if not operation_id:
        return None, tool_failure("OPERATION_REQUIRED", "审批申请确认卡缺少 Operation 绑定，请重新生成草稿。")
    runtime = OperationRuntime.open_existing(operation_id, required=True)
    if runtime is None or runtime.operation.status != "WAITING_APPROVAL":
        if runtime is not None:
            runtime.close()
        return None, tool_failure("APPROVAL_REQUEST_NOT_PENDING", "当前没有等待确认的审批申请操作。")
    approval_id = str(runtime.operation.approval_id or "").strip()
    runtime.close()
    context, error = _load(approval_id)
    if error or context is None:
        return None, error
    if str(context.approval.get("status") or "") != "PENDING":
        return None, tool_failure("APPROVAL_REQUEST_NOT_PENDING", "审批申请确认已处理或已过期。")
    return context, None


def load_approval_request_context(approval_id: str) -> tuple[ApprovalRequestContext | None, ToolResponse | None]:
    return _load(str(approval_id or ""))


def confirmation_args(context: ApprovalRequestContext, args: dict[str, Any]) -> dict[str, Any]:
    draft = context.approval.get("draft") if isinstance(context.approval.get("draft"), dict) else {}
    withdraw = str(context.approval.get("draftType") or "") == "APPROVAL_WITHDRAW"
    if withdraw:
        title, approve_label = "确认撤回审批流程", "确认撤回"
        fields = [{"label": "操作", "value": "撤回审批流程"}]
        if draft.get("processDefinitionName") or draft.get("name"):
            fields.append({"label": "流程", "value": str(draft.get("processDefinitionName") or draft.get("name"))})
        fields.append({"label": "撤回原因", "value": str(draft.get("reason") or "")})
        action = "confirm_approval_withdraw_action"
    else:
        generic = str(context.approval.get("draftType") or "") == "APPROVAL_REQUEST_GENERIC"
        label = str(draft.get("processDefinitionName") or draft.get("requestType") or "审批申请") if generic else ("请假" if str(draft.get("requestType") or "") == "leave" else "出差")
        title, approve_label = f"确认发起{label}审批", f"确认发起{label}"
        if generic:
            fields = [
                {"label": "模板", "value": label},
                {"label": "表单", "value": json.dumps(draft.get("variables") or {}, ensure_ascii=False)},
                {"label": "审批链", "value": str((draft.get("preview") or {}).get("normalizedSummary") or "待系统确定")},
            ]
        else:
            fields = [{"label": "类型", "value": label}, {"label": "时间", "value": f"{draft.get('startTime', '')} - {draft.get('endTime', '')}"}, {"label": "原因", "value": str(draft.get("reason") or "")}, {"label": "审批链", "value": str((draft.get("preview") or {}).get("normalizedSummary") or "待系统确定")}]
        action = "confirm_approval_request_action"
    return {**args, "approvalId": context.approval.get("approvalId"), "draftId": context.approval.get("draftId"), "confirmation_token": context.approval.get("approvalId"), "action": action, "cardType": "approval_request", "title": title, "approveLabel": approve_label, "rejectLabel": "取消操作", "status": context.approval.get("status"), "allowedActions": ["approve", "reject"], "expiresAt": context.approval.get("expiresAt"), "fields": fields, "draft": draft, "threadId": context.runtime.get("threadId"), "runId": context.runtime.get("runId"), "messageId": context.runtime.get("messageId")}


def confirmation_description(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:
    context, error = _load(str((tool_call.get("args") or {}).get("approval_id") or (tool_call.get("args") or {}).get("approvalId") or ""))
    return "当前审批确认上下文无效。" if error or context is None else json.dumps(confirmation_args(context, dict(tool_call.get("args") or {})), ensure_ascii=False)


def prepare_confirmation_interrupt(request: Any) -> bool:
    args = (request.tool_call or {}).get("args") or {}
    context, error = _load(str(args.get("approval_id") or args.get("approvalId") or ""))
    if error or context is None:
        return False
    action = str(args.get("action") or "")
    if not has_trusted_approval_projection(request, action=action, approval_id=context.approval.get("approvalId"), draft_id=context.approval.get("draftId"), origin_run_id=context.runtime.get("runId"), message_id=context.runtime.get("messageId")):
        return False
    status = str(context.approval.get("status") or "")
    operation_id = str(context.approval.get("operationId") or "").strip()
    if not operation_id:
        return False
    try:
        runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception:
        return False
    if runtime is None:
        return False
    try:
        operation_status = runtime.operation.status
        if status == "APPROVED":
            if not str(context.approval.get("resumeIdempotencyKey") or "").strip():
                return False
            if operation_status not in {"WAITING_APPROVAL", "COMMITTING", "UNKNOWN"}:
                return operation_status == "SUCCEEDED"
            mark_run_resumed()
            return False
        if status in {"REJECTED", "EXPIRED"}:
            if operation_status == "WAITING_APPROVAL":
                runtime.transition(
                    "CANCELLED" if status == "REJECTED" else "EXPIRED",
                    event_type=("operation.approval_rejected" if status == "REJECTED" else "operation.approval_expired"),
                    data={"approvalId": context.approval.get("approvalId"), "approvalStatus": status},
                )
            mark_run_resumed()
            return False
        if status != "PENDING" or operation_status != "WAITING_APPROVAL":
            return False
        emit(getattr(request.runtime, "stream_writer", None), "run.paused", "等待用户确认审批申请操作",
             require_persist=True, eventId=f"{context.approval.get('approvalId')}:paused",
             approvalId=context.approval.get("approvalId"), draftId=context.approval.get("draftId"),
             reason="approval_required")
        mark_run_paused()
        return True
    finally:
        runtime.close()


def can_execute(context: ApprovalRequestContext) -> bool:
    operation_id = str(context.approval.get("operationId") or "").strip()
    if not operation_id:
        return False
    try:
        runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception:
        return False
    if runtime is None:
        return False
    try:
        return (
            str(context.approval.get("status") or "") == "APPROVED"
            and bool(str(context.approval.get("resumeIdempotencyKey") or "").strip())
            and runtime.operation.status in {"WAITING_APPROVAL", "COMMITTING", "UNKNOWN"}
        )
    finally:
        runtime.close()


def complete(context: ApprovalRequestContext) -> None:
    return None


def cancel(context: ApprovalRequestContext) -> None:
    return None
