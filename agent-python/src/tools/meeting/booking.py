from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ...domain.effect import EffectRecord
from ...runtime.effect_commit import (
    CommitInProgress,
    CommitKernelError,
    CommitStart,
    EffectCommitCoordinator,
    ReconciliationPending,
    StoredFinalFailure,
)
from ...runtime.operation_runtime import OperationRuntime
from ...runtime.operation_payload import merge_operation_payload
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
    get_meeting_booking_commit_status,
    mark_run_resumed,
    java_post,
    tool_failure,
    tool_success,
    update_meeting_draft_status,
)
from ...services.meeting_approval import (
    approval_status,
    complete_approval_resume,
    consume_approval_resume,
    consume_rejected_resume,
    load_confirmation_context,
)


_CommitKernelError = CommitKernelError
_CommitInProgress = CommitInProgress
_ReconciliationPending = ReconciliationPending
_StoredFinalFailure = StoredFinalFailure
_CommitStart = CommitStart


def _meeting_action_id(draft: dict[str, Any]) -> str:
    from ...runtime.operation_runtime import action_id_for
    return action_id_for("meeting", str(draft.get("operation") or "CREATE"))


def _is_unknown_commit_error(exc: Exception) -> bool:
    if isinstance(exc, (JavaFacadeConnectionError, JavaFacadeJsonDecodeError,
                        JavaFacadeResponseTypeError)):
        return True
    if isinstance(exc, JavaFacadeHttpError):
        return bool(exc.retryable)
    # An unclassified exception may happen after Java accepted the request.
    # Treat it as UNKNOWN until the durable business result says otherwise.
    return not isinstance(exc, JavaFacadeBusinessError)


def _settle_success(
    runtime: OperationRuntime,
    effect: EffectRecord,
    result: dict[str, Any],
) -> EffectRecord:
    coordinator = EffectCommitCoordinator(
        runtime=runtime,
        expected_action_id=runtime.operation.action_id,
        request_data=effect.request_data,
        idempotency_key=effect.idempotency_key,
        reconcile_strategy=effect.reconcile_strategy,
        lease_owner="meeting-success",
        result_field="bookingResult",
    )
    coordinator.effect = effect
    return coordinator.settle_success(result)


def _record_commit_failure(
    runtime: OperationRuntime,
    effect: EffectRecord | None,
    exc: Exception,
    *,
    unknown: bool,
    code: str,
) -> None:
    if effect is None:
        return
    coordinator = EffectCommitCoordinator(
        runtime=runtime,
        expected_action_id=runtime.operation.action_id,
        request_data=effect.request_data,
        idempotency_key=effect.idempotency_key,
        reconcile_strategy=effect.reconcile_strategy,
        lease_owner="meeting-failure",
        result_field="bookingResult",
    )
    coordinator.effect = effect
    coordinator.record_failure(exc, unknown=unknown, code=code)


def _reconcile_effect(
    runtime: OperationRuntime,
    effect: EffectRecord,
) -> dict[str, Any]:
    coordinator = EffectCommitCoordinator(
        runtime=runtime,
        expected_action_id=runtime.operation.action_id,
        request_data=effect.request_data,
        idempotency_key=effect.idempotency_key,
        reconcile_strategy=effect.reconcile_strategy,
        lease_owner="meeting-reconcile",
        result_field="bookingResult",
    )
    coordinator.effect = effect

    def resolve(current: EffectRecord) -> dict[str, Any] | None:
        request_data = current.request_data
        status_payload = get_meeting_booking_commit_status(
            str(request_data.get("draftId") or ""),
            str(request_data.get("approvalId") or ""),
            str(request_data.get("operationId") or runtime.operation_id) or None,
        )
        if isinstance(status_payload.get("data"), dict) and not status_payload.get("status"):
            status_payload = status_payload["data"]
        if str(status_payload.get("status") or "").upper() != "SUBMITTED":
            return None
        value = status_payload.get("result")
        return value if isinstance(value, dict) else {
            key: value for key, value in status_payload.items() if key != "status"
        }

    return coordinator.reconcile(resolve, pending_message="会议预约提交结果仍未知，请稍后重试")


