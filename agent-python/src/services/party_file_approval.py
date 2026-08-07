"""Operation-bound HITL bridge for party-file CRUD.

Java owns the Approval and the party-file Draft.  The Python Operation owns
the orchestration lifecycle, while the official LangGraph interrupt is the
only pause boundary.  Redis working-memory facts are deliberately not part
of this proof: a replay is authorized by the Java Approval's
``resumeIdempotencyKey`` and the Operation's identity/status.
"""

from __future__ import annotations

import json
from copy import copy, deepcopy
from dataclasses import dataclass, replace
from hashlib import sha256
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from ..hitl.auto_confirm import ConfiguredApprovalProjectionMiddleware
from ..runtime.operation_runtime import OperationRuntime, action_id_for
from ..tools.common import (
    current_agent_context,
    emit,
    java_get,
    mark_run_paused,
    mark_run_resumed,
    set_operation_context,
    set_message_context,
    tool_failure,
)
from ..tools.common.http_client import JavaFacadeBusinessError, JavaFacadeHttpError
from ..services.approval_core import (
    ApprovalBinding,
    IDENTITY_FIELDS,
    PROJECTION_METADATA_KEY,
    approval_projection_metadata,
    has_trusted_approval_projection,
    identity_mismatch,
    resume_runtime,
)

_DRAFT_TOOLS = frozenset({
    "create_party_file_draft",
    "update_party_file_draft",
    "delete_party_file_draft",
})
_CONFIRM_TOOLS = {
    "CREATE": "confirm_create_party_file",
    "UPDATE": "confirm_update_party_file",
    "DELETE": "confirm_delete_party_file",
}


@dataclass(frozen=True)
class PartyFileApprovalContext(ApprovalBinding):
    """The exact Java Approval + Operation binding for one party-file write."""


def approval_status(context: PartyFileApprovalContext) -> str:
    return str(context.approval.get("status") or "").upper()


def _operation_id(draft: dict[str, Any], approval: dict[str, Any]) -> str:
    draft_id = str(draft.get("operationId") or "").strip()
    approval_id = str(approval.get("operationId") or "").strip()
    if not draft_id or not approval_id or draft_id != approval_id:
        return ""
    return draft_id


def _operation_snapshot(operation_id: str):
    runtime = OperationRuntime.open_existing(operation_id, required=True)
    if runtime is None:
        return None
    try:
        return runtime.operation
    finally:
        runtime.close()


def _sync_terminal_approval(approval: dict[str, Any]) -> Any | None:
    status = str(approval.get("status") or "").upper()
    operation_id = str(approval.get("operationId") or "").strip()
    if status not in {"REJECTED", "EXPIRED"} or not operation_id:
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
            "党务文件审批已结束，但 Agent 操作状态尚未同步，暂不继续恢复。",
            details=str(exc),
            retryable=True,
        )
    return None


def _is_not_found(exc: Exception | None) -> bool:
    if isinstance(exc, JavaFacadeHttpError):
        return exc.status_code == 404
    if isinstance(exc, JavaFacadeBusinessError):
        return str(exc.code) == "404"
    return False


