"""Trusted HITL boundary for durable personal-schedule drafts.

The schedule workflow intentionally has the same security semantics as the
meeting workflow: the model can prepare a draft, but only the official
HumanInTheLoop resume for that exact draft may reach the Java commit endpoint.
The Operation and Java Approval records are the durable sources of truth for
draft ownership, approval status, source version and final conflict
validation.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

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
from ..runtime.operation_runtime import OperationRuntime, action_id_for
from .approval_core import (
    ApprovalBinding, IDENTITY_FIELDS, has_trusted_approval_projection,
    identity_mismatch, resume_runtime,
)


_IDENTITY_FIELDS = IDENTITY_FIELDS
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersonalScheduleApprovalContext(ApprovalBinding):
    pass


def approval_status(context: PersonalScheduleApprovalContext) -> str:
    return str(context.approval.get("status") or "").upper()


def _operation_snapshot(operation_id: str):
    """Read the durable Operation without making Redis part of the proof."""
    runtime = OperationRuntime.open_existing(operation_id, required=True)
    if runtime is None:
        return None
    try:
        return runtime.operation
    finally:
        runtime.close()


def _operation_id(context: PersonalScheduleApprovalContext | None = None) -> str:
    if context is not None:
        return str(
            context.approval.get("operationId")
            or context.draft.get("operationId")
            or context.runtime.get("operationId")
            or ""
        ).strip()
    return str(current_agent_context().get("operationId") or "").strip()


def _sync_terminal_approval(approval: dict[str, Any]) -> ToolResponse | None:
    """Project the Java-owned terminal approval decision into Operation."""
    status = str(approval.get("status") or "").upper()
    if status not in {"REJECTED", "EXPIRED"}:
        return None
    operation_id = str(approval.get("operationId") or "").strip()
    if not operation_id:
        return None
    try:
        OperationRuntime.settle_approval(
            operation_id,
            status,
            approval_id=str(approval.get("approvalId") or "") or None,
            required=True,
        )
    except Exception as exc:
        return tool_failure(
            "OPERATION_STATE_SYNC_FAILED",
            "审批已结束，但 Agent 操作状态尚未同步，暂不继续恢复。",
            details=str(exc),
            retryable=True,
        )
    return None


def load_personal_schedule_confirmation(
    draft_id: str, approval_id: str,
) -> tuple[PersonalScheduleApprovalContext | None, ToolResponse | None]:
    """Load Java facts and bind them to the current tenant/user/thread/message.

    ``runId`` deliberately uses the stored origin run as its authority.  A
    LangGraph Server resume may have a new current run id, while it must still
    continue the draft produced by the original run.
    """
    if not approval_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "缺少日程草稿或确认 ID")
    try:
        approval = java_get(f"/agent/approvals/{approval_id}")
    except Exception as exc:
        return None, tool_failure("APPROVAL_NOT_FOUND", "日程确认记录不存在、已过期或无权访问", details=str(exc))
    if not isinstance(approval, dict):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "日程草稿或确认记录返回格式无效")
    draft_id = str(draft_id or approval.get("draftId") or "").strip()
    if not draft_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "日程确认记录缺少 draftId")
    sync_error = _sync_terminal_approval(approval)
    if sync_error is not None:
        return None, sync_error
    current_runtime = current_agent_context()
    approval_operation_id = str(approval.get("operationId") or "").strip()
    approval_snapshot = approval.get("draft") if isinstance(approval.get("draft"), dict) else {}
    draft_operation_id = str(approval_snapshot.get("operationId") or "").strip()
    if approval_operation_id and draft_operation_id and approval_operation_id != draft_operation_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "日程草稿与确认记录的 operationId 不一致")
    operation_id = approval_operation_id or draft_operation_id
    current_operation_id = str(current_runtime.get("operationId") or "").strip()
    if not operation_id:
        return None, tool_failure(
            "OPERATION_REQUIRED",
            "日程 Approval 缺少 Operation 绑定，请重新生成草稿。",
        )
    if operation_id:
        set_operation_context(operation_id)
        current_runtime = {**current_runtime, "operationId": operation_id}
    draft = None
    draft_error = None
    try:
        draft_response = java_get(f"/agent/tools/calendar/personal-schedules/drafts/{draft_id}")
        draft = draft_response.get("draft") if isinstance(draft_response, dict) else None
    except Exception as exc:
        draft_error = exc
    # Rejecting an approval cancels the live draft.  The approval endpoint
    # keeps the joined immutable draft JSON specifically so the resumed graph
    # can render its deterministic cancelled terminal message.
    if not isinstance(draft, dict) or not draft:
        snapshot = approval.get("draft")
        if str(approval.get("status") or "").upper() == "REJECTED" and isinstance(snapshot, dict) and snapshot:
            draft = dict(snapshot)
        else:
            return None, tool_failure("DRAFT_NOT_FOUND", "日程草稿不存在、已处理、已过期或无权访问", details=str(draft_error) if draft_error else None)
    # The personal-schedule draft endpoint returns the business payload, while
    # the approval record owns the request identity binding.  Current Java
    # responses therefore may omit tenant/user/thread/message from the nested
    # draft even though the top-level approval has them.  Fill only missing
    # fields from that same approval record; any conflicting value remains
    # visible to the strict checks below and is rejected.
    for field in ("approvalId", "draftId", *_IDENTITY_FIELDS, "runId", "threadId", "messageId", "operationId"):
        if not draft.get(field) and approval.get(field) is not None:
            draft[field] = approval[field]
    if str(draft.get("draftId") or draft_id) != str(draft_id):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "个人日程草稿与 draftId 不匹配")
    if str(draft.get("approvalId") or "") != str(approval_id) or str(approval.get("approvalId") or approval_id) != str(approval_id):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "个人日程草稿与确认记录不匹配")
    if str(approval.get("draftId") or "") != str(draft_id):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "确认记录与日程草稿不匹配")

    operation_id = str(approval.get("operationId") or draft.get("operationId") or "").strip()
    if operation_id:
        try:
            operation = _operation_snapshot(operation_id)
        except Exception as exc:
            return None, tool_failure(
                "APPROVAL_RUNTIME_UNAVAILABLE",
                "个人日程的持久化 Operation 不可用，请稍后重试。",
                details=str(exc), retryable=True,
            )
        if operation is None:
            return None, tool_failure("APPROVAL_RUNTIME_UNAVAILABLE", "个人日程缺少可用的 Operation Runtime。", retryable=True)
        expected_action = action_id_for("schedule", str(draft.get("operation") or "CREATE"))
        if operation.action_id != expected_action:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "个人日程审批绑定的 Action 不匹配")
        if operation.approval_id and operation.approval_id != approval_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "个人日程审批绑定了其他 Approval")
        current_origin_run_id = str(
            current_runtime.get("originRunId") or current_runtime.get("runId") or ""
        )
        approval_origin_run_id = str(approval.get("runId") or draft.get("runId") or "")
        if not current_origin_run_id or current_origin_run_id != approval_origin_run_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "日程审批不属于当前原始 runId")
        if current_operation_id and current_operation_id != operation_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "日程审批与当前 Operation 不匹配")
        runtime = {**current_runtime, "operationId": operation_id}
    else:
        return None, tool_failure("OPERATION_REQUIRED", "日程确认缺少 Operation 绑定，请重新生成草稿。")
    for record, label in ((draft, "日程草稿"), (approval, "确认记录")):
        mismatch = identity_mismatch(record, runtime)
        if mismatch:
            _LOGGER.warning(
                "personal schedule approval context mismatch approval=%s draft=%s status=%s field=%s runtime=%s record=%s",
                approval.get("approvalId"), draft.get("draftId"), approval.get("status"), mismatch,
                {key: runtime.get(key) for key in _IDENTITY_FIELDS},
                {key: record.get(key) for key in _IDENTITY_FIELDS},
            )
            return None, tool_failure(
                "APPROVAL_CONTEXT_INVALID",
                f"{label}不属于当前 tenant/user/thread/message",
                details={"field": mismatch},
            )
    origin_run_id = str(approval.get("runId") or draft.get("runId") or "")
    if not origin_run_id or str(draft.get("runId") or "") != origin_run_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "日程草稿缺少或不匹配原始 runId")
    runtime, resume_run_id = resume_runtime(runtime, origin_run_id)
    return PersonalScheduleApprovalContext(
        draft=draft,
        approval=approval,
        runtime={**runtime, "originRunId": origin_run_id, "resumeRunId": resume_run_id},
        origin_run_id=origin_run_id,
        resume_run_id=resume_run_id,
    ), None


def load_pending_personal_schedule_context() -> tuple[PersonalScheduleApprovalContext | None, ToolResponse | None]:
    """Return the sole draft permitted to create a new schedule ApprovalCard."""
    operation_id = _operation_id()
    if operation_id:
        try:
            operation = _operation_snapshot(operation_id)
        except Exception as exc:
            return None, tool_failure(
                "APPROVAL_RUNTIME_UNAVAILABLE",
                "当前个人日程的持久化操作不可用，请稍后重试。",
                details=str(exc),
                retryable=True,
            )
        if operation is None or operation.status != "WAITING_APPROVAL":
            return None, tool_failure("APPROVAL_TASK_NOT_PENDING", "当前没有等待确认的个人日程操作。")
        approval_id = str(operation.approval_id or "").strip()
        if not approval_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "个人日程 Operation 缺少 Approval 绑定")
        context, error = load_personal_schedule_confirmation("", approval_id)
        if error or context is None:
            return None, error
        if str(context.approval.get("operationId") or "").strip() != operation_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "个人日程审批与当前 Operation 不匹配")
        if approval_status(context) != "PENDING":
            return None, tool_failure("APPROVAL_NOT_PENDING", "个人日程确认已处理或已失效")
        return context, None

    return None, tool_failure(
        "OPERATION_REQUIRED",
        "个人日程确认卡缺少 Operation 绑定，旧版任务链不能继续执行，请重新生成草稿。",
    )


def consume_personal_schedule_resume(context: PersonalScheduleApprovalContext) -> bool:
    return (
        bool(_operation_id(context))
        and approval_status(context) == "APPROVED"
        and bool(str(context.approval.get("resumeIdempotencyKey") or "").strip())
    )


def complete_personal_schedule_resume(context: PersonalScheduleApprovalContext) -> bool:
    return bool(_operation_id(context))


def consume_rejected_personal_schedule_resume(context: PersonalScheduleApprovalContext) -> bool:
    return bool(_operation_id(context)) and approval_status(context) in {"REJECTED", "EXPIRED"}


def personal_schedule_confirmation_args(context: PersonalScheduleApprovalContext, args: dict[str, Any]) -> dict[str, Any]:
    draft, approval, runtime = context.draft, context.approval, context.runtime
    operation = str(draft.get("operation") or "").upper()
    title = str(draft.get("title") or "个人日程")
    fields = [{"label": "操作", "value": {"CREATE": "创建日程", "UPDATE": "修改日程", "CANCEL": "取消日程"}.get(operation, operation)}]
    if operation != "CANCEL":
        fields.extend([{"label": "标题", "value": title}, {"label": "时间", "value": f"{draft.get('startTime') or ''} - {draft.get('endTime') or ''}"}])
    draft_id, approval_id = str(draft.get("draftId") or ""), str(draft.get("approvalId") or "")
    card_copy = {
        "CREATE": ("创建个人日程", "确认创建", "取消操作"),
        "UPDATE": ("修改个人日程", "确认修改", "取消操作"),
        "CANCEL": ("取消个人日程", "确认取消", "保留原日程"),
    }
    operation_title, approve_label, reject_label = card_copy.get(operation, card_copy["CREATE"])
    return {**args, "confirmation_token": draft_id, "draft_id": draft_id, "approval_id": approval_id,
            "draftId": draft_id, "approvalId": approval_id, "action": "confirm_personal_schedule", "cardType": "personal_schedule",
            "title": operation_title, "name": title, "approveLabel": approve_label, "rejectLabel": reject_label,
            "status": approval_status(context), "allowedActions": ["approve", "reject"], "fields": fields, "draft": draft,
            "threadId": runtime.get("threadId"), "runId": runtime.get("runId"), "originRunId": context.origin_run_id,
            "resumeRunId": context.resume_run_id, "messageId": runtime.get("messageId")}


def personal_schedule_confirmation_description(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:
    args = tool_call.get("args") or {}
    context, error = load_personal_schedule_confirmation(str(args.get("draft_id") or args.get("draftId") or ""), str(args.get("approval_id") or args.get("approvalId") or ""))
    if error or context is None:
        return "当前个人日程确认上下文无效，系统不会创建确认卡片。"
    return json.dumps(personal_schedule_confirmation_args(context, dict(args)), ensure_ascii=False)


def prepare_personal_schedule_confirmation(request: Any) -> bool:
    """Persist the pause/resume proof immediately around official HITL."""
    args = (request.tool_call or {}).get("args") or {}
    context, error = load_personal_schedule_confirmation(str(args.get("draft_id") or args.get("draftId") or ""), str(args.get("approval_id") or args.get("approvalId") or ""))
    if error or context is None:
        return False
    if not has_trusted_approval_projection(
        request,
        action="confirm_personal_schedule",
        approval_id=context.draft.get("approvalId"),
        draft_id=context.draft.get("draftId"),
        origin_run_id=context.origin_run_id,
        message_id=context.runtime.get("messageId"),
    ):
        return False
    status = approval_status(context)
    operation_id = _operation_id(context)
    if not operation_id:
        return False
    if status == "APPROVED":
        if not str(context.approval.get("resumeIdempotencyKey") or "").strip():
            return False
        mark_run_resumed()
        return False
    if status in {"REJECTED", "EXPIRED"}:
        mark_run_resumed()
        return False
    if status != "PENDING" or str(context.runtime.get("originRunId") or context.origin_run_id) != context.origin_run_id:
        return False
    try:
        operation = _operation_snapshot(operation_id)
    except Exception:
        return False
    if operation is None or operation.status != "WAITING_APPROVAL":
        return False
    try:
        emit(
            getattr(request.runtime, "stream_writer", None),
            "run.paused",
            "等待用户确认个人日程",
            require_persist=True,
            eventId=f"{context.approval.get('approvalId')}:paused",
            approvalId=context.draft["approvalId"],
            draftId=context.draft["draftId"],
            operationId=operation_id,
            reason="approval_required",
        )
    except Exception:
        mark_run_resumed()
        return False
    mark_run_paused()
    return True
