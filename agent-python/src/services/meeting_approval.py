"""Trusted approval context used by the official DeepAgents HITL boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..tools.common import (
    ToolResponse,
    current_agent_context,
    emit,
    get_meeting_approval,
    get_meeting_draft,
    mark_run_paused,
    mark_run_resumed,
    set_message_context,
    set_operation_context,
    tool_failure,
)
from ..runtime.operation_runtime import OperationRuntime, action_id_for
from ..orchestration.delegated_receipt import (
    DelegatedMeetingDraftReceipt,
    parse_meeting_draft_receipt,
)
from .approval_core import (
    ApprovalBinding, IDENTITY_FIELDS, has_trusted_approval_projection,
    identity_mismatch, resume_runtime,
)


_IDENTITY_FIELDS = IDENTITY_FIELDS


@dataclass(frozen=True)
class PendingApprovalContext(ApprovalBinding):
    """Canonical meeting approval binding shared by model and HITL layers.

    ``draft`` and ``approval`` are always loaded from the Java business
    boundary.  The operation binding is checked before this object is
    returned; no thread-wide task projection participates in the decision.
    """

    draft_from_approval_snapshot: bool = False


ConfirmationContext = PendingApprovalContext


def _approval_draft_snapshot(approval: dict[str, Any]) -> dict[str, Any] | None:
    """Return the immutable draft snapshot carried by a settled approval.

    Rejecting or expiring an approval cancels the live draft row.  The approval
    endpoint still returns the joined ``draft`` JSON, which is the only valid
    read source for a settled continuation.  Never use this fallback to start
    an approved submission: that path must read and atomically claim the live
    PENDING draft through Java.
    """
    for key in ("draft", "draftSnapshot", "draft_snapshot", "card"):
        value = approval.get(key)
        if isinstance(value, dict) and value:
            return dict(value)
    return None


def _sync_terminal_approval(approval: dict[str, Any]) -> ToolResponse | None:
    """Project a Java Approval terminal fact into the Python Operation."""

    status = str(approval.get("status") or "").upper()
    if status not in {"REJECTED", "EXPIRED"}:
        return None
    operation_id = str(approval.get("operationId") or "").strip()
    # Old approvals predate Operation binding.  They remain readable through
    # the compatibility path, but cannot claim to have synchronized a runtime
    # aggregate that does not exist.
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


def load_confirmation_context(
    confirmation_token: str,
    draft_id: str,
    approval_id: str,
) -> tuple[ConfirmationContext | None, ToolResponse | None]:
    """Load and strictly bind a draft/approval to the current execution."""
    if not confirmation_token or confirmation_token != draft_id or not approval_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批上下文缺少或不匹配 draftId、approvalId")

    current_runtime = current_agent_context()
    try:
        approval = get_meeting_approval(approval_id)
    except Exception as exc:
        return None, tool_failure("APPROVAL_NOT_FOUND", "审批记录不存在、已过期或无权访问", details=str(exc))
    if not isinstance(approval, dict):
        return None, tool_failure("DRAFT_NOT_FOUND", "预约草稿不存在、已过期或无权访问")

    status = str(approval.get("status") or "").upper()
    sync_error = _sync_terminal_approval(approval)
    if sync_error is not None:
        return None, sync_error
    draft_from_snapshot = False
    draft = None
    draft_error = None
    try:
        draft_response = get_meeting_draft(draft_id)
        draft = draft_response.get("draft") if isinstance(draft_response, dict) else None
    except Exception as exc:
        draft_error = exc
    if not isinstance(draft, dict) or not draft:
        # A rejected approval always needs its immutable snapshot because the
        # live draft is cancelled.  An approved approval may also need it on a
        # recovery run after Java has already marked the draft SUBMITTED; the
        # Effect/commit-status query remains the authority for that path.
        if status in {"APPROVED", "REJECTED", "EXPIRED"}:
            draft = _approval_draft_snapshot(approval)
            draft_from_snapshot = draft is not None
        if not draft:
            return None, tool_failure(
                "DRAFT_NOT_FOUND", "预约草稿不存在、已过期或无权访问",
                details=str(draft_error) if draft_error else None,
            )

    origin_run_id = str(approval.get("runId") or draft.get("runId") or "")
    if not origin_run_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批记录缺少原始 runId")

    # The approval record is the canonical origin binding.  A cancelled draft
    # snapshot may omit fields, so fill only missing values from the approval;
    # conflicting values are rejected below.
    for field in ("approvalId", "draftId", *_IDENTITY_FIELDS, "runId", "threadId", "messageId"):
        if not draft.get(field) and approval.get(field) is not None:
            draft[field] = approval[field]

    pairs = (
        (draft, "预约草稿"),
        (approval, "审批记录"),
    )
    for record, label in pairs:
        mismatch = identity_mismatch(record, current_runtime)
        if mismatch:
            return None, tool_failure(
                "APPROVAL_CONTEXT_INVALID",
                f"{label}不属于当前 tenant/user/thread/run/message",
                details={"field": mismatch},
            )

    for record, label in pairs:
        if str(record.get("runId") or "") != origin_run_id:
            return None, tool_failure(
                "APPROVAL_CONTEXT_INVALID",
                f"{label}不属于审批原始 runId",
                details={"field": "originRunId"},
            )

    if str(draft.get("draftId") or draft_id) != str(draft_id):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "预约草稿与 draftId 不匹配")
    if str(draft.get("approvalId") or "") != str(approval_id):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "预约草稿与 approvalId 不匹配")
    if str(approval.get("approvalId") or approval_id) != str(approval_id):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批记录与 approvalId 不匹配")
    if str(approval.get("draftId") or "") != str(draft_id):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "审批记录与 draftId 不匹配")
    operation_id = str(
        approval.get("operationId") or draft.get("operationId") or ""
    ).strip()
    if not operation_id:
        return None, tool_failure(
            "OPERATION_REQUIRED",
            "会议预约审批缺少 Operation 绑定，请重新生成预约草稿。",
        )
    current_operation_id = str(current_runtime.get("operationId") or "").strip()
    if current_operation_id and current_operation_id != operation_id:
        return None, tool_failure(
            "APPROVAL_CONTEXT_INVALID",
            "会议预约审批与当前 Operation 不匹配",
        )
    try:
        operation_runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception as exc:
        return None, tool_failure(
            "APPROVAL_RUNTIME_UNAVAILABLE",
            "会议预约的持久化 Operation 不可用，请稍后重试。",
            details=str(exc),
            retryable=True,
        )
    if operation_runtime is None:
        return None, tool_failure(
            "APPROVAL_RUNTIME_UNAVAILABLE",
            "会议预约缺少可用的 Operation Runtime，请重新发起预约。",
            retryable=True,
        )
    try:
        operation = operation_runtime.operation
        expected_action = action_id_for("meeting", str(draft.get("operation") or "CREATE"))
        if operation.action_id != expected_action:
            return None, tool_failure(
                "APPROVAL_CONTEXT_INVALID",
                "会议预约审批绑定的 Action 不匹配。",
            )
        if operation.approval_id and operation.approval_id != approval_id:
            return None, tool_failure(
                "APPROVAL_CONTEXT_INVALID",
                "会议预约审批绑定了其他 Approval。",
            )
        if operation.origin_run_id != origin_run_id:
            return None, tool_failure(
                "APPROVAL_CONTEXT_INVALID",
                "会议预约审批不属于原始运行。",
            )
    finally:
        operation_runtime.close()
    draft["operationId"] = operation_id
    approval["operationId"] = operation_id
    set_operation_context(operation_id)
    # ``runId`` remains the currently executing LangGraph run for event audit;
    # business records use this explicit originRunId instead.
    runtime, resume_run_id = resume_runtime(current_runtime, origin_run_id)
    return PendingApprovalContext(
        draft=draft,
        approval=approval,
        runtime=runtime,
        origin_run_id=origin_run_id,
        resume_run_id=resume_run_id,
        draft_from_approval_snapshot=draft_from_snapshot,
    ), None


def _operation_id_from_draft_request(request: Any | None) -> str:
    """Read the operation binding from the immediately preceding draft result.

    The workflow binds ``operationId`` only while its Tool call is executing.
    The following model call is a new Runnable context, so the ContextVar may
    not contain that value even though the checkpoint still has the structured
    ``DRAFT_READY`` ToolMessage.  This is a one-frame recovery: it accepts no
    text or historical message and therefore cannot reopen an old draft.
    """
    state = getattr(request, "state", None) if request is not None else None
    if not isinstance(state, dict):
        return ""
    messages = state.get("messages") or []
    if not messages:
        return ""
    message = messages[-1]
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    if not isinstance(content, str):
        return ""
    try:
        envelope = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return ""
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict) or str(data.get("status") or "").upper() != "DRAFT_READY":
        return ""
    for record in (data, data.get("facts")):
        if not isinstance(record, dict):
            continue
        operation_id = str(record.get("operationId") or record.get("operation_id") or "").strip()
        if operation_id:
            return operation_id
    return ""


def _message_id_from_draft_request(request: Any | None) -> str:
    """Restore the trusted user-turn binding from checkpoint state.

    LangGraph's model middleware can receive a Runnable context without the
    Gateway's optional ``messageId`` metadata.  The root middleware stores the
    authenticated current user message in state before any business tool is
    called; accepting only that code-owned, trusted binding keeps this from
    becoming a free-form message or historical-thread fallback.
    """
    state = getattr(request, "state", None) if request is not None else None
    if not isinstance(state, dict):
        return ""
    binding = state.get("current_user_message")
    if not isinstance(binding, dict) or binding.get("trusted") is not True:
        return ""
    if binding.get("source") != "current_human_message":
        return ""
    return str(binding.get("messageId") or binding.get("message_id") or "").strip()


def _delegated_draft_receipt_from_request(request: Any | None) -> DelegatedMeetingDraftReceipt | None:
    """Read only the immediate, already-validated task receipt payload.

    Caller-side projection verifies the parent task call and subagent type.
    This loader only decodes its code-owned payload so it can bind the
    durable Operation without a historical database search.
    """
    state = getattr(request, "state", None) if request is not None else None
    if not isinstance(state, dict):
        return None
    messages = state.get("messages") or []
    if not messages:
        return None
    message = messages[-1]
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    return parse_meeting_draft_receipt(content)


def load_pending_approval_context(
    request: Any | None = None,
) -> tuple[PendingApprovalContext | None, ToolResponse | None]:
    """Resolve the one current draft that is allowed to create an HITL card.

    Operation supplies the current process binding and Java supplies the
    durable business records.  A settled approval is deliberately rejected
    here so a later model call cannot resurrect an old card.
    """
    runtime_context = current_agent_context()
    delegated_receipt = _delegated_draft_receipt_from_request(request)
    checkpoint_message_id = _message_id_from_draft_request(request)
    if checkpoint_message_id and checkpoint_message_id != str(runtime_context.get("messageId") or "").strip():
        # The immediate draft frame is the only place where the checkpoint's
        # code-owned current-user binding may repair a missing or stale
        # Runnable ContextVar.  A later free-form message never reaches this
        # branch because ``is_draft_projection_turn`` rejects it upstream.
        set_message_context(checkpoint_message_id)
        runtime_context = current_agent_context()
    # The root task boundary may run in a fresh Runnable ContextVar.  Its
    # code-produced receipt is the source of the operation binding; do not
    # substitute a matching pending row from a database query.
    operation_id = delegated_receipt.operation_id if delegated_receipt else str(runtime_context.get("operationId") or "").strip()
    if not operation_id:
        operation_id = _operation_id_from_draft_request(request)
        if operation_id:
            set_operation_context(operation_id)
    if not operation_id:
        return None, tool_failure(
            "OPERATION_REQUIRED",
            "会议预约确认卡缺少 Operation 绑定，旧版任务链不能继续执行，请重新发起预约。",
        )
    try:
        runtime = OperationRuntime.open_existing(operation_id, required=True)
        if runtime is None or runtime.operation.status != "WAITING_APPROVAL":
            if runtime is not None:
                runtime.close()
            return None, tool_failure("APPROVAL_TASK_NOT_PENDING", "当前没有等待确认的会议室预约操作。")
        approval_id = str(runtime.operation.approval_id or "").strip()
        runtime.close()
        if not approval_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "会议预约 Operation 缺少 Approval 绑定")
        if delegated_receipt and approval_id != delegated_receipt.approval_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "会议预约回执与 Operation 的 Approval 不匹配")
        approval = get_meeting_approval(approval_id)
        draft_id = str(approval.get("draftId") or "").strip() if isinstance(approval, dict) else ""
        if not draft_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "会议预约 Approval 缺少 Draft 绑定")
        if delegated_receipt and draft_id != delegated_receipt.draft_id:
            return None, tool_failure("APPROVAL_CONTEXT_INVALID", "会议预约回执与 Approval 的 Draft 不匹配")
        context, error = load_confirmation_context(draft_id, draft_id, approval_id)
        if error or context is None:
            return None, error
        if approval_status(context) != "PENDING":
            return None, tool_failure("APPROVAL_NOT_PENDING", "会议室预约审批已处理或已失效")
        return context, None
    except Exception as exc:
        return None, tool_failure(
            "APPROVAL_TASK_UNAVAILABLE",
            "无法读取当前会议室预约任务",
            details=str(exc),
        )


def approval_status(context: ConfirmationContext) -> str:
    return str(context.approval.get("status") or "").upper()


def consume_approval_resume(context: ConfirmationContext) -> bool:
    """Validate Java's one-shot approval decision before the Effect commit."""
    operation_id = str(
        context.approval.get("operationId") or context.draft.get("operationId") or ""
    ).strip()
    if not operation_id or approval_status(context) != "APPROVED":
        return False
    if not str(context.approval.get("resumeIdempotencyKey") or "").strip():
        return False
    try:
        runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception:
        return False
    if runtime is None:
        return False
    try:
        return runtime.operation.status in {"WAITING_APPROVAL", "COMMITTING", "UNKNOWN", "SUCCEEDED"}
    finally:
        runtime.close()


