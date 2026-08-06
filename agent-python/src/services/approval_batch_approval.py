"""Durable HITL binding for a batch approval preview.

The Java batch-preview row is the write authority. Redis/task memory carries
only the exact graph pause binding, so a model cannot convert a historical
preview or a free-form "confirm" message into a BPM mutation.
"""

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
class ApprovalBatchContext:
    preview: dict[str, Any]
    runtime: dict[str, str]
    origin_run_id: str


def _origin_runtime() -> dict[str, str]:
    runtime = dict(current_agent_context())
    runtime["originRunId"] = str(runtime.get("originRunId") or runtime.get("runId") or "")
    return runtime


def _load(preview_id: str, confirmation_token: str) -> tuple[ApprovalBatchContext | None, ToolResponse | None]:
    if not preview_id or not confirmation_token:
        return None, tool_failure("APPROVAL_BATCH_CONTEXT_INVALID", "批量审批确认信息不完整，请重新生成预览。")
    try:
        record = java_get(f"/agent/tools/approvals/batch/{preview_id}")
    except Exception as exc:
        return None, tool_failure("APPROVAL_BATCH_NOT_FOUND", "批量审批预览不存在、已过期或无权访问。", details=str(exc))
    if not isinstance(record, dict) or str(record.get("previewId") or "") != preview_id:
        return None, tool_failure("APPROVAL_BATCH_CONTEXT_INVALID", "批量审批预览返回格式无效。")
    if str(record.get("confirmationToken") or "") != confirmation_token:
        return None, tool_failure("APPROVAL_BATCH_CONTEXT_INVALID", "批量审批确认令牌不匹配。")
    runtime = _origin_runtime()
    origin_run_id = str(record.get("runId") or "")
    for field, expected in (("threadId", record.get("threadId")), ("messageId", record.get("messageId"))):
        actual = runtime.get(field)
        if not actual or not expected or str(actual) != str(expected):
            return None, tool_failure("APPROVAL_BATCH_CONTEXT_INVALID", f"批量审批不属于当前 {field}。")
    if not origin_run_id or str(runtime.get("originRunId") or "") != origin_run_id:
        return None, tool_failure("APPROVAL_BATCH_CONTEXT_INVALID", "批量审批不属于当前原始运行。")
    operation_id = str(record.get("operationId") or "").strip()
    if not operation_id:
        return None, tool_failure("OPERATION_REQUIRED", "批量审批确认缺少 Operation 绑定，请重新生成预览。")
    current_operation_id = str(runtime.get("operationId") or "").strip()
    if current_operation_id and current_operation_id != operation_id:
        return None, tool_failure("APPROVAL_BATCH_CONTEXT_INVALID", "批量审批与当前 Operation 不匹配。")
    try:
        operation_runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception as exc:
        return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "当前批量审批的持久化操作不可用，请稍后重试。", details=str(exc), retryable=True)
    if operation_runtime is None:
        return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "当前批量审批缺少可用的 Operation Runtime。", retryable=True)
    try:
        operation = operation_runtime.operation
        if operation.action_id != "approval.write.batch":
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "批量审批绑定的 Action 不匹配。")
        if operation.approval_id and operation.approval_id != preview_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "批量审批绑定了其他 Approval。")
        for field, value in {
            "tenantId": operation.tenant_id,
            "userId": operation.user_id,
            "threadId": operation.thread_id,
            "messageId": operation.message_id,
        }.items():
            if runtime.get(field) and str(runtime[field]) != str(value):
                return None, tool_failure("APPROVAL_CONTEXT_INVALID", f"批量审批不属于当前 {field}。")
    finally:
        operation_runtime.close()
    runtime["operationId"] = operation_id
    set_operation_context(operation_id)
    return ApprovalBatchContext(preview=record, runtime=runtime, origin_run_id=origin_run_id), None


