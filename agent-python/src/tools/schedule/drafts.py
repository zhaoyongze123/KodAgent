"""Personal schedule draft boundary.

These tools deliberately do not operate on MEETING_BOOKING calendar events.
The Java facade owns the durable approval, owner/version and final conflict
checks; Python only carries a structured draft through the Agent workflow.
"""

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
from ...runtime.operation_runtime import OperationRuntime, action_id_for
from ...runtime.operation_payload import merge_operation_payload
from ...services.personal_schedule_approval import (
    approval_status,
    complete_personal_schedule_resume,
    consume_personal_schedule_resume,
    load_personal_schedule_confirmation,
)
from ...workflows.personal_schedule.service import (
    create_personal_schedule_draft_service,
    get_personal_schedule_service,
)
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
    get_personal_schedule_commit_status,
    java_post,
    mark_run_resumed,
    tool_failure,
    tool_success,
)


def _schedule_action_id(draft: dict[str, Any]) -> str:
    return action_id_for("schedule", str(draft.get("operation") or "CREATE"))


def _is_unknown_commit_error(exc: Exception) -> bool:
    if isinstance(exc, (JavaFacadeConnectionError, JavaFacadeJsonDecodeError,
                        JavaFacadeResponseTypeError)):
        return True
    if isinstance(exc, JavaFacadeHttpError):
        return bool(exc.retryable)
    return not isinstance(exc, JavaFacadeBusinessError)


def _resolved_schedule_result(
    effect: EffectRecord, *, draft_id: str, approval_id: str, operation_id: str,
) -> dict[str, Any] | None:
    request = effect.request_data
    payload = get_personal_schedule_commit_status(
        str(request.get("draftId") or draft_id),
        str(request.get("approvalId") or approval_id),
        str(request.get("operationId") or operation_id) or None,
    )
    if isinstance(payload.get("data"), dict) and not payload.get("status"):
        payload = payload["data"]
    if str(payload.get("status") or "").upper() != "SUBMITTED":
        return None
    result = payload.get("result")
    if isinstance(result, dict):
        return result
    return {key: value for key, value in payload.items() if key != "status"}


