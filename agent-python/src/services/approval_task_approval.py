"""Durable HITL binding for one BPM todo action."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..runtime.operation_runtime import OperationRuntime
from ..tools.common import (
    ToolResponse,
    current_agent_context,
    emit,
    java_get,
    mark_run_paused,
    mark_run_resumed,
    set_operation_context,
    tool_failure,
)
from .approval_core import has_trusted_approval_projection

@dataclass(frozen=True)
class ApprovalTaskContext:
    approval: dict[str, Any]
    runtime: dict[str, str]


def _load(approval_id: str) -> tuple[ApprovalTaskContext | None, ToolResponse | None]:
    if not approval_id.strip():
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批确认上下文缺少 approvalId。")
    try:
        approval = java_get(f"/agent/approvals/{approval_id.strip()}")
    except Exception as exc:
        return None, tool_failure("APPROVAL_NOT_FOUND", "审批确认不存在、已过期或无权访问。", details=str(exc))
    runtime = dict(current_agent_context())
    approval_origin_run_id = str(approval.get("runId") or "")
    current_origin_run_id = str(runtime.get("originRunId") or runtime.get("runId") or "")
    if not current_origin_run_id or current_origin_run_id != approval_origin_run_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批不属于当前原始 runId。")
    for field in ("threadId", "messageId"):
        if not runtime.get(field) or str(runtime[field]) != str(approval.get(field) or ""):
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", f"审批不属于当前 {field}。")
    if str(approval.get("draftType") or "") != "APPROVAL_TASK":
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "该审批不是单条待办审批操作。")
    operation_id = str(approval.get("operationId") or "").strip()
    if not operation_id:
        return None, tool_failure(
            "OPERATION_REQUIRED",
            "审批确认缺少 Operation 绑定，旧版任务链不能继续执行，请重新生成预览。",
        )
    current_operation_id = str(runtime.get("operationId") or "").strip()
    if current_operation_id and current_operation_id != operation_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批与当前 Operation 不匹配。")
    try:
        operation_runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception as exc:
        return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "当前单条审批的持久化操作不可用，请稍后重试。", details=str(exc), retryable=True)
    if operation_runtime is None:
        return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "当前单条审批缺少可用的 Operation Runtime。", retryable=True)
    try:
        if operation_runtime.operation.action_id != "approval.write.task":
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批绑定的 Action 不匹配。")
        if operation_runtime.operation.approval_id and operation_runtime.operation.approval_id != operation_id and operation_runtime.operation.approval_id != approval.get("approvalId"):
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批与 Operation 绑定不一致。")
    finally:
        operation_runtime.close()
    set_operation_context(operation_id)
    runtime["operationId"] = operation_id
    runtime["originRunId"] = approval_origin_run_id
    return ApprovalTaskContext(approval=approval, runtime=runtime), None


def _operation_snapshot(operation_id: str):
    """Read the durable Operation used by the HITL boundary."""
    runtime = OperationRuntime.open_existing(operation_id, required=True)
    if runtime is None:
        return None
    try:
        return runtime.operation
    finally:
        runtime.close()


def load_pending_approval_task_context() -> tuple[ApprovalTaskContext | None, ToolResponse | None]:
    operation_id = str(current_agent_context().get("operationId") or "").strip()
    operation = None
    if operation_id:
        try:
            operation = _operation_snapshot(operation_id)
        except Exception as exc:
            return None, tool_failure(
                "APPROVAL_RUNTIME_UNAVAILABLE",
                "当前单条审批的持久化操作不可用，请稍后重试。",
                details=str(exc),
                retryable=True,
            )
        if operation is None or operation.status != "WAITING_APPROVAL":
            return None, tool_failure("APPROVAL_TASK_NOT_PENDING", "当前没有等待确认的单条审批操作。")

    if not operation_id:
        return None, tool_failure(
            "OPERATION_REQUIRED",
            "单条审批确认卡缺少 Operation 绑定，旧版任务链不能继续执行，请重新生成预览。",
        )
    approval_id = str(operation.approval_id or "").strip()
    if not approval_id:
        return None, tool_failure("APPROVAL_TASK_NOT_PENDING", "当前没有等待确认的单条审批操作。")
    context, error = _load(approval_id)
    if error or context is None:
        return None, error
    if operation_id and str(context.approval.get("operationId") or "").strip() != operation_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批与当前 Operation 不匹配。")
    if str(context.approval.get("status") or "") != "PENDING":
        return None, tool_failure("APPROVAL_TASK_NOT_PENDING", "单条审批确认已处理或已过期。")
    return context, None


def load_approval_task_context(approval_id: str) -> tuple[ApprovalTaskContext | None, ToolResponse | None]:
    """Load the exact task binding during the official HITL resume."""
    context, error = _load(str(approval_id or ""))
    if error or context is None:
        return None, error
    operation_id = str(context.approval.get("operationId") or "").strip()
    if not operation_id:
        return None, tool_failure("OPERATION_REQUIRED", "审批确认缺少 Operation 绑定，请重新生成预览。")
    return context, None


def confirmation_args(context: ApprovalTaskContext, args: dict[str, Any]) -> dict[str, Any]:
    draft = context.approval.get("draft") if isinstance(context.approval.get("draft"), dict) else {}
    action = str(draft.get("action") or "")
    label = "通过" if action == "APPROVE" else "驳回"
    fields = [{"label": "操作", "value": f"审批{label}"}, {"label": "流程", "value": str(draft.get("processDefinitionName") or draft.get("name") or "") }]
    if draft.get("startUserName"):
        fields.append({"label": "发起人", "value": str(draft.get("startUserName"))})
    if draft.get("reason"):
        fields.append({"label": "审批意见", "value": str(draft["reason"])})
    return {
        **args,
        "approvalId": context.approval.get("approvalId"),
        "draftId": context.approval.get("draftId"),
        "operationId": context.approval.get("operationId") or context.runtime.get("operationId"),
        "confirmation_token": context.approval.get("approvalId"),
        "action": "confirm_approval_task_action",
        "cardType": "approval_task",
        "title": f"确认审批{label}",
        "approveLabel": f"确认{label}",
        "rejectLabel": "取消操作",
        "status": context.approval.get("status"),
        "allowedActions": ["approve", "reject"],
        "expiresAt": context.approval.get("expiresAt"),
        "fields": fields,
        "draft": draft,
        "threadId": context.runtime.get("threadId"),
        "runId": context.runtime.get("runId"),
        "originRunId": context.runtime.get("originRunId"),
        "resumeRunId": context.runtime.get("resumeRunId"),
        "messageId": context.runtime.get("messageId"),
    }


def confirmation_description(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:
    context, error = _load(str((tool_call.get("args") or {}).get("approval_id") or (tool_call.get("args") or {}).get("approvalId") or ""))
    return "当前审批确认上下文无效。" if error or context is None else json.dumps(confirmation_args(context, dict(tool_call.get("args") or {})), ensure_ascii=False)


def prepare_confirmation_interrupt(request: Any) -> bool:
    args = (request.tool_call or {}).get("args") or {}
    context, error = _load(str(args.get("approval_id") or args.get("approvalId") or ""))
    if error or context is None:
        return False
    if not has_trusted_approval_projection(
        request,
        action="confirm_approval_task_action",
        approval_id=context.approval.get("approvalId"),
        draft_id=context.approval.get("draftId"),
        origin_run_id=context.runtime.get("originRunId") or context.approval.get("runId"),
        message_id=context.runtime.get("messageId"),
    ):
        return False
    status = str(context.approval.get("status") or "")
    operation_id = str(context.approval.get("operationId") or "").strip()
    durable_operation = bool(operation_id)
    if not durable_operation:
        return False
    if status == "APPROVED":
        if not str(context.approval.get("resumeIdempotencyKey") or "").strip():
            return False
        mark_run_resumed(); return False
    if status in {"REJECTED", "EXPIRED"}:
        mark_run_resumed(); return False
    if status != "PENDING":
        return False
    emit(getattr(request.runtime, "stream_writer", None), "run.paused", "等待用户确认单条审批", require_persist=True, eventId=f"{context.approval.get('approvalId')}:paused", approvalId=context.approval.get("approvalId"), draftId=context.approval.get("draftId"), reason="approval_required")
    mark_run_paused(); return True


def can_execute(context: ApprovalTaskContext) -> bool:
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


def settle_terminal_approval(context: ApprovalTaskContext) -> ToolResponse | None:
    """Project a Java-owned rejection/expiry into the Agent Operation."""
    status = str(context.approval.get("status") or "").upper()
    operation_id = str(context.approval.get("operationId") or "").strip()
    if status not in {"REJECTED", "EXPIRED"} or not operation_id:
        return None
    try:
        OperationRuntime.settle_approval(
            operation_id,
            status,
            approval_id=str(context.approval.get("approvalId") or "") or None,
            required=True,
        )
    except Exception as exc:
        return tool_failure(
            "OPERATION_STATE_SYNC_FAILED",
            "审批已结束，但 Agent Operation 尚未同步，暂不继续恢复。",
            details=str(exc),
            retryable=True,
        )
    return None


def complete(context: ApprovalTaskContext) -> None:
    # EffectCommitCoordinator settles the Operation. There is no separate
    # task marker to consume after the business result is durable.
    return None


def cancel(context: ApprovalTaskContext) -> None:
    return None
