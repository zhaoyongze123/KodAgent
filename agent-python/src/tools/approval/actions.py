"""Approval preview and commit tools."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ...domain.effect import EffectRecord
from ...runtime.effect_commit import (
    CommitInProgress,
    CommitKernelError,
    EffectCommitCoordinator,
    ReconciliationPending,
    StoredFinalFailure,
)
from ...runtime.operation_runtime import OperationRuntime
from ..common import (
    JavaFacadeBusinessError,
    JavaFacadeConnectionError,
    JavaFacadeHttpError,
    JavaFacadeJsonDecodeError,
    JavaFacadeResponseTypeError,
    ToolResponse,
    bind_tool_call_id,
    current_agent_context,
    emit,
    reconcile_approval_task_action,
    java_get,
    java_post,
    tool_failure,
    tool_success,
)
from ...services.approval_batch_approval import (
    can_execute as can_execute_batch,
    can_replay as can_replay_batch,
    complete as complete_batch,
    load_pending_approval_batch_context,
    _load as load_approval_batch,
    settle_terminal_approval as settle_terminal_batch_approval,
)
from ...services.approval_task_approval import (
    can_execute as can_execute_task,
    cancel as cancel_task,
    complete as complete_task,
    load_approval_task_context,
    settle_terminal_approval,
)
from ...services.approval_request_approval import (
    can_execute as can_execute_request,
    cancel as cancel_request,
    complete as complete_request,
    load_approval_request_context,
)
from .common import approval_failure as _approval_failure


_BATCH_ACTION_ID = "approval.write.batch"


def _batch_operation_key(action: str, reason: str, task_ids: list[str], criteria: dict[str, Any] | None) -> str:
    """Build the stable identity of one batch preview request.

    The current message/run scope is added by ``OperationRuntime``. The key
    only distinguishes the business selection inside that turn, so a retried
    preview reopens the same Operation instead of creating another Approval.
    """
    identity = {
        "action": action,
        "reason": reason,
        "taskIds": task_ids,
        "criteria": criteria,
    }
    encoded = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "batch:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _is_unknown_batch_commit_error(exc: Exception) -> bool:
    if isinstance(exc, (JavaFacadeConnectionError, JavaFacadeJsonDecodeError,
                        JavaFacadeResponseTypeError)):
        return True
    if isinstance(exc, JavaFacadeHttpError):
        return bool(exc.retryable)
    return not isinstance(exc, JavaFacadeBusinessError)


def _batch_commit_coordinator(
    runtime: OperationRuntime,
    effect: EffectRecord,
    *,
    lease_owner: str,
) -> EffectCommitCoordinator:
    coordinator = EffectCommitCoordinator(
        runtime=runtime,
        expected_action_id=_BATCH_ACTION_ID,
        request_data=effect.request_data,
        idempotency_key=effect.idempotency_key,
        reconcile_strategy=effect.reconcile_strategy,
        lease_owner=lease_owner,
    )
    coordinator.effect = effect
    return coordinator


def _reconcile_batch_effect(runtime: OperationRuntime, effect: EffectRecord) -> dict[str, Any]:
    """Re-read BPM facts before deciding an atomic batch outcome."""
    coordinator = _batch_commit_coordinator(runtime, effect, lease_owner="approval-batch-reconcile")

    def resolve(current: EffectRecord) -> dict[str, Any] | None:
        preview_id = str(current.request_data.get("previewId") or "")
        record = java_post(
            f"/agent/tools/approvals/batch/{preview_id}/reconcile",
            {
                "confirmationToken": current.request_data.get("confirmationToken"),
                "operationId": runtime.operation_id,
                "idempotencyKey": current.idempotency_key,
            },
        )
        status = str(record.get("status") or "").upper()
        if status == "COMPLETED":
            result = record.get("result")
            return result if isinstance(result, dict) else {
                "previewId": preview_id,
                "status": "COMPLETED",
                "results": [],
                "idempotentReplay": True,
            }
        if status in {"FAILED", "FAILED_FINAL", "INCONSISTENT"}:
            raise StoredFinalFailure({
                "code": "APPROVAL_BATCH_RECONCILIATION_FAILED",
                "message": str(record.get("message") or "批量审批结果需要人工核对"),
            })
        # PENDING/UNKNOWN/APPROVED/EXECUTING do not prove a commit. Leave the
        # Effect UNKNOWN and require another read or manual review; never
        # submit the batch a second time here.
        return None

    return coordinator.reconcile(resolve, pending_message="批量审批提交结果仍未知，请先核对待办状态")

@tool
def preview_approval_batch_action(
    action: str,
    reason: str = "",
    task_ids: list[str] | None = None,
    process_types: list[str] | None = None,
    amount_operator: str | None = None,
    amount: float | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    department: str | None = None,
    min_pending_days: int | None = None,
    sort_by: str = "CREATED_DESC",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """生成批量通过或驳回待办的预览，不会执行审批。

    只能提供 task_ids，或提供一组结构化筛选条件，两者不可混用。
    action 只能是 APPROVE 或 REJECT；批量驳回必须给出统一且具体的 reason。
    预览结果会生成官方确认卡片；只有用户点击卡片确认后的 HITL
    恢复能调用内部执行服务，模型不能直接执行。
    """
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    tool_name = "preview_approval_batch_action"
    normalized_action = action.strip().upper() if isinstance(action, str) else ""
    normalized_ids = [value.strip() for value in (task_ids or []) if isinstance(value, str) and value.strip()]
    has_criteria = any([
        process_types,
        amount_operator,
        amount is not None,
        created_from,
        created_to,
        department,
        min_pending_days is not None,
    ])
    if normalized_action not in {"APPROVE", "REJECT"}:
        return tool_failure("APPROVAL_BATCH_ACTION_INVALID", "批量操作仅支持 APPROVE 或 REJECT。")
    if bool(normalized_ids) == has_criteria:
        return tool_failure("APPROVAL_BATCH_SELECTION_INVALID", "请提供待办 ID 列表，或提供筛选条件之一，不能同时提供。")
    if normalized_action == "REJECT" and not reason.strip():
        return tool_failure("APPROVAL_BATCH_REASON_REQUIRED", "批量驳回前必须填写统一且具体的驳回理由。")
    context = current_agent_context()
    message_id = str(context.get("messageId") or "").strip()
    if not message_id:
        return tool_failure("APPROVAL_BATCH_CONTEXT_INVALID", "当前批量审批预览缺少消息上下文，请重新发起请求。")
    criteria: dict[str, Any] | None = None
    if has_criteria:
        criteria = {
            "processTypes": [value.strip() for value in (process_types or []) if isinstance(value, str) and value.strip()] or None,
            "amountOperator": amount_operator.strip().upper() if isinstance(amount_operator, str) and amount_operator.strip() else None,
            "amount": amount,
            "createdFrom": created_from.strip() if isinstance(created_from, str) and created_from.strip() else None,
            "createdTo": created_to.strip() if isinstance(created_to, str) and created_to.strip() else None,
            "department": department.strip() if isinstance(department, str) and department.strip() else None,
            "minPendingDays": min_pending_days,
            "sortBy": sort_by.strip().upper() if isinstance(sort_by, str) and sort_by.strip() else "CREATED_DESC",
        }
        criteria = {key: value for key, value in criteria.items() if value is not None}
    payload = {
        "action": normalized_action,
        "reason": reason.strip(),
        "taskIds": normalized_ids or None,
        "criteria": criteria,
        "previewMessageId": message_id,
        "runId": str(context.get("runId") or "") or None,
        "threadId": str(context.get("threadId") or "") or None,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    label = "通过" if normalized_action == "APPROVE" else "驳回"
    emit(writer, "tool_started", f"🔧 正在生成批量{label}预览……", toolName=tool_name, toolCallId=tool_call_id)
    runtime: OperationRuntime | None = None
    try:
        runtime = OperationRuntime.start(
            action_id=_BATCH_ACTION_ID,
            capability_id="approval",
            payload={
                "action": normalized_action,
                "reason": reason.strip(),
                "taskIds": normalized_ids,
                "criteria": criteria,
            },
            operation_key=_batch_operation_key(normalized_action, reason.strip(), normalized_ids, criteria),
            required=True,
        )
        if runtime is None:
            raise RuntimeError("批量审批缺少可用的 Operation Runtime")
        if runtime.operation.status == "COLLECTING_INFO":
            runtime.transition("READY", event_type="operation.ready")
        if runtime.operation.status == "READY":
            runtime.transition("RUNNING", event_type="operation.running")
        if runtime.operation.status not in {"RUNNING", "WAITING_APPROVAL"}:
            raise RuntimeError(f"批量审批 Operation 当前状态不可预览: {runtime.operation.status}")
        payload["operationId"] = runtime.operation_id
        result = java_post("/agent/tools/approvals/batch/preview", payload)
    except Exception as exc:
        if runtime is not None and runtime.operation.status in {"COLLECTING_INFO", "READY", "RUNNING"}:
            try:
                runtime.transition("FAILED", event_type="operation.failed", data={"reason": str(exc)[:500]})
                runtime.patch_result({"status": "FAILED", "error": str(exc)[:500]})
            except Exception:
                pass
        return _approval_failure(writer, tool_name, tool_call_id, "批量审批预览生成失败，请稍后重试", exc)
    try:
        if not isinstance(result, dict) or not result.get("previewId") or not result.get("confirmationToken"):
            raise RuntimeError("批量审批预览缺少确认上下文")
        if str(result.get("operationId") or "") != runtime.operation_id:
            raise RuntimeError("Java 批量审批预览未返回匹配的 Operation")
        runtime.bind_approval(str(result["previewId"]))
        if runtime.operation.status == "RUNNING":
            runtime.transition("WAITING_APPROVAL", event_type="operation.waiting_approval", data={"approvalId": result["previewId"]})
        # Java's preview row owns the action, target set, expiry and final BPM
        # idempotency facts. Operation keeps only the Agent-side projection;
        # Redis is not part of the approval proof.
        runtime.merge_payload({
            "approval_batch_preview": {
                **result,
                "runId": payload.get("runId"),
                "threadId": payload.get("threadId"),
                "messageId": message_id,
                "operationId": runtime.operation_id,
            },
        })
        count = result.get("taskCount", 0)
        presentation = {"blockType": "card", "cardType": "approval_batch_preview"}
        emit(writer, "tool_completed", f"✅ 已生成 {count} 条待办的批量{label}预览，等待你的确认",
             toolName=tool_name, toolCallId=tool_call_id, result=result, presentation=presentation)
        return tool_success(result, presentation)
    except Exception as exc:
        if runtime.operation.status in {"COLLECTING_INFO", "READY", "RUNNING"}:
            try:
                runtime.transition("FAILED", event_type="operation.failed", data={"reason": str(exc)[:500]})
                runtime.patch_result({"status": "FAILED", "error": str(exc)[:500]})
            except Exception:
                pass
        return _approval_failure(writer, tool_name, tool_call_id, "批量审批预览失败，请稍后重试", exc)
    finally:
        if runtime is not None:
            runtime.close()


@tool
def confirm_approval_batch_action(
    preview_id: str,
    confirmation_token: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """提交已由官方 ApprovalCard 确认的批量审批预览。

    该工具只能在 LangGraph Human-in-the-loop 恢复后调用；不能由模型
    根据自然语言“确认”绕过确认卡片。
    """
    bind_tool_call_id(tool_call_id)
    context, context_error = load_approval_batch(preview_id.strip(), confirmation_token.strip())
    if context_error or context is None:
        return context_error or tool_failure("APPROVAL_BATCH_CONTEXT_INVALID", "批量审批确认上下文无效。")
    status = str(context.preview.get("status") or "")
    operation_id = str(context.preview.get("operationId") or context.runtime.get("operationId") or "").strip()
    if status in {"REJECTED", "EXPIRED"}:
        # A rejected ApprovalCard still resumes the interrupted graph.  It is
        # a terminal, successful cancellation rather than a tool failure.
        sync_error = settle_terminal_batch_approval(context)
        if sync_error:
            return sync_error
        complete_batch(context)
        message = "已取消批量审批操作" if status == "REJECTED" else "批量审批已过期"
        emit(get_stream_writer(), "approval.rejected", message, toolName="confirm_approval_batch_action", toolCallId=tool_call_id)
        return tool_success({"previewId": preview_id.strip(), "status": status, "cancelled": True})
    if not can_execute_batch(context) and not can_replay_batch(context):
        return tool_failure("APPROVAL_RESUME_REQUIRED", "当前批量审批尚未通过确认卡片，不能执行。")
    writer = get_stream_writer()
    emit(writer, "tool_started", "📨 用户已确认，正在原子执行批量审批……", toolName="confirm_approval_batch_action", toolCallId=tool_call_id)
    payload = {
        "previewId": preview_id.strip(), "confirmationToken": confirmation_token.strip(),
        "confirmationMessageId": str(context.runtime.get("messageId") or ""),
        # The Java facade replays this exact result when a transport retry
        # reaches an already-COMPLETED preview.
        "idempotencyKey": f"approval-batch:v2:{preview_id.strip()}",
    }
    if operation_id:
        payload["operationId"] = operation_id
    runtime: OperationRuntime | None = None
    coordinator: EffectCommitCoordinator | None = None
    effect: EffectRecord | None = None
    try:
        if operation_id:
            runtime = OperationRuntime.open_existing(operation_id, required=True)
            if runtime is None:
                raise CommitKernelError("OPERATION_RUNTIME_UNAVAILABLE", "批量审批缺少可用的 Operation Runtime")
            preview = context.preview.get("preview") if isinstance(context.preview.get("preview"), dict) else {}
            request_data = {
                **payload,
                "action": preview.get("action"),
                "reason": preview.get("reason"),
                "taskIds": preview.get("taskIds") or [
                    item.get("taskId") for item in (preview.get("tasks") if isinstance(preview.get("tasks"), list) else [])
                    if isinstance(item, dict) and item.get("taskId")
                ],
            }
            coordinator = EffectCommitCoordinator(
                runtime=runtime,
                expected_action_id=_BATCH_ACTION_ID,
                request_data=request_data,
                idempotency_key=payload["idempotencyKey"],
                reconcile_strategy="approval.batch.preview-status",
                lease_owner=f"{context.runtime.get('runId') or 'run'}:{tool_call_id or 'approval-batch-commit'}",
            )
            start = coordinator.prepare()
            effect = start.effect
            if start.reconciliation_required:
                result = _reconcile_batch_effect(runtime, effect)
            elif start.recovered_result is not None:
                result = start.recovered_result
            else:
                result = java_post("/agent/tools/approvals/batch/execute", payload)
                coordinator.settle_success(result)
        else:
            raise CommitKernelError(
                "OPERATION_REQUIRED",
                "批量审批缺少 Operation 绑定，旧版直接执行路径已关闭，请重新生成预览。",
            )
    except ReconciliationPending as exc:
        emit(writer, "tool_failed", "批量审批提交结果仍未知，请先核对待办状态", toolName="confirm_approval_batch_action", toolCallId=tool_call_id, errorCode="APPROVAL_BATCH_RECONCILIATION_PENDING")
        return tool_failure("APPROVAL_BATCH_RECONCILIATION_PENDING", str(exc), retryable=True)
    except CommitInProgress as exc:
        return tool_failure("APPROVAL_BATCH_COMMIT_IN_PROGRESS", str(exc), retryable=True)
    except StoredFinalFailure as exc:
        return tool_failure(exc.code, exc.message, retryable=False)
    except CommitKernelError as exc:
        return tool_failure(exc.code, exc.message, retryable=False)
    except JavaFacadeBusinessError as exc:
        if coordinator is not None and runtime is not None:
            try:
                coordinator.record_failure(exc, unknown=False, code="APPROVAL_BATCH_BUSINESS_REJECTED")
            except Exception:
                pass
        return _approval_failure(writer, "confirm_approval_batch_action", tool_call_id, "批量审批未被业务系统接受，请重新读取待办状态", exc)
    except Exception as exc:
        if coordinator is not None and runtime is not None:
            unknown = _is_unknown_batch_commit_error(exc)
            try:
                coordinator.record_failure(
                    exc,
                    unknown=unknown,
                    code="APPROVAL_BATCH_COMMIT_UNKNOWN" if unknown else "APPROVAL_BATCH_SUBMIT_FAILED",
                )
            except Exception:
                pass
            return _approval_failure(
                writer,
                "confirm_approval_batch_action",
                tool_call_id,
                "批量审批提交结果未知，请稍后先核对待办状态" if unknown else "批量审批未执行，请检查待办最新状态后重试",
                exc,
            )
        return _approval_failure(writer, "confirm_approval_batch_action", tool_call_id, "批量审批未执行，请检查待办最新状态后重试", exc)
    finally:
        if runtime is not None:
            runtime.close()
    complete_batch(context)
    completed = len(result.get("results", [])) if isinstance(result, dict) else 0
    emit(writer, "approval.approved", f"✅ 已完成 {completed} 条待办的批量审批", toolName="confirm_approval_batch_action", toolCallId=tool_call_id, operationId=operation_id or None, result=result)
    return tool_success(result, {"blockType": "card", "cardType": "approval_batch_result"})


@tool
def get_approval_task_detail(
    task_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取当前用户的一条待办详情；Java 会验证任务仍归当前用户处理。"""
    bind_tool_call_id(tool_call_id)
    if not task_id.strip():
        return tool_failure("APPROVAL_TASK_ID_REQUIRED", "请选择需要查看的待办审批。")
    writer = get_stream_writer()
    tool_name = "get_approval_task_detail"
    emit(writer, "tool_started", "🔧 正在读取待办审批详情……", toolName=tool_name, toolCallId=tool_call_id)
    try:
        result = java_get(f"/agent/tools/tasks/{task_id.strip()}")
    except Exception as exc:
        return _approval_failure(writer, tool_name, tool_call_id, "待办详情读取失败，请稍后重试", exc)
    presentation = {"blockType": "card", "cardType": "approval_task"}
    emit(writer, "tool_completed", "✅ 已获取待办审批详情", toolName=tool_name, toolCallId=tool_call_id,
         result=result, presentation=presentation)
    return tool_success(result, presentation)