def _start_commit_effect(
    draft: dict[str, Any],
    approval_id: str,
    tool_call_id: str,
) -> _CommitStart | None:
    operation_id = str(draft.get("operationId") or current_agent_context().get("operationId") or "").strip()
    if not operation_id:
        raise _CommitKernelError(
            "OPERATION_REQUIRED",
            "会议预约缺少 Operation 绑定，已拒绝旧版直接提交路径",
        )
    try:
        runtime = OperationRuntime.open_existing(operation_id, required=True)
    except Exception as exc:
        raise _CommitKernelError(
            "OPERATION_RUNTIME_UNAVAILABLE",
            "会议预约缺少可用的 Operation Runtime，已拒绝直接提交业务写操作",
        ) from exc
    if runtime is None:
        raise _CommitKernelError(
            "OPERATION_RUNTIME_UNAVAILABLE",
            "会议预约缺少可用的 Operation Runtime，已拒绝直接提交业务写操作",
        )
    expected_action = _meeting_action_id(draft)
    if runtime.operation.action_id != expected_action:
        runtime.close()
        raise _CommitKernelError(
            "OPERATION_ACTION_MISMATCH",
            f"会议预约 Operation actionId 不匹配，期望 {expected_action}",
        )
    try:
        operation = str(draft.get("operation") or "CREATE").upper()
        idempotency_key = f"{operation_id}:meeting.commit:{draft.get('draftId') or ''}"
        request_data = {
            "operationId": operation_id,
            "draftId": str(draft.get("draftId") or ""),
            "approvalId": approval_id,
            "operation": operation,
            "sourceBookingId": draft.get("sourceBookingId"),
        }
        coordinator = EffectCommitCoordinator(
            runtime=runtime,
            expected_action_id=expected_action,
            request_data=request_data,
            idempotency_key=idempotency_key,
            reconcile_strategy="meeting.booking.commit.status",
            lease_owner=f"{current_agent_context().get('runId') or 'run'}:{tool_call_id or 'meeting-commit'}",
            result_field="bookingResult",
        )
        start = coordinator.prepare()
        if start.reconciliation_required:
            result = _reconcile_effect(runtime, start.effect)
            return _CommitStart(runtime=runtime, effect=coordinator.effect or start.effect, recovered_result=result, settled=True)
        return start
    except Exception:
        runtime.close()
        raise