def load_party_file_confirmation(
    draft_id: str, approval_id: str,
) -> tuple[PartyFileApprovalContext | None, Any | None]:
    """Load and verify the Java-owned draft, Approval and Operation facts."""

    if not draft_id or not approval_id:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "缺少党务文件草稿或确认 ID")
    try:
        approval = java_get(f"/agent/approvals/{approval_id}")
    except Exception as exc:
        return None, tool_failure(
            "APPROVAL_NOT_FOUND",
            "党务文件确认记录不存在、已过期或无权访问",
            details=str(exc),
        )
    if not isinstance(approval, dict):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "党务文件确认记录返回格式无效")

    draft_response = None
    draft_error = None
    try:
        draft_response = java_get(f"/agent/tools/party-files/drafts/{draft_id}")
    except Exception as exc:
        draft_error = exc

    draft = draft_response.get("draft") if isinstance(draft_response, dict) else None
    status = str(approval.get("status") or "").upper()
    if not isinstance(draft, dict) or not draft:
        snapshot = approval.get("draft")
        if status == "REJECTED" and isinstance(snapshot, dict) and snapshot and _is_not_found(draft_error):
            # The live draft is archived after rejection.  Bind a private copy
            # of the Approval's immutable snapshot so identity enrichment below
            # cannot mutate the Approval response or its nested payload.
            draft = deepcopy(snapshot)
        else:
            return None, tool_failure(
                "DRAFT_NOT_FOUND",
                "党务文件草稿不存在、已处理、已过期或无权访问",
                details=str(draft_error) if draft_error else None,
            )
    else:
        draft = deepcopy(draft)

    for field in ("approvalId", "draftId", *IDENTITY_FIELDS, "runId", "operationId"):
        if not draft.get(field) and approval.get(field) is not None:
            draft[field] = approval[field]

    operation_id = _operation_id(draft, approval)
    if (
        str(draft.get("draftId") or "") != str(draft_id)
        or str(draft.get("approvalId") or "") != str(approval_id)
        or str(approval.get("approvalId") or "") != str(approval_id)
        or str(approval.get("draftId") or "") != str(draft_id)
        or str(approval.get("draftType") or "") != "PARTY_FILE"
        or not operation_id
    ):
        return None, tool_failure(
            "APPROVAL_CONTEXT_INVALID",
            "党务文件草稿、确认记录与 Operation 绑定不一致",
        )

    runtime_now = dict(current_agent_context())
    if not str(runtime_now.get("messageId") or "").strip() and draft.get("messageId"):
        set_message_context(str(draft["messageId"]))
        runtime_now = dict(current_agent_context())
    set_operation_context(operation_id)

    if any(identity_mismatch(record, runtime_now) for record in (draft, approval)):
        return None, tool_failure(
            "APPROVAL_CONTEXT_INVALID",
            "党务文件审批不属于当前 tenant/user/thread/message",
        )
    origin = str(approval.get("runId") or draft.get("runId") or "").strip()
    if not origin or str(draft.get("runId") or "") != origin:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "党务文件审批缺少或不匹配原始 runId")
    if str(runtime_now.get("originRunId") or origin) != origin:
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "党务文件审批不属于当前原始 runId")

    try:
        operation = _operation_snapshot(operation_id)
    except Exception as exc:
        return None, tool_failure(
            "APPROVAL_RUNTIME_UNAVAILABLE",
            "党务文件持久化操作不可用，请稍后重试。",
            details=str(exc),
            retryable=True,
        )
    if operation is None or operation.action_id != action_id_for(
        "party_file", str(draft.get("operation") or "CREATE")
    ):
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "党务文件 Operation 与草稿操作不一致")

    terminal_error = _sync_terminal_approval(approval)
    if terminal_error is not None:
        return None, terminal_error
    status = str(approval.get("status") or "").upper()
    if status == "PENDING" and operation.status != "WAITING_APPROVAL":
        return None, tool_failure("APPROVAL_CONTEXT_INVALID", "党务文件 Operation 当前不在等待确认状态")

    runtime, resume_run_id = resume_runtime(runtime_now, origin)
    runtime["operationId"] = operation_id
    return PartyFileApprovalContext(
        draft=draft,
        approval=approval,
        runtime={**runtime, "originRunId": origin, "resumeRunId": resume_run_id},
        origin_run_id=origin,
        resume_run_id=resume_run_id,
    ), None


def _messages(request: Any) -> list[Any]:
    state = getattr(request, "state", None)
    if not isinstance(state, dict) and isinstance(request, dict):
        state = request.get("state")
    values = state.get("messages") if isinstance(state, dict) else []
    return list(values) if isinstance(values, (list, tuple)) else []


def _parse_result(message: Any) -> dict[str, Any] | None:
    name = getattr(message, "name", "")
    if name and name not in _DRAFT_TOOLS:
        return None
    content = message.content
    if not isinstance(content, str):
        return None
    try:
        value = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("ok") is False:
        return None
    data = value.get("data")
    if not isinstance(data, dict) or not data.get("approvalId") or not data.get("draftId"):
        return None
    if not name and not (data.get("requires_confirmation") or str(data.get("status") or "").upper() == "DRAFT_READY"):
        return None
    return data


def _fields(draft: dict[str, Any]) -> list[dict[str, str]]:
    operation = str(draft.get("operation") or "").upper()
    labels = [("操作", {"CREATE": "发布党务文件", "UPDATE": "更新党务文件", "DELETE": "删除党务文件"}.get(operation, "党务文件操作"))]
    presentation = draft.get("presentation") if isinstance(draft.get("presentation"), dict) else {}
    source_title = presentation.get("sourceTitle")
    if source_title:
        labels.append(("原文件", str(source_title)))
    title = draft.get("title")
    if title not in (None, ""):
        labels.append(("标题", str(title)))
    category = presentation.get("categoryName") or draft.get("categoryName")
    if category:
        labels.append(("分类", str(category)))
    publish_time = presentation.get("publishTime") or draft.get("publishTime")
    if publish_time:
        labels.append(("发布时间", str(publish_time)))
    for key, label in (("statusLabel", "状态"), ("storageTypeLabel", "存储方式"),
                       ("distributionLabel", "分发对象"), ("attachmentLabel", "附件")):
        if presentation.get(key):
            labels.append((label, str(presentation[key])))
    return [{"label": key, "value": value} for key, value in labels]