_TASK_ACTION_ID = "approval.write.task"


def _task_operation_key(task_id: str, action: str, reason: str) -> str:
    return f"{task_id.strip()}|{action.strip().upper()}|{reason.strip()}"


def _is_unknown_task_commit_error(exc: Exception) -> bool:
    if isinstance(exc, (JavaFacadeConnectionError, JavaFacadeJsonDecodeError,
                        JavaFacadeResponseTypeError)):
        return True
    if isinstance(exc, JavaFacadeHttpError):
        return bool(exc.retryable)
    return not isinstance(exc, JavaFacadeBusinessError)


def _task_commit_coordinator(
    runtime: OperationRuntime,
    effect: EffectRecord,
    *,
    lease_owner: str,
) -> EffectCommitCoordinator:
    coordinator = EffectCommitCoordinator(
        runtime=runtime,
        expected_action_id=_TASK_ACTION_ID,
        request_data=effect.request_data,
        idempotency_key=effect.idempotency_key,
        reconcile_strategy=effect.reconcile_strategy,
        lease_owner=lease_owner,
    )
    coordinator.effect = effect
    return coordinator


def _reconcile_task_effect(runtime: OperationRuntime, effect: EffectRecord) -> dict[str, Any]:
    coordinator = _task_commit_coordinator(runtime, effect, lease_owner="approval-task-reconcile")

    def resolve(current: EffectRecord) -> dict[str, Any] | None:
        request = current.request_data
        payload = reconcile_approval_task_action(
            str(request.get("approvalId") or ""),
            str(request.get("operationId") or runtime.operation_id),
        )
        if isinstance(payload.get("data"), dict) and "status" not in payload:
            payload = payload["data"]
        status = str(payload.get("status") or "").upper()
        if status == "SUBMITTED":
            result = payload.get("result")
            return result if isinstance(result, dict) else {
                key: value for key, value in payload.items() if key not in {"status", "result"}
            }
        if status == "FAILED_FINAL":
            raise StoredFinalFailure({
                "code": "APPROVAL_TASK_EXTERNAL_STATE_MISMATCH",
                "message": str(payload.get("message") or "待办状态与原审批动作不一致"),
            })
        return None

    return coordinator.reconcile(resolve, pending_message="单条审批提交结果仍未知，请稍后重试")