@tool
def confirm_meeting_booking(
    confirmation_token: str,
    draft_id: str,
    approval_id: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """提交预约草稿。

    Human-in-the-loop interrupt 由主 DeepAgents 图的官方
    HumanInTheLoopMiddleware 在 Tool 执行前负责。Tool 本身只接受
    APPROVED 的持久化审批并提交，PENDING 直达 handler 时必须拒绝，
    防止旧版运行时再次吞掉 GraphInterrupt。
    """
    bind_tool_call_id(tool_call_id)
    context, error = load_confirmation_context(confirmation_token, draft_id, approval_id)
    if error:
        return error
    assert context is not None
    runtime = context.runtime
    draft = context.draft
    status = approval_status(context)
    if not str(draft.get("operationId") or current_agent_context().get("operationId") or "").strip():
        return tool_failure(
            "OPERATION_REQUIRED",
            "会议预约缺少 Operation 绑定，旧版直接提交路径已关闭，请重新生成草稿。",
        )
    if status == "PENDING":
        return tool_failure("APPROVAL_REQUIRED", "当前预约仍等待用户确认，必须由主图 HumanInTheLoopMiddleware 中断")
    elif status == "REJECTED":
        return tool_failure("APPROVAL_REJECTED", "用户已取消会议室预约")
    elif status != "APPROVED":
        return tool_failure("APPROVAL_NOT_APPROVED", "当前审批尚未通过或已失效，不能提交预约")
    else:
        if not consume_approval_resume(context):
            return tool_failure(
                "APPROVAL_RESUME_REQUIRED",
                "当前审批不是本次 Human-in-the-loop 恢复结果，不能提交预约",
            )
        mark_run_resumed()
        # Keep RESUME_APPROVED until Java accepts the booking.  It is the
        # durable one-shot proof used to recover a transient transport failure;
        # Java's atomic draft claim remains the irreversible idempotency edge.
        emit(
            get_stream_writer(),
            "run.resumed",
            "已收到用户确认，正在继续处理",
            eventId=f"{runtime['runId']}:resumed:{approval_id}",
            approvalId=approval_id,
            draftId=draft_id,
            decision="approve",
        )

    writer = get_stream_writer()
    commit_runtime: OperationRuntime | None = None
    commit_effect: EffectRecord | None = None
    emit(writer, "tool_started", "📨 用户已确认，正在提交会议室预约……", toolName="confirm_meeting_booking", toolCallId=tool_call_id, approvalId=approval_id, draftId=draft_id)
    try:
        commit_start = _start_commit_effect(draft, approval_id, tool_call_id)
        commit_payload = {
            # Java must atomically claim the persisted PENDING draft.
            # The token is the draft id returned by the draft endpoint.
            "draftId": draft_id,
            "approvalId": approval_id,
        }
        operation_id = str(draft.get("operationId") or current_agent_context().get("operationId") or "").strip()
        if not operation_id or commit_start is None:
            raise _CommitKernelError(
                "OPERATION_REQUIRED",
                "会议预约缺少 Operation/Effect 绑定，已拒绝直接提交业务写操作",
            )
        commit_payload["operationId"] = operation_id
        commit_runtime = commit_start.runtime
        commit_effect = commit_start.effect
        if commit_start.recovered_result is not None:
            result = commit_start.recovered_result
        else:
            result = java_post("/agent/tools/meetings/book", commit_payload)
            assert commit_effect is not None
            _settle_success(commit_runtime, commit_effect, result)
    except _ReconciliationPending as exc:
        emit(writer, "tool_failed", "会议预约提交结果仍在核对中，请稍后重试", toolName="confirm_meeting_booking", toolCallId=tool_call_id, errorCode="BOOKING_RECONCILIATION_PENDING")
        return tool_failure(
            "BOOKING_RECONCILIATION_PENDING",
            str(exc),
            retryable=True,
            user_action="请稍后重试，系统会先查询会议预约提交结果",
        )
    except _CommitInProgress as exc:
        emit(writer, "tool_failed", "会议预约正在处理中，请稍后查看结果", toolName="confirm_meeting_booking", toolCallId=tool_call_id, errorCode="BOOKING_COMMIT_IN_PROGRESS")
        return tool_failure("BOOKING_COMMIT_IN_PROGRESS", str(exc), retryable=True)
    except _StoredFinalFailure as exc:
        consume_rejected_resume(context)
        emit(writer, "tool_failed", "会议室预约未被业务系统接受，请检查预约条件", toolName="confirm_meeting_booking", toolCallId=tool_call_id, errorCode=exc.code)
        return tool_failure(exc.code, exc.message, retryable=False)
    except _CommitKernelError as exc:
        emit(writer, "tool_failed", exc.message, toolName="confirm_meeting_booking", toolCallId=tool_call_id, errorCode=exc.code)
        return tool_failure(exc.code, exc.message, retryable=False)
    except JavaFacadeBusinessError as exc:
        if commit_runtime is not None:
            try:
                _record_commit_failure(
                    commit_runtime,
                    commit_effect,
                    exc,
                    unknown=False,
                    code="BOOKING_BUSINESS_REJECTED",
                )
            except Exception:
                pass
        if "MEETING_BOOKING_ALREADY_CANCELLED" in str(exc.message):
            consume_rejected_resume(context)
            user_message = "该会议预约已取消，不能再次修改或取消；请重新查询当前会议安排。"
            emit(writer, "tool_failed", user_message, toolName="confirm_meeting_booking", toolCallId=tool_call_id,
                 errorCode="MEETING_BOOKING_ALREADY_CANCELLED")
            return tool_failure("MEETING_BOOKING_ALREADY_CANCELLED", user_message)
        if str(exc.code).replace("_", "") == "1002010002" or "固定两小时" in exc.message:
            try:
                update_meeting_draft_status(draft_id, "CANCELLED")
            except Exception:
                pass
            consume_rejected_resume(context)
            merge_operation_payload({
                "meeting_booking_draft": None,
                "confirmation_token": None,
                "approvalId": None,
                "lastSubmissionError": {
                    "code": "MEETING_BOOKING_TIME_SLOT_INVALID",
                    "message": exc.message,
                },
            })
            emit(
                writer,
                "tool_failed",
                "预约时段不符合整点固定两小时规则，请调整时间后重试",
                toolName="confirm_meeting_booking",
                toolCallId=tool_call_id,
                errorCode="MEETING_BOOKING_TIME_SLOT_INVALID",
            )
            return tool_failure(
                "MEETING_BOOKING_TIME_SLOT_INVALID",
                "当前仅支持整点开始的固定两小时预约，请调整时间后重新生成草稿",
            )
        consume_rejected_resume(context)
        emit(writer, "tool_failed", "会议室预约提交失败，请检查业务条件", toolName="confirm_meeting_booking", toolCallId=tool_call_id, errorCode="BOOKING_BUSINESS_REJECTED")
        return tool_failure("BOOKING_BUSINESS_REJECTED", "会议室预约未被业务系统接受，请检查预约条件", details=str(exc))
    except Exception as exc:
        if commit_runtime is not None:
            unknown = _is_unknown_commit_error(exc)
            try:
                _record_commit_failure(
                    commit_runtime,
                    commit_effect,
                    exc,
                    unknown=unknown,
                    code="BOOKING_COMMIT_UNKNOWN" if unknown else "BOOKING_SUBMIT_FAILED",
                )
            except Exception:
                pass
            error_code = "BOOKING_COMMIT_UNKNOWN" if unknown else "BOOKING_SUBMIT_FAILED"
            message = "会议预约提交结果未知，请稍后重试并先核对提交结果" if unknown else "会议预约提交失败，请稍后重试"
            emit(writer, "tool_failed", message, toolName="confirm_meeting_booking", toolCallId=tool_call_id, errorCode=error_code)
            return tool_failure(error_code, message, details=str(exc), retryable=unknown)
        emit(writer, "tool_failed", "会议预约提交失败，请稍后重试", toolName="confirm_meeting_booking", toolCallId=tool_call_id, errorCode="BOOKING_SUBMIT_FAILED")
        return tool_failure("BOOKING_SUBMIT_FAILED", "会议预约提交失败，请稍后重试", details=str(exc))
    finally:
        if commit_runtime is not None:
            commit_runtime.close()
    operation = str(result.get("operation") or draft.get("operation") or "CREATE").upper()
    action_label = {"CREATE": "会议室预约", "UPDATE": "会议预约修改", "CANCEL": "会议预约取消"}.get(operation, "会议操作")
    emit(writer, "approval.approved", f"✅ 用户已确认，{action_label}提交成功", draftId=draft_id, approvalId=approval_id, toolName="confirm_meeting_booking", toolCallId=tool_call_id)
    # Consume the resume proof only after Java has accepted the booking.  If
    # the request failed before this point, the proof remains retryable.
    complete_approval_resume(context)
    merge_operation_payload({
        "booking_result": result,
        "confirmation_token": confirmation_token,
        "meeting_booking_draft": draft,
    })
    return tool_success(result)