def load_pending_approval_batch_context() -> tuple[ApprovalBatchContext | None, ToolResponse | None]:
    operation_id = str(current_agent_context().get("operationId") or "").strip()
    if not operation_id:
        try:
            candidates = OperationRuntime.find_by_binding(
                action_id="approval.write.batch",
                statuses={"WAITING_APPROVAL"},
                required=True,
            )
        except Exception as exc:
            return None, tool_failure(
                "APPROVAL_RUNTIME_UNAVAILABLE",
                "当前批量审批的持久化操作不可用，请稍后重试。",
                details=str(exc), retryable=True,
            )
        if len(candidates) > 1:
            return None, tool_failure(
                "APPROVAL_CONTEXT_AMBIGUOUS",
                "当前存在多个待确认的批量审批，请从对应确认卡片继续。",
            )
        if candidates:
            operation_id = candidates[0].operation_id
    if operation_id:
        try:
            operation_runtime = OperationRuntime.open_existing(operation_id, required=True)
        except Exception as exc:
            return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "当前批量审批的持久化操作不可用，请稍后重试。", details=str(exc), retryable=True)
        if operation_runtime is None:
            return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "当前批量审批缺少可用的 Operation Runtime。", retryable=True)
        try:
            operation = operation_runtime.operation
            if operation.action_id != "approval.write.batch" or operation.status != "WAITING_APPROVAL":
                return None, tool_failure("APPROVAL_BATCH_NOT_PENDING", "当前没有等待确认的批量审批。")
            operation_preview_id = str(operation.approval_id or "").strip()
            if not operation_preview_id:
                return None, tool_failure("APPROVAL_CONTEXT_INVALID", "批量审批 Operation 缺少 Approval 绑定。")
        finally:
            operation_runtime.close()
        preview_id = operation_preview_id
        try:
            durable = java_get(f"/agent/tools/approvals/batch/{preview_id}")
            token = str(durable.get("confirmationToken") or "")
        except Exception as exc:
            return None, tool_failure("APPROVAL_BATCH_NOT_FOUND", "批量审批预览不存在、已过期或无权访问。", details=str(exc))
        context, error = _load(preview_id, token)
    else:
        return None, tool_failure(
            "OPERATION_REQUIRED",
            "批量审批确认卡缺少 Operation 绑定，旧版任务链不能继续执行，请重新生成预览。",
        )
    if error or context is None:
        return None, error
    if str(context.preview.get("status") or "") != "PENDING":
        return None, tool_failure("APPROVAL_BATCH_NOT_PENDING", "批量审批确认已处理或已过期。")
    return context, None


def confirmation_args(context: ApprovalBatchContext, args: dict[str, Any]) -> dict[str, Any]:
    preview = context.preview
    data = preview.get("preview") if isinstance(preview.get("preview"), dict) else {}
    action = str(data.get("action") or "")
    label = "批量驳回" if action == "REJECT" else "批量通过"
    tasks = data.get("tasks") if isinstance(data.get("tasks"), list) else []
    fields = [
        {"label": "操作", "value": label},
        {"label": "涉及审批", "value": f"{len(tasks)} 条"},
    ]
    if data.get("reason"):
        fields.append({"label": "统一意见", "value": str(data["reason"])})
    return {
        **args,
        "preview_id": preview["previewId"], "confirmation_token": preview["confirmationToken"],
        # The existing ApprovalCard treats this durable operation id like an
        # approval id; cardType selects the batch decision endpoint.
        "approvalId": preview["previewId"], "draftId": preview["previewId"],
        "operationId": preview.get("operationId"),
        "action": "confirm_approval_batch_action", "cardType": "approval_batch",
        "title": f"确认{label}", "approveLabel": f"确认{label}", "rejectLabel": "取消操作",
        "status": preview.get("status"), "allowedActions": ["approve", "reject"],
        "expiresAt": preview.get("expiresAt"),
        "fields": fields, "draft": {"tasks": tasks, "action": action, "reason": data.get("reason")},
        "threadId": context.runtime.get("threadId"), "runId": context.origin_run_id,
        "originRunId": context.origin_run_id, "messageId": context.runtime.get("messageId"),
    }