def _confirmation_args(data: dict[str, Any], runtime: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    draft = data.get("draft") if isinstance(data.get("draft"), dict) else {}
    operation = str(draft.get("operation") or "CREATE").upper()
    tool_name = _CONFIRM_TOOLS.get(operation, _CONFIRM_TOOLS["CREATE"])
    args = {
        "confirmation_token": str(data.get("draftId")),
        "draft_id": str(data.get("draftId")),
        "approval_id": str(data.get("approvalId")),
        "draftId": str(data.get("draftId")),
        "approvalId": str(data.get("approvalId")),
        "action": tool_name,
        "cardType": "party_file_approval",
        "title": {"CREATE": "确认发布党务文件", "UPDATE": "确认更新党务文件", "DELETE": "确认删除党务文件"}.get(operation, "确认党务文件操作"),
        "approveLabel": "确认提交",
        "rejectLabel": "取消操作",
        "status": "PENDING",
        "allowedActions": ["approve", "reject"],
        "fields": _fields(draft),
        "draft": draft,
        "threadId": runtime.get("threadId"),
        "runId": runtime.get("runId"),
        "originRunId": runtime.get("originRunId") or runtime.get("runId"),
        "messageId": runtime.get("messageId"),
        "operationId": draft.get("operationId"),
    }
    return tool_name, args


def _copy_message(message: AIMessage, calls: list[dict[str, Any]], proof: dict[str, str]) -> AIMessage:
    update = {"tool_calls": calls, "additional_kwargs": {**(message.additional_kwargs or {}), PROJECTION_METADATA_KEY: proof}}
    return message.model_copy(deep=True, update=update)


def _project(request: Any, response: Any) -> Any:
    messages = _messages(request)
    data = _parse_result(messages[-1]) if messages else None
    if not data:
        return response
    runtime = dict(current_agent_context())
    draft = data.get("draft") if isinstance(data.get("draft"), dict) else {}
    if not str(runtime.get("messageId") or "").strip() and draft.get("messageId"):
        set_message_context(str(draft["messageId"]))
        runtime = dict(current_agent_context())
    tool_name, args = _confirmation_args(data, runtime)
    approval_id, draft_id = args["approvalId"], args["draftId"]
    proof = approval_projection_metadata(
        action=tool_name,
        approval_id=approval_id,
        draft_id=draft_id,
        origin_run_id=runtime.get("originRunId") or runtime.get("runId"),
        message_id=runtime.get("messageId"),
    )
    result = getattr(response, "result", None)
    if not isinstance(result, list):
        return response
    target = next((i for i in range(len(result) - 1, -1, -1) if isinstance(result[i], AIMessage)), None)
    if target is None:
        return response
    call = {"name": tool_name, "args": args, "id": "auto-party-file-" + sha256((runtime.get("runId", "") + approval_id).encode()).hexdigest()[:24], "type": "tool_call"}
    updated = list(result)
    updated[target] = _copy_message(result[target], [call], proof)
    try:
        return replace(response, result=updated)
    except TypeError:
        value = copy(response)
        value.result = updated
        return value


class PartyFileApprovalAutoConfirmMiddleware(ConfiguredApprovalProjectionMiddleware):
    """Turn a successful party-file draft into one official confirmation call."""

    name = "PartyFileApprovalAutoConfirmMiddleware"

    def __init__(self) -> None:
        super().__init__(name=self.name, projector=_project)


def prepare_party_file_confirmation(request: Any) -> bool:
    """Pause only a PENDING Operation-bound ApprovalCard."""

    call = getattr(request, "tool_call", None) or {}
    args = call.get("args") if isinstance(call, dict) else {}
    args = args if isinstance(args, dict) else {}
    action = str(call.get("name") or "") if isinstance(call, dict) else ""
    if action not in _CONFIRM_TOOLS.values():
        return False
    approval_id = args.get("approval_id") or args.get("approvalId")
    draft_id = args.get("draft_id") or args.get("draftId")
    if not approval_id or not draft_id:
        return False
    context, error = load_party_file_confirmation(str(draft_id), str(approval_id))
    if context is None:
        return False
    if not has_trusted_approval_projection(
        request,
        action=action,
        approval_id=approval_id,
        draft_id=draft_id,
        origin_run_id=context.origin_run_id,
        message_id=context.runtime.get("messageId"),
    ):
        return False
    status = approval_status(context)
    if status == "PENDING":
        try:
            emit(
                getattr(getattr(request, "runtime", None), "stream_writer", None),
                "run.paused",
                "等待用户确认党务文件操作",
                require_persist=True,
                eventId=f"{context.approval.get('approvalId')}:paused",
                approvalId=context.approval.get("approvalId"),
                draftId=context.draft.get("draftId"),
                operationId=context.draft.get("operationId"),
                reason="approval_required",
            )
        except Exception:
            mark_run_resumed()
            return False
        mark_run_paused()
        return True
    if status == "APPROVED":
        # The Java resume idempotency key is written by the Gateway after the
        # user decision. It is the durable proof for a Server-created resume.
        if not str(context.approval.get("resumeIdempotencyKey") or "").strip():
            return False
        mark_run_resumed()
        return False
    if status in {"REJECTED", "EXPIRED"}:
        mark_run_resumed()
    return False


def consume_party_file_resume(context: PartyFileApprovalContext) -> bool:
    return approval_status(context) == "APPROVED" and bool(
        str(context.approval.get("resumeIdempotencyKey") or "").strip()
    )


__all__ = [
    "PartyFileApprovalAutoConfirmMiddleware",
    "PartyFileApprovalContext",
    "approval_status",
    "consume_party_file_resume",
    "load_party_file_confirmation",
    "prepare_party_file_confirmation",
]