def complete_approval_resume(context: ConfirmationContext) -> bool:
    """The Java approval/effect records are already the durable resume proof."""
    return bool(
        str(context.approval.get("operationId") or context.draft.get("operationId") or "").strip()
    )


def consume_rejected_resume(context: ConfirmationContext) -> bool:
    """A rejected/expired Java Approval needs no second Python marker."""
    return approval_status(context) in {"REJECTED", "EXPIRED"} and bool(
        str(context.approval.get("operationId") or context.draft.get("operationId") or "").strip()
    )


def confirmation_card_args(context: ConfirmationContext, original_args: dict[str, Any]) -> dict[str, Any]:
    """Build the trusted args shown in the official HITL card."""
    draft = context.draft
    draft_id = str(draft.get("draftId"))
    approval_id = str(draft.get("approvalId"))
    token = draft_id
    attendee_names = draft.get("attendeeUserNames")
    attendee_ids = draft.get("attendeeUserIds")
    if isinstance(attendee_names, (list, tuple)) and attendee_names:
        attendees = ", ".join(str(item) for item in attendee_names if str(item).strip())
    elif isinstance(attendee_ids, (list, tuple)) and attendee_ids:
        attendees = f"已关联参会人（{len(attendee_ids)} 人）"
    else:
        attendees = "未提供"
    operation = str(draft.get("operation") or "CREATE").upper()
    if operation == "CANCEL":
        fields = [
            {"label": "主题", "value": str(draft.get("subject") or draft.get("sourceSubject") or "")},
            {"label": "原时间", "value": f"{draft.get('startTime', '')} - {draft.get('endTime', '')}"},
            {"label": "取消原因", "value": str(draft.get("cancelReason") or "用户取消会议预约")},
        ]
    else:
        fields = [
            {"label": "主题", "value": str(draft.get("subject") or "")},
            {"label": "会议室", "value": str(draft.get("meetingRoomName") or ("已关联会议室" if draft.get("meetingRoomId") else "未指定"))},
            {"label": "时间", "value": f"{draft.get('startTime', '')} - {draft.get('endTime', '')}"},
            {"label": "参会人", "value": attendees},
        ]
    title = {"CREATE": "预约会议室", "UPDATE": "修改会议预约", "CANCEL": "取消会议预约"}.get(operation, "会议预约")
    return {
        **original_args,
        "confirmation_token": token,
        "draft_id": draft_id,
        "approval_id": approval_id,
        "draftId": draft_id,
        "approvalId": approval_id,
        "action": "confirm_meeting_booking",
        "cardType": "meeting_booking",
        "title": title,
        "name": str(draft.get("subject") or draft.get("sourceSubject") or title),
        "approveLabel": "确认取消" if operation == "CANCEL" else "确认提交",
        "rejectLabel": "保留原预约" if operation == "CANCEL" else "取消操作",
        "status": approval_status(context),
        "allowedActions": ["approve", "reject"],
        "fields": fields,
        "draft": draft,
        "threadId": context.runtime.get("threadId"),
        "runId": context.runtime.get("runId"),
        "originRunId": context.origin_run_id,
        "resumeRunId": context.resume_run_id,
        "messageId": context.runtime.get("messageId"),
    }


