"""Approval tools for the domain boundary."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import (
    JavaFacadeBusinessError, JavaFacadeConnectionError, JavaFacadeHttpError,
    JavaFacadeJsonDecodeError, JavaFacadeResponseTypeError, ToolResponse,
    bind_tool_call_id, current_agent_context, emit, java_get, java_post,
    tool_failure, tool_success,
)
from ...domain.effect import EffectRecord
from ...runtime.effect_commit import (
    CommitInProgress,
    CommitKernelError,
    EffectCommitCoordinator,
    ReconciliationPending,
    StoredFinalFailure,
)
from ...runtime.operation_runtime import OperationRuntime
from ...services.approval_request_approval import (
    can_execute as can_execute_request,
    cancel as cancel_request,
    complete as complete_request,
    load_approval_request_context,
)
from .common import (
    approval_failure as _approval_failure,
    request_payload as _request_payload,
)


def _operation_key(prefix: str, payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"{prefix}:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


def _start_operation(action_id: str, payload: dict[str, Any], operation_key: str) -> tuple[OperationRuntime, dict[str, Any]]:
    runtime = OperationRuntime.start(
        action_id=action_id,
        capability_id="approval",
        payload=payload,
        operation_key=operation_key,
        required=True,
    )
    if runtime is None:
        raise RuntimeError("审批申请缺少可用的 Operation Runtime")
    try:
        if runtime.operation.status == "CREATED":
            runtime.transition("COLLECTING_INFO", event_type="operation.collecting_info")
        if runtime.operation.status == "COLLECTING_INFO":
            runtime.transition("READY", event_type="operation.ready")
        if runtime.operation.status == "READY":
            runtime.transition("RUNNING", event_type="operation.running")
        return runtime, {**payload, "operationId": runtime.operation_id}
    except Exception:
        runtime.close()
        raise


def _bind_draft_operation(runtime: OperationRuntime, result: dict[str, Any]) -> None:
    operation_id = str(result.get("operationId") or "").strip()
    approval_id = str(result.get("approvalId") or "").strip()
    if operation_id != runtime.operation_id:
        raise RuntimeError("审批草稿返回的 operationId 与 Runtime 不一致")
    if not approval_id:
        raise RuntimeError("审批草稿缺少 approvalId")
    if runtime.operation.approval_id and runtime.operation.approval_id != approval_id:
        raise RuntimeError("审批草稿返回了其他 Approval")
    runtime.bind_approval(approval_id)
    if runtime.operation.status in {"READY", "RUNNING"}:
        runtime.transition("WAITING_APPROVAL", event_type="operation.waiting_approval", data={"approvalId": approval_id})
    elif runtime.operation.status != "WAITING_APPROVAL":
        raise RuntimeError(f"审批草稿绑定时 Operation 状态无效: {runtime.operation.status}")


def _fail_operation(runtime: OperationRuntime | None, exc: Exception) -> None:
    if runtime is None:
        return
    try:
        if runtime.operation.status not in {"SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"}:
            runtime.transition("FAILED", event_type="operation.failed", data={"error": str(exc)[:500]})
    except Exception:
        pass
    finally:
        runtime.close()


def _create_draft_with_operation(
    *, endpoint: str, action_id: str, operation_key: str, payload: dict[str, Any],
) -> dict[str, Any]:
    runtime: OperationRuntime | None = None
    try:
        runtime, request = _start_operation(action_id, payload, operation_key)
        result = java_post(endpoint, request)
        if not isinstance(result, dict):
            raise RuntimeError("审批草稿响应格式无效")
        _bind_draft_operation(runtime, result)
        return result
    except Exception as exc:
        _fail_operation(runtime, exc)
        raise
    finally:
        if runtime is not None and not runtime._closed:
            runtime.close()


def _is_unknown_commit_error(exc: Exception) -> bool:
    if isinstance(exc, (JavaFacadeConnectionError, JavaFacadeJsonDecodeError,
                        JavaFacadeResponseTypeError)):
        return True
    if isinstance(exc, JavaFacadeHttpError):
        return bool(exc.retryable)
    return not isinstance(exc, JavaFacadeBusinessError)


def _resolve_approval_result(effect: EffectRecord) -> dict[str, Any] | None:
    approval_id = str(effect.request_data.get("approvalId") or "").strip()
    if not approval_id:
        return None
    approval = java_get(f"/agent/approvals/{approval_id}")
    if str(approval.get("status") or "").upper() != "COMPLETED":
        return None
    draft = approval.get("draft") if isinstance(approval.get("draft"), dict) else {}
    result = draft.get("result")
    return dict(result) if isinstance(result, dict) else None

@tool
def create_approval_request_draft(
    request_type: str,
    start_time: str,
    end_time: str,
    approval_type: int | None,
    reason: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """创建请假/出差审批草稿并生成官方确认卡，不会提交 BPM。"""
    bind_tool_call_id(tool_call_id)
    payload, failure = _request_payload(request_type, start_time, end_time, approval_type, reason)
    if failure:
        return failure
    context = current_agent_context()
    binding = {key: str(context.get(key) or "") for key in ("runId", "threadId", "messageId")}
    if not all(binding.values()):
        return tool_failure("APPROVAL_CONTEXT_INVALID", "当前审批申请缺少运行、线程或消息绑定，请重新发起。")
    operation_payload = {**payload, **binding}
    writer = get_stream_writer()
    emit(writer, "tool_started", "🔧 正在生成审批申请草稿……", toolName="create_approval_request_draft", toolCallId=tool_call_id)
    try:
        result = _create_draft_with_operation(
            endpoint="/agent/tools/approvals/request-draft",
            action_id="approval.request.create",
            operation_key=_operation_key("request", operation_payload),
            payload=operation_payload,
        )
    except Exception as exc:
        return _approval_failure(writer, "create_approval_request_draft", tool_call_id, "审批申请草稿生成失败，请稍后重试", exc)
    emit(writer, "draft.created", "📝 审批申请草稿已生成，等待用户确认", toolName="create_approval_request_draft", toolCallId=tool_call_id, result=result, draftId=result.get("draftId"), approvalId=result.get("approvalId"), presentation={"blockType": "card", "cardType": "approval_request"})
    return tool_success({**result, "requires_confirmation": True}, {"blockType": "card", "cardType": "approval_request"})


@tool
def create_generic_approval_request_draft(
    process_definition: str,
    variables: dict[str, Any] | None = None,
    start_user_select_assignees: dict[str, list[int]] | None = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """按当前用户可发起的任意审批模板生成草稿，不会直接启动 BPM。

    先调用 list_startable_approval_types 获取模板和表单字段，再将用户
    提供的业务字段放进 variables。Java 会再次按模板字段、权限和流程
    定义校验，模型不能注入引擎系统变量。
    """
    bind_tool_call_id(tool_call_id)
    process_definition = str(process_definition or "").strip()
    if not process_definition:
        return tool_failure("APPROVAL_TEMPLATE_REQUIRED", "请先指定要发起的审批模板。")
    if variables is not None and not isinstance(variables, dict):
        return tool_failure("APPROVAL_FORM_INVALID", "审批表单字段必须是对象。")
    context = current_agent_context()
    binding = {key: str(context.get(key) or "") for key in ("runId", "threadId", "messageId")}
    if not all(binding.values()):
        return tool_failure("APPROVAL_CONTEXT_INVALID", "当前审批申请缺少运行、线程或消息绑定，请重新发起。")
    payload = {
        "processDefinition": process_definition,
        "variables": variables or {},
        "startUserSelectAssignees": start_user_select_assignees or {},
        **binding,
        "taskId": str(context.get("taskId") or "") or None,
    }
    payload = {key: value for key, value in payload.items() if value is not None}
    writer = get_stream_writer()
    emit(writer, "tool_started", "🔧 正在生成通用审批申请草稿……", toolName="create_generic_approval_request_draft", toolCallId=tool_call_id)
    try:
        result = _create_draft_with_operation(
            endpoint="/agent/tools/approvals/generic/draft",
            action_id="approval.request.create",
            operation_key=_operation_key("generic-request", payload),
            payload=payload,
        )
    except Exception as exc:
        return _approval_failure(writer, "create_generic_approval_request_draft", tool_call_id, "通用审批申请草稿生成失败，请稍后重试", exc)
    emit(writer, "draft.created", "📝 通用审批申请草稿已生成，等待用户确认", toolName="create_generic_approval_request_draft", toolCallId=tool_call_id, result=result, draftId=result.get("draftId"), approvalId=result.get("approvalId"), presentation={"blockType": "card", "cardType": "approval_request"})
    return tool_success({**result, "requires_confirmation": True}, {"blockType": "card", "cardType": "approval_request"})


@tool
def create_approval_withdraw_draft(
    process_instance_id: str,
    reason: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """创建撤回本人运行中审批流程的确认草稿，不会立刻撤回。"""
    bind_tool_call_id(tool_call_id)
    process_id, normalized_reason = str(process_instance_id or "").strip(), str(reason or "").strip()
    if not process_id or not normalized_reason:
        return tool_failure("APPROVAL_WITHDRAW_FIELDS_INCOMPLETE", "撤回审批需要流程实例编号和撤回理由。")
    context = current_agent_context()
    binding = {key: str(context.get(key) or "") for key in ("runId", "threadId", "messageId")}
    if not all(binding.values()):
        return tool_failure("APPROVAL_CONTEXT_INVALID", "当前撤回操作缺少运行、线程或消息绑定，请重新发起。")
    operation_payload = {"processInstanceId": process_id, "reason": normalized_reason, **binding}
    writer = get_stream_writer()
    emit(writer, "tool_started", "🔧 正在生成审批撤回草稿……", toolName="create_approval_withdraw_draft", toolCallId=tool_call_id)
    try:
        result = _create_draft_with_operation(
            endpoint="/agent/tools/approvals/withdraw-draft",
            action_id="approval.request.withdraw",
            operation_key=_operation_key("withdraw-request", operation_payload),
            payload=operation_payload,
        )
    except Exception as exc:
        return _approval_failure(writer, "create_approval_withdraw_draft", tool_call_id, "审批撤回草稿生成失败，请稍后重试", exc)
    emit(writer, "draft.created", "📝 审批撤回草稿已生成，等待用户确认", toolName="create_approval_withdraw_draft", toolCallId=tool_call_id, result=result, draftId=result.get("draftId"), approvalId=result.get("approvalId"), presentation={"blockType": "card", "cardType": "approval_withdraw"})
    return tool_success({**result, "requires_confirmation": True}, {"blockType": "card", "cardType": "approval_withdraw"})


def _confirm_approval_request(approval_id: str, tool_call_id: str, withdrawal: bool) -> ToolResponse:
    context, error = load_approval_request_context(approval_id)
    if error or context is None:
        return error or tool_failure("APPROVAL_CONTEXT_INVALID", "当前审批申请确认上下文无效。")
    if str(context.approval.get("status") or "") == "REJECTED":
        cancel_request(context)
        return tool_success({"success": False, "cancelled": True, "message": "已取消操作"}, {"blockType": "card", "cardType": "approval_request_result"})
    if not can_execute_request(context):
        return tool_failure("APPROVAL_REQUEST_NOT_READY", "审批申请尚未完成确认或已失效，请重新生成草稿。")
    writer = get_stream_writer()
    draft_type = str(context.approval.get("draftType") or "")
    endpoint = "/agent/tools/approvals/withdraw-commit" if withdrawal else (
        "/agent/tools/approvals/generic/commit" if draft_type == "APPROVAL_REQUEST_GENERIC"
        else "/agent/tools/approvals/request-commit")
    operation_id = str(context.approval.get("operationId") or "").strip()
    runtime: OperationRuntime | None = None
    coordinator: EffectCommitCoordinator | None = None
    try:
        runtime = OperationRuntime.open_existing(operation_id, required=True)
        if runtime is None:
            raise CommitKernelError("OPERATION_RUNTIME_UNAVAILABLE", "审批申请缺少可用的 Operation Runtime")
        action_id = "approval.request.withdraw" if withdrawal else "approval.request.create"
        request_data = {
            "approvalId": approval_id,
            "operationId": operation_id,
            "draftType": draft_type,
            "endpoint": endpoint,
        }
        coordinator = EffectCommitCoordinator(
            runtime=runtime,
            expected_action_id=action_id,
            request_data=request_data,
            idempotency_key=f"{operation_id}:approval.commit:{approval_id}",
            reconcile_strategy="approval.request.commit.status",
            lease_owner=f"{current_agent_context().get('runId') or 'run'}:{tool_call_id or 'approval-commit'}",
            result_field="approvalResult",
        )
        start = coordinator.prepare()
        if start.reconciliation_required:
            result = coordinator.reconcile(
                _resolve_approval_result,
                pending_message="审批申请提交结果仍在核对中，请稍后重试",
            )
        elif start.recovered_result is not None:
            result = start.recovered_result
        else:
            result = java_post(endpoint, {
                "approvalId": approval_id,
                "operationId": operation_id,
                "idempotencyKey": f"{approval_id}:commit",
            })
            coordinator.settle_success(result)
    except ReconciliationPending as exc:
        return tool_failure("APPROVAL_RECONCILIATION_PENDING", str(exc), retryable=True)
    except CommitInProgress as exc:
        return tool_failure("APPROVAL_COMMIT_IN_PROGRESS", str(exc), retryable=True)
    except StoredFinalFailure as exc:
        return tool_failure(exc.code, exc.message, retryable=False)
    except CommitKernelError as exc:
        return tool_failure(exc.code, exc.message, retryable=False)
    except Exception as exc:
        if coordinator is not None:
            try:
                coordinator.record_failure(
                    exc,
                    unknown=_is_unknown_commit_error(exc),
                    code="APPROVAL_COMMIT_UNKNOWN" if _is_unknown_commit_error(exc) else "APPROVAL_COMMIT_FAILED",
                )
            except Exception:
                pass
        if _is_unknown_commit_error(exc):
            return tool_failure("APPROVAL_COMMIT_UNKNOWN", "审批申请提交结果未知，请稍后核对提交结果", details=str(exc), retryable=True)
        return _approval_failure(writer, "confirm_approval_withdraw_action" if withdrawal else "confirm_approval_request_action", tool_call_id, "审批操作未执行，请稍后重试", exc)
    finally:
        if runtime is not None:
            runtime.close()
    complete_request(context)
    message = "✅ 审批流程已撤回" if withdrawal else "✅ 审批申请已提交"
    emit(writer, "approval.approved", message, toolName="confirm_approval_withdraw_action" if withdrawal else "confirm_approval_request_action", toolCallId=tool_call_id, result=result, draftId=context.approval.get("draftId"), approvalId=approval_id)
    return tool_success(result, {"blockType": "card", "cardType": "approval_request_result"})


@tool
def confirm_approval_request_action(
    approval_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """在官方 HITL 恢复后提交请假或出差审批申请。"""
    bind_tool_call_id(tool_call_id)
    return _confirm_approval_request(approval_id, tool_call_id, False)


@tool
def confirm_approval_withdraw_action(
    approval_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """在官方 HITL 恢复后撤回本人审批流程。"""
    bind_tool_call_id(tool_call_id)
    return _confirm_approval_request(approval_id, tool_call_id, True)


__all__ = [
    "create_approval_request_draft",
    "create_generic_approval_request_draft",
    "create_approval_withdraw_draft",
    "confirm_approval_request_action",
    "confirm_approval_withdraw_action",
]