@tool
def get_personal_schedule(
    schedule_id: int, tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """读取当前用户自己的 PERSONAL_SCHEDULE 详情；会议室预约不可用此工具修改。"""
    return get_personal_schedule_service(schedule_id, tool_call_id=tool_call_id)


@tool
def create_personal_schedule_draft(
    operation: str, title: str = "", start_time: str = "", end_time: str = "",
    source_schedule_id: int | None = None, location: str = "", description: str = "",
    attendee_user_ids: list[int] | None = None, other_participants: str = "",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """创建个人日程的 CREATE、UPDATE 或 CANCEL 草稿，用户确认前绝不写入日程。"""
    return create_personal_schedule_draft_service(
        operation=operation, title=title, start_time=start_time, end_time=end_time,
        source_schedule_id=source_schedule_id, location=location,
        description=description, attendee_user_ids=attendee_user_ids,
        other_participants=other_participants, tool_call_id=tool_call_id,
    )


@tool
def confirm_personal_schedule(
    confirmation_token: str, draft_id: str, approval_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """提交已获用户确认的个人日程草稿；Java 会再次校验确认、所有权、版本和冲突。"""
    bind_tool_call_id(tool_call_id)
    context, context_error = load_personal_schedule_confirmation(draft_id, approval_id)
    if context_error or context is None or confirmation_token != draft_id:
        return context_error or tool_failure("APPROVAL_CONTEXT_INVALID", "日程确认上下文不完整或不匹配")
    writer = get_stream_writer()
    status = approval_status(context)
    operation_id = str(context.draft.get("operationId") or current_agent_context().get("operationId") or "").strip()
    if not operation_id:
        return tool_failure(
            "OPERATION_REQUIRED",
            "个人日程缺少 Operation 绑定，旧版直接提交路径已关闭，请重新生成草稿。",
        )
    if status == "PENDING":
        return tool_failure("APPROVAL_REQUIRED", "当前日程仍等待用户确认，必须由主图 Human-in-the-loop 中断")
    if status == "REJECTED":
        return tool_failure("APPROVAL_REJECTED", "用户已取消个人日程操作")
    if status != "APPROVED":
        return tool_failure("APPROVAL_NOT_APPROVED", "个人日程审批尚未通过或已失效，不能提交")
    if not consume_personal_schedule_resume(context):
        return tool_failure("APPROVAL_RESUME_REQUIRED", "当前审批不是本次 Human-in-the-loop 恢复结果，不能提交日程")
    mark_run_resumed()
    emit(writer, "tool_started", "📨 用户已确认，正在提交个人日程……", toolName="confirm_personal_schedule", toolCallId=tool_call_id, draftId=draft_id, approvalId=approval_id)
    draft = context.draft
    operation_id = str(draft.get("operationId") or current_agent_context().get("operationId") or "").strip()
    if not operation_id:
        return tool_failure(
            "OPERATION_REQUIRED",
            "个人日程缺少 Operation 绑定，旧版直接提交路径已关闭，请重新生成草稿。",
        )
    coordinator: EffectCommitCoordinator | None = None
    try:
        commit_payload = {"draftId": draft_id, "approvalId": approval_id}
        runtime = OperationRuntime.open_existing(operation_id, required=True)
        if runtime is None:
            raise CommitKernelError(
                "OPERATION_RUNTIME_UNAVAILABLE",
                "个人日程缺少可用的 Operation Runtime，已拒绝直接提交业务写操作",
            )
        operation = str(draft.get("operation") or "CREATE").upper()
        coordinator = EffectCommitCoordinator(
            runtime=runtime,
            expected_action_id=_schedule_action_id(draft),
            request_data={
                "operationId": operation_id,
                "draftId": draft_id,
                "approvalId": approval_id,
                "operation": operation,
                "sourceScheduleId": draft.get("sourceScheduleId"),
            },
            idempotency_key=f"{operation_id}:schedule.commit:{draft_id}",
            reconcile_strategy="schedule.personal.commit.status",
            lease_owner=f"{current_agent_context().get('runId') or 'run'}:{tool_call_id or 'schedule-commit'}",
        )
        start = coordinator.prepare()
        if start.reconciliation_required:
            result = coordinator.reconcile(
                lambda effect: _resolved_schedule_result(
                    effect, draft_id=draft_id, approval_id=approval_id, operation_id=operation_id,
                ),
                pending_message="个人日程提交结果仍在核对中，请稍后重试",
            )
        elif start.recovered_result is not None:
            result = start.recovered_result
        else:
            commit_payload["operationId"] = operation_id
            result = java_post("/agent/tools/calendar/personal-schedules/commit", commit_payload)
            coordinator.settle_success(result)
    except ReconciliationPending as exc:
        emit(writer, "tool_failed", "个人日程提交结果仍在核对中，请稍后重试", toolName="confirm_personal_schedule", toolCallId=tool_call_id, errorCode="SCHEDULE_RECONCILIATION_PENDING")
        return tool_failure("SCHEDULE_RECONCILIATION_PENDING", str(exc), retryable=True)
    except CommitInProgress as exc:
        emit(writer, "tool_failed", "个人日程正在处理中，请稍后查看结果", toolName="confirm_personal_schedule", toolCallId=tool_call_id, errorCode="SCHEDULE_COMMIT_IN_PROGRESS")
        return tool_failure("SCHEDULE_COMMIT_IN_PROGRESS", str(exc), retryable=True)
    except StoredFinalFailure as exc:
        emit(writer, "tool_failed", "个人日程未被业务系统接受，请重新生成草稿", toolName="confirm_personal_schedule", toolCallId=tool_call_id, errorCode=exc.code)
        return tool_failure(exc.code, exc.message, retryable=False)
    except CommitKernelError as exc:
        emit(writer, "tool_failed", exc.message, toolName="confirm_personal_schedule", toolCallId=tool_call_id, errorCode=exc.code)
        return tool_failure(exc.code, exc.message, retryable=False)
    except JavaFacadeBusinessError as exc:
        if coordinator is not None:
            try:
                coordinator.record_failure(exc, unknown=False, code="SCHEDULE_BUSINESS_REJECTED")
            except Exception:
                pass
        message = str(exc.message)
        if "PERSONAL_SCHEDULE_VERSION_CONFLICT" in message:
            code, user_message = "PERSONAL_SCHEDULE_VERSION_CONFLICT", "原日程已被其他操作修改，请重新读取后生成新的草稿。"
        elif "PERSONAL_SCHEDULE_CONFLICT" in message:
            code, user_message = "PERSONAL_SCHEDULE_CONFLICT", "当前时段与已有日程或会议冲突，请调整时间后重新确认。"
        elif "AGENT_APPROVAL_REQUIRED" in message:
            code, user_message = "APPROVAL_REQUIRED", "个人日程仍需要有效的确认，不能提交。"
        else:
            code, user_message = "SCHEDULE_BUSINESS_REJECTED", "个人日程未被业务系统接受，请检查日程条件。"
        merge_operation_payload({
            "lastSubmissionError": {"code": code, "message": message},
        })
        emit(writer, "tool_failed", user_message, toolName="confirm_personal_schedule", toolCallId=tool_call_id, errorCode=code)
        return tool_failure(code, user_message, details=message)
    except Exception as exc:
        if coordinator is not None:
            unknown = _is_unknown_commit_error(exc)
            try:
                coordinator.record_failure(
                    exc,
                    unknown=unknown,
                    code="SCHEDULE_COMMIT_UNKNOWN" if unknown else "SCHEDULE_SUBMIT_FAILED",
                )
            except Exception:
                pass
            error_code = "SCHEDULE_COMMIT_UNKNOWN" if unknown else "SCHEDULE_SUBMIT_FAILED"
            message = "个人日程提交结果未知，请稍后重试并先核对提交结果" if unknown else "个人日程提交失败，请稍后重试"
            emit(writer, "tool_failed", message, toolName="confirm_personal_schedule", toolCallId=tool_call_id, errorCode=error_code)
            return tool_failure(error_code, message, details=str(exc), retryable=unknown)
        emit(writer, "tool_failed", "个人日程提交失败", toolName="confirm_personal_schedule", toolCallId=tool_call_id, errorCode="SCHEDULE_COMMIT_FAILED")
        return tool_failure("SCHEDULE_COMMIT_FAILED", "个人日程未被业务系统接受，请检查冲突或最新状态", details=str(exc))
    finally:
        if coordinator is not None:
            coordinator.runtime.close()
    complete_personal_schedule_resume(context)
    merge_operation_payload({
        "personal_schedule_result": result,
        "personal_schedule_draft": draft,
    })
    emit(writer, "approval.approved", "✅ 用户已确认，个人日程已提交", toolName="confirm_personal_schedule", toolCallId=tool_call_id, draftId=draft_id, approvalId=approval_id)
    return tool_success(result)