def confirmation_description(tool_call: dict[str, Any], state: Any, runtime: Any) -> str:
    args = tool_call.get("args") or {}
    context, error = load_confirmation_context(
        str(args.get("confirmation_token") or ""),
        str(args.get("draft_id") or args.get("draftId") or ""),
        str(args.get("approval_id") or args.get("approvalId") or ""),
    )
    if error or context is None:
        return "当前预约审批上下文无效，系统不会创建审批卡片。"
    return json.dumps(
        {
            "title": "预约会议室",
            "approvalId": context.draft.get("approvalId"),
            "draftId": context.draft.get("draftId"),
            "confirmation_token": context.draft.get("draftId"),
            "draft": context.draft,
        },
        ensure_ascii=False,
    )


def prepare_confirmation_interrupt(request: Any) -> bool:
    """Validate the Java Approval and Operation gate immediately before interrupt."""
    tool_call = request.tool_call
    args = tool_call.get("args") or {}
    context, error = load_confirmation_context(
        str(args.get("confirmation_token") or ""),
        str(args.get("draft_id") or args.get("draftId") or ""),
        str(args.get("approval_id") or args.get("approvalId") or ""),
    )
    if error or context is None:
        return False
    if not has_trusted_approval_projection(
        request,
        action="confirm_meeting_booking",
        approval_id=context.draft.get("approvalId"),
        draft_id=context.draft.get("draftId"),
        origin_run_id=context.origin_run_id,
        message_id=context.runtime.get("messageId"),
    ):
        return False
    status = approval_status(context)
    operation_id = str(
        context.approval.get("operationId") or context.draft.get("operationId") or ""
    ).strip()
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
    if status != "PENDING":
        return False
    try:
        operation_runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception:
        return False
    if operation_runtime is None:
        return False
    try:
        if operation_runtime.operation.status != "WAITING_APPROVAL":
            return False
    finally:
        operation_runtime.close()
    emit(
        getattr(request.runtime, "stream_writer", None),
        "run.paused",
        "等待用户确认会议室预约",
        require_persist=True,
        eventId=f"{context.origin_run_id}:paused:{context.draft['approvalId']}",
        approvalId=context.draft["approvalId"],
        draftId=context.draft["draftId"],
        operationId=operation_id,
        reason="approval_required",
    )
    mark_run_paused()
    return True