def _completed_task_result(
    context: Any,
    approval_id: str,
) -> dict[str, Any] | None:
    """Read a completed task action without opening another business claim.

    A repeated click can arrive after the Java Approval has already reached
    ``COMPLETED``.  That is a replay, not a new resume: do not require the
    old ``APPROVED + resume`` gate again and never call the BPM mutation
    endpoint.  Prefer the durable Effect result; the Java Approval result is
    the narrow fallback for a projection that completed before Python closed
    its local record.
    """
    operation_id = str(context.approval.get("operationId") or "").strip()
    if operation_id:
        runtime = OperationRuntime.open_existing(operation_id, required=True)
        if runtime is not None:
            try:
                effect = runtime.get_effect(
                    f"approval-task:v2:{approval_id}"
                )
                if effect is not None and effect.status == "SUCCEEDED":
                    return dict(effect.response_data or {})
            finally:
                runtime.close()

    draft = context.approval.get("draft")
    if isinstance(draft, dict) and isinstance(draft.get("result"), dict):
        return dict(draft["result"])
    return None


@tool
def preview_approval_task_action(
    task_id: str,
    action: str,
    reason: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """生成单条待办通过/驳回预览，正式操作必须通过 ApprovalCard。"""
    bind_tool_call_id(tool_call_id)
    normalized = str(action or "").strip().upper()
    if normalized not in {"APPROVE", "REJECT"}:
        return tool_failure("APPROVAL_ACTION_INVALID", "单条审批动作仅支持 APPROVE 或 REJECT。")
    if normalized == "REJECT" and not str(reason or "").strip():
        return tool_failure("APPROVAL_REASON_REQUIRED", "驳回审批必须填写具体理由。")
    context = current_agent_context()
    normalized_task_id = str(task_id or "").strip()
    normalized_reason = str(reason or "").strip()
    payload = {
        "taskId": normalized_task_id,
        "action": normalized,
        "reason": normalized_reason,
        "runId": context.get("runId"),
        "threadId": context.get("threadId"),
        "messageId": context.get("messageId"),
    }
    if not payload["taskId"] or not all(payload.get(key) for key in ("runId", "threadId", "messageId")):
        return tool_failure("APPROVAL_CONTEXT_INVALID", "单条审批预览缺少当前消息上下文，请重新发起。")
    runtime: OperationRuntime | None = None
    try:
        runtime = OperationRuntime.start(
            action_id=_TASK_ACTION_ID,
            capability_id="approval",
            payload=payload,
            operation_key=_task_operation_key(normalized_task_id, normalized, normalized_reason),
            required=True,
        )
        if runtime is None:
            raise RuntimeError("单条审批缺少可用的 Operation Runtime")
        if runtime.operation.status == "COLLECTING_INFO":
            runtime.transition("READY", event_type="operation.ready")
        if runtime.operation.status == "READY":
            runtime.transition("RUNNING", event_type="operation.running")
        if runtime.operation.status not in {"RUNNING", "WAITING_APPROVAL"}:
            raise RuntimeError(f"单条审批 Operation 当前状态不可预览: {runtime.operation.status}")
        payload["operationId"] = runtime.operation_id
        result = java_post("/agent/tools/tasks/action-preview", payload)
        result = result.get("data") if isinstance(result.get("data"), dict) and "approvalId" in result.get("data", {}) else result
        approval_id = str(result.get("approvalId") or "").strip()
        operation_id = str(result.get("operationId") or "").strip()
        if not approval_id or operation_id != runtime.operation_id:
            raise RuntimeError("Java 单条审批预览未返回匹配的 Approval/Operation")
        runtime.bind_approval(approval_id)
        if runtime.operation.status == "RUNNING":
            runtime.transition("WAITING_APPROVAL", event_type="operation.waiting_approval", data={"approvalId": approval_id})
        result["operationId"] = runtime.operation_id
        runtime.merge_payload({"approval_task_approval": result})
        return tool_success(result, {"blockType": "card", "cardType": "approval_task"})
    except Exception as exc:
        if runtime is not None and runtime.operation.status in {"COLLECTING_INFO", "READY", "RUNNING"}:
            try:
                runtime.transition("FAILED", event_type="operation.failed", data={"reason": str(exc)[:500]})
                runtime.patch_result({"status": "FAILED", "error": str(exc)[:500]})
            except Exception:
                pass
        return _approval_failure(get_stream_writer(), "preview_approval_task_action", tool_call_id, "单条审批预览失败，请稍后重试", exc)
    finally:
        if runtime is not None:
            runtime.close()


@tool
def confirm_approval_task_action(
    approval_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """仅由官方 ApprovalCard Resume 后执行一条已确认的待办审批。"""
    bind_tool_call_id(tool_call_id)
    context, error = load_approval_task_context(approval_id)
    if error or context is None or str(context.approval.get("approvalId") or "") != str(approval_id or ""):
        return error or tool_failure("APPROVAL_CONTEXT_INVALID", "单条审批确认上下文无效。")
    approval_status = str(context.approval.get("status") or "").upper()
    if approval_status in {"REJECTED", "EXPIRED"}:
        sync_error = settle_terminal_approval(context)
        if sync_error:
            return sync_error
        cancel_task(context)
        return tool_success({"approvalId": approval_id, "cancelled": True, "status": approval_status})
    if approval_status == "COMPLETED":
        replay = _completed_task_result(context, approval_id)
        if replay is not None:
            return tool_success(replay, {"blockType": "card", "cardType": "approval_task_result"})
        return tool_failure(
            "APPROVAL_RESULT_UNAVAILABLE",
            "单条审批已经完成，但结果投影暂不可用，请稍后重试。",
            retryable=True,
        )
    recovery_mode = approval_status == "SUBMITTING"
    if not recovery_mode and not can_execute_task(context):
        return tool_failure("APPROVAL_RESUME_REQUIRED", "当前单条审批尚未通过确认卡片，不能执行。")
    draft = context.approval.get("draft") if isinstance(context.approval.get("draft"), dict) else {}
    operation_id = str(context.approval.get("operationId") or context.runtime.get("operationId") or "").strip()
    runtime: OperationRuntime | None = None
    coordinator: EffectCommitCoordinator | None = None
    effect: EffectRecord | None = None
    result: dict[str, Any]
    try:
        if operation_id:
            runtime = OperationRuntime.open_existing(operation_id, required=True)
            if runtime is None:
                raise CommitKernelError("OPERATION_RUNTIME_UNAVAILABLE", "单条审批缺少可用的 Operation Runtime")
            idempotency_key = f"approval-task:v2:{approval_id}"
            if recovery_mode:
                # SUBMITTING means another worker already claimed the Java
                # boundary. Only an existing UNKNOWN/RECONCILING/SUCCEEDED
                # Effect is recoverable here; never create or claim a fresh
                # Effect from this state.
                effect = runtime.get_effect(idempotency_key)
                if effect is None:
                    raise CommitKernelError(
                        "APPROVAL_RECONCILIATION_REQUIRED",
                        "单条审批已进入提交窗口，但缺少 Effect 记录，请先核对外部待办状态",
                    )
                if effect.status in {"CLAIMED", "EXECUTING"}:
                    raise CommitInProgress("单条审批提交正在由其他执行者处理")
                if effect.status not in {"UNKNOWN", "RECONCILING", "SUCCEEDED"}:
                    raise CommitKernelError(
                        "APPROVAL_RECONCILIATION_REQUIRED",
                        f"单条审批提交窗口的 Effect 状态为 {effect.status}，不能重新执行",
                    )
                coordinator = _task_commit_coordinator(
                    runtime,
                    effect,
                    lease_owner=f"{context.runtime.get('runId') or 'run'}:{tool_call_id or 'approval-task-reconcile'}",
                )
                start = coordinator.prepare()
                if start.reconciliation_required:
                    result = _reconcile_task_effect(runtime, start.effect)
                elif start.recovered_result is not None:
                    result = start.recovered_result
                else:
                    raise CommitKernelError(
                        "APPROVAL_RECONCILIATION_REQUIRED",
                        "单条审批提交结果尚未被外部事实确认",
                    )
            else:
                coordinator = EffectCommitCoordinator(
                    runtime=runtime,
                    expected_action_id=_TASK_ACTION_ID,
                    request_data={
                        "approvalId": approval_id,
                        "operationId": operation_id,
                        "taskId": draft.get("taskId"),
                        "action": draft.get("action"),
                        "reason": draft.get("reason"),
                    },
                    idempotency_key=idempotency_key,
                    reconcile_strategy="approval.task.action-status",
                    lease_owner=f"{context.runtime.get('runId') or 'run'}:{tool_call_id or 'approval-task-commit'}",
                )
                start = coordinator.prepare()
                effect = start.effect
                if start.reconciliation_required:
                    result = _reconcile_task_effect(runtime, effect)
                elif start.recovered_result is not None:
                    result = start.recovered_result
                else:
                    result = java_post("/agent/tools/tasks/action-execute", {
                        "approvalId": approval_id,
                        "operationId": operation_id,
                        "idempotencyKey": idempotency_key,
                    })
                    coordinator.settle_success(result)
        else:
            raise CommitKernelError(
                "OPERATION_REQUIRED",
                "单条审批缺少 Operation 绑定，旧版直接执行路径已关闭，请重新生成预览。",
            )
    except ReconciliationPending as exc:
        emit(get_stream_writer(), "tool_failed", "单条审批提交结果仍未知，请稍后重试", toolName="confirm_approval_task_action", toolCallId=tool_call_id, errorCode="APPROVAL_TASK_RECONCILIATION_PENDING")
        return tool_failure("APPROVAL_TASK_RECONCILIATION_PENDING", str(exc), retryable=True)
    except CommitInProgress as exc:
        return tool_failure("APPROVAL_TASK_COMMIT_IN_PROGRESS", str(exc), retryable=True)
    except StoredFinalFailure as exc:
        return tool_failure(exc.code, exc.message, retryable=False)
    except CommitKernelError as exc:
        return tool_failure(exc.code, exc.message, retryable=False)
    except JavaFacadeBusinessError as exc:
        if coordinator is not None and runtime is not None:
            try:
                coordinator.record_failure(exc, unknown=False, code="APPROVAL_TASK_BUSINESS_REJECTED")
            except Exception:
                pass
        return _approval_failure(get_stream_writer(), "confirm_approval_task_action", tool_call_id, "单条审批未被业务系统接受，请重新读取待办状态", exc)
    except Exception as exc:
        if coordinator is not None and runtime is not None:
            unknown = _is_unknown_task_commit_error(exc)
            try:
                coordinator.record_failure(
                    exc,
                    unknown=unknown,
                    code="APPROVAL_TASK_COMMIT_UNKNOWN" if unknown else "APPROVAL_TASK_SUBMIT_FAILED",
                )
            except Exception:
                pass
            return _approval_failure(
                get_stream_writer(),
                "confirm_approval_task_action",
                tool_call_id,
                "单条审批提交结果未知，请稍后先核对待办状态" if unknown else "单条审批未执行，请检查待办最新状态后重试",
                exc,
            )
        return _approval_failure(get_stream_writer(), "confirm_approval_task_action", tool_call_id, "单条审批未执行，请检查待办最新状态后重试", exc)
    finally:
        if runtime is not None:
            runtime.close()
    complete_task(context)
    emit(get_stream_writer(), "approval.approved", f"✅ 已完成审批{('通过' if draft.get('action') == 'APPROVE' else '驳回')}", toolName="confirm_approval_task_action", toolCallId=tool_call_id, operationId=operation_id or None, result=result)
    return tool_success(result, {"blockType": "card", "cardType": "approval_task_result"})


__all__ = [
    "preview_approval_batch_action",
    "confirm_approval_batch_action",
    "get_approval_task_detail",
    "preview_approval_task_action",
    "confirm_approval_task_action",
]