def confirmation_description(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:
    args = tool_call.get("args") or {}
    context, error = _load(str(args.get("preview_id") or ""), str(args.get("confirmation_token") or ""))
    return "当前批量审批确认上下文无效。" if error or context is None else json.dumps(confirmation_args(context, dict(args)), ensure_ascii=False)


def prepare_confirmation_interrupt(request: Any) -> bool:
    args = (request.tool_call or {}).get("args") or {}
    context, error = _load(str(args.get("preview_id") or ""), str(args.get("confirmation_token") or ""))
    if error or context is None:
        return False
    if not has_trusted_approval_projection(
        request,
        action="confirm_approval_batch_action",
        approval_id=context.preview.get("previewId"),
        draft_id=context.preview.get("previewId"),
        origin_run_id=context.origin_run_id,
        message_id=context.runtime.get("messageId"),
    ):
        return False
    status = str(context.preview.get("status") or "")
    operation_id = str(context.preview.get("operationId") or "").strip()
    if operation_id:
        if status == "APPROVED":
            if not str(context.preview.get("decisionIdempotencyKey") or "").strip():
                return False
            mark_run_resumed()
            return False
        if status in {"REJECTED", "EXPIRED"}:
            try:
                OperationRuntime.settle_approval(
                    operation_id,
                    status,
                    approval_id=str(context.preview.get("previewId") or "") or None,
                    required=True,
                )
            except Exception:
                return False
            mark_run_resumed()
            return False
        if status == "PENDING":
            emit(getattr(request.runtime, "stream_writer", None), "run.paused", "等待用户确认批量审批", require_persist=True,
                 eventId=f"{context.origin_run_id}:paused:{context.preview['previewId']}", approvalId=context.preview["previewId"], draftId=context.preview["previewId"], reason="approval_required")
            mark_run_paused()
            return True
        return False
    return False


def can_execute(context: ApprovalBatchContext) -> bool:
    operation_id = str(context.preview.get("operationId") or "").strip()
    if operation_id:
        try:
            operation_runtime = OperationRuntime.open_existing(operation_id, required=True)
        except Exception:
            return False
        if operation_runtime is None:
            return False
        try:
            return (
                str(context.preview.get("status") or "") == "APPROVED"
                and bool(str(context.preview.get("decisionIdempotencyKey") or "").strip())
                and operation_runtime.operation.status in {"WAITING_APPROVAL", "COMMITTING", "UNKNOWN"}
            )
        finally:
            operation_runtime.close()
    return False


def can_replay(context: ApprovalBatchContext) -> bool:
    """A completed Java operation can safely return its durable result again.

    This is deliberately narrower than normal execution: the Java facade
    accepts the stable idempotency key only for its already-completed preview,
    so no stale checkpoint can create a second BPM mutation.
    """
    return str(context.preview.get("status") or "") == "COMPLETED"


def complete(context: ApprovalBatchContext) -> bool:
    return True


def rejected(context: ApprovalBatchContext) -> bool:
    return True


def settle_terminal_approval(context: ApprovalBatchContext) -> ToolResponse | None:
    """Project a Java-owned batch rejection/expiry into its Operation."""
    status = str(context.preview.get("status") or "").upper()
    operation_id = str(context.preview.get("operationId") or "").strip()
    if status not in {"REJECTED", "EXPIRED"} or not operation_id:
        return None
    try:
        OperationRuntime.settle_approval(
            operation_id,
            status,
            approval_id=str(context.preview.get("previewId") or "") or None,
            required=True,
        )
    except Exception as exc:
        return tool_failure(
            "OPERATION_STATE_SYNC_FAILED",
            "批量审批已结束，但 Agent Operation 尚未同步，暂不继续恢复。",
            details=str(exc), retryable=True,
        )
    return None
