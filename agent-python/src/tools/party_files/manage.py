"""Confirmed write boundary for party-file CRUD; attachments are existing IDs only."""
from datetime import datetime
from typing import Annotated
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
from ..common import (
    AGENT_TIMEZONE,
    JavaFacadeBusinessError,
    JavaFacadeConnectionError,
    JavaFacadeHttpError,
    JavaFacadeJsonDecodeError,
    JavaFacadeResponseTypeError,
    ToolResponse,
    bind_tool_call_id,
    current_agent_context,
    emit,
    get_party_file_commit_status,
    java_get,
    java_get_list,
    java_post,
    mark_run_resumed,
    tool_failure,
    tool_success,
)
from ...services.party_file_service import (
    canonical_category_name,
    normalize_targets,
    resolve_category_id,
)


def _map_party_file_write_error(exc: Exception) -> tuple[str, str]:
    """Translate OA validation errors into stable Agent-facing contracts.

    The Java facade is the source of truth for validation, but its human
    messages are not a safe protocol for the model or the UI.  Keep the
    original exception in ``details`` for diagnostics while exposing a stable
    code/message pair that can drive clarification and presentation.
    """
    if isinstance(exc, JavaFacadeBusinessError):
        message = str(exc.message or "")
        if "categoryId" in message or "分类" in message:
            return (
                "PARTY_FILE_CATEGORY_REQUIRED",
                "党务文件缺少文件类别，请补充 category_name（例如：通知公告、制度规范、组织建设）。",
            )
        if "publishTime" in message or "发布时间" in message:
            return "PARTY_FILE_PUBLISH_TIME_REQUIRED", "党务文件缺少发布时间，请补充 publish_time。"
        if "targets" in message or "分发对象" in message:
            return "PARTY_FILE_TARGET_REQUIRED", "党务文件缺少分发对象，请指定接收人、部门或选择全员。"
        if "无权" in message or str(exc.code) in {"401", "403"}:
            return "PARTY_FILE_PERMISSION_DENIED", "当前用户没有执行该党务文件操作的权限。"
        if "版本" in message or "VERSION_CONFLICT" in message:
            return "PARTY_FILE_VERSION_CONFLICT", "党务文件已被其他操作修改，请重新读取后再生成草稿。"
    return "PARTY_FILE_DRAFT_SAVE_FAILED", "党务文件草稿保存失败，请检查输入或稍后重试。"


def _party_file_action_id(draft: dict) -> str:
    return action_id_for("party_file", str(draft.get("operation") or "CREATE"))


def _is_unknown_commit_error(exc: Exception) -> bool:
    if isinstance(exc, (JavaFacadeConnectionError, JavaFacadeJsonDecodeError,
                        JavaFacadeResponseTypeError)):
        return True
    if isinstance(exc, JavaFacadeHttpError):
        return bool(exc.retryable)
    return not isinstance(exc, JavaFacadeBusinessError)


def _resolved_party_file_result(
    effect: EffectRecord, *, draft_id: str, approval_id: str, operation_id: str,
) -> dict | None:
    request = effect.request_data
    payload = get_party_file_commit_status(
        str(request.get("draftId") or draft_id),
        str(request.get("approvalId") or approval_id),
        str(request.get("operationId") or operation_id),
    )
    if isinstance(payload.get("data"), dict) and not payload.get("status"):
        payload = payload["data"]
    if str(payload.get("status") or "").upper() != "SUBMITTED":
        return None
    result = payload.get("result")
    # The read-side status is the proof that the MySQL ledger already
    # succeeded. Re-enter the existing idempotent Java boundary only after
    # that proof, so it can repair the PostgreSQL draft/Approval marker
    # without issuing another party-file CRUD mutation.
    operation = str(request.get("operation") or "").strip().lower()
    if operation not in {"create", "update", "delete"}:
        return None
    repaired = java_post(
        f"/agent/tools/party-files/commit/{operation}",
        {
            "draftId": str(request.get("draftId") or draft_id),
            "approvalId": str(request.get("approvalId") or approval_id),
            "operationId": str(request.get("operationId") or operation_id),
        },
    )
    return repaired if isinstance(repaired, dict) else (result if isinstance(result, dict) else {
        key: value for key, value in payload.items() if key != "status"
    })
from ..common.events import turn_id_from_context

@tool
def get_manage_party_file(party_file_id: int, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """读取有编辑权限的党务文件完整字段，用于修改或删除前核验。"""
    bind_tool_call_id(tool_call_id)
    try: return tool_success(java_get(f"/agent/tools/party-files/manage/{int(party_file_id)}"))
    except Exception as exc: return tool_failure("PARTY_FILE_NOT_FOUND", "党务文件不存在或无编辑权限", details=str(exc))

def _save_party_file_draft(operation: str, title: str = "", category_id: int | None = None,
                           category_name: str = "", distribute_to_self: bool = False,
                           summary: str = "", content: str = "", attachment_file_ids: str = "",
                           storage_type: int | None = None, status: int | None = None,
                           publish_time: str = "", targets: list[dict] | None = None,
                           source_party_file_id: int | None = None,
                           tool_call_id: str = "", tool_name: str = "create_party_file_draft",
                           document_type: str = "") -> ToolResponse:
    """Shared draft persistence; operation-specific public tools call this kernel."""
    bind_tool_call_id(tool_call_id)
    action = operation.strip().upper()
    context = dict(current_agent_context())
    # LangGraph Server can rebuild a tool frame without the optional gateway
    # messageId. Use the stable run-derived turn ID only as a transport
    # fallback; tenant/user/thread/run still must be present and are never
    # guessed. The Java Approval and the Operation both retain this envelope.
    if not str(context.get("messageId") or "").strip():
        context["messageId"] = turn_id_from_context(context)
    if action not in {"CREATE", "UPDATE", "DELETE"}:
        return tool_failure("PARTY_FILE_OPERATION_INVALID", "操作必须是 CREATE、UPDATE 或 DELETE")
    if action in {"UPDATE", "DELETE"} and not source_party_file_id:
        return tool_failure("PARTY_FILE_TARGET_REQUIRED", "修改或删除前必须指定 source_party_file_id")
    if any(not context.get(k) for k in ("runId","threadId","messageId")): return tool_failure("PARTY_FILE_CONTEXT_INVALID", "当前文件草稿缺少 Agent 运行上下文")
    # CREATE requests often contain a complete document but no internal OA
    # form fields. Resolve a stable category name from the document shape, then
    # let Java map that name to the tenant's actual category ID. UPDATE keeps
    # the source snapshot when the category is omitted.
    effective_category_name = canonical_category_name(category_name, title, document_type)
    try:
        resolved_category_id = resolve_category_id(
            category_id, effective_category_name, category_loader=java_get_list
        )
        resolved_targets = normalize_targets(targets, distribute_to_self, context)
    except ValueError as exc:
        message = str(exc)
        if "分类" in message:
            return tool_failure(
                "PARTY_FILE_CATEGORY_REQUIRED",
                "未找到可用的党务文件类别，请提供有效的 category_name（例如：通知公告、制度规范、组织建设）。",
                details=message,
            )
        return tool_failure("PARTY_FILE_INPUT_INVALID", message)
    if action == "CREATE" and resolved_category_id is None:
        return tool_failure(
            "PARTY_FILE_CATEGORY_REQUIRED",
            "无法根据标题确定文件类别，请提供 category_name（例如：通知公告、制度规范、组织建设）。",
        )
    # CREATE/UPDATE use the ordinary published-file defaults unless the user
    # explicitly supplies a different supported value.  These defaults are
    # business facts, not model decisions, and keep a natural-language write
    # request from failing on invisible OA form fields.
    if action != "DELETE":
        storage_type = 1 if storage_type is None else storage_type
        status = 0 if status is None else status
        if action == "CREATE" and not str(publish_time or "").strip():
            publish_time = datetime.now(AGENT_TIMEZONE).replace(microsecond=0).strftime("%Y-%m-%d %H:%M:%S")
        # A publication without an explicit audience has the OA business
        # default "全员".  UPDATE with [] intentionally remains empty so Java
        # can merge the source snapshot and preserve existing recipients.
        if action == "CREATE" and not resolved_targets:
            resolved_targets = [{"targetType": 1}]
    payload = {
        "operation": action,
        "sourcePartyFileId": source_party_file_id,
        "title": title.strip() or None,
        "categoryId": resolved_category_id,
        "categoryName": effective_category_name or None,
        "summary": summary.strip() or None,
        "content": content,
        "attachmentFileIds": attachment_file_ids.strip() or None,
        "storageType": storage_type,
        "status": status,
        "publishTime": publish_time.strip() or None,
        "targets": resolved_targets,
        "tenantId": context.get("tenantId"),
        "userId": context.get("userId"),
        "runId": context["runId"],
        "threadId": context["threadId"],
        "messageId": context["messageId"],
    }
    payload["idempotencyKey"] = (
        f"{context['runId']}:{context['messageId']}:party-file:"
        f"{action}:{source_party_file_id or 'new'}"
    )
    emit(get_stream_writer(), "tool_started", "正在生成党务文件确认草稿……", toolName=tool_name, toolCallId=tool_call_id)
    runtime = None
    # Use an operation-specific facade route so the HTTP permission contract
    # matches the eventual mutation (CREATE, UPDATE or DELETE).  A single
    # generic write permission would let an update-only user mint a delete
    # draft, which is outside the Java authorization boundary.
    try:
        try:
            runtime = OperationRuntime.start(
                action_id=action_id_for("party_file", action),
                capability_id="party_file",
                operation_key=f"{action}:{source_party_file_id or 'new'}",
                required=True,
                payload={
                    "operation": action,
                    "sourcePartyFileId": source_party_file_id,
                    "idempotencyKey": payload["idempotencyKey"],
                    "title": payload.get("title"),
                    "categoryId": payload.get("categoryId"),
                    "publishTime": payload.get("publishTime"),
                    "targets": payload.get("targets"),
                },
            )
        except Exception as exc:
            return tool_failure(
                "PARTY_FILE_RUNTIME_UNAVAILABLE",
                "党务文件持久化操作不可用，请稍后重试",
                details=str(exc),
                retryable=True,
            )
        if runtime is None:
            raise RuntimeError("党务文件需要可用的 Operation Runtime")
        if runtime.operation.status == "COLLECTING_INFO":
            runtime.transition("READY", event_type="operation.ready")
        if runtime.operation.status == "READY":
            runtime.transition("RUNNING", event_type="operation.running")
        if runtime.operation.status not in {"RUNNING", "WAITING_APPROVAL"}:
            raise RuntimeError(
                f"党务文件 Operation 当前状态 {runtime.operation.status} 不能生成审批草稿"
            )
        payload["operationId"] = runtime.operation_id
        saved = java_post(f"/agent/tools/party-files/drafts/{action.lower()}", payload)
        did=str(saved.get("draftId") or ""); aid=str(saved.get("approvalId") or "")
        if not did or not aid: raise RuntimeError("Java 未返回有效的文件草稿或确认 ID")
        runtime.bind_approval(aid)
        if runtime.operation.status == "RUNNING":
            runtime.transition("WAITING_APPROVAL", event_type="operation.waiting_approval", data={"approvalId": aid})
    except Exception as exc:
        if runtime is not None:
            try:
                if runtime.operation.status in {"COLLECTING_INFO", "READY", "RUNNING"}:
                    runtime.transition("FAILED", event_type="operation.failed", data={"error": str(exc)[:500]})
            except Exception:
                pass
            finally:
                runtime.close()
        if isinstance(exc, RuntimeError) and "Runtime" in str(exc):
            return tool_failure("PARTY_FILE_RUNTIME_UNAVAILABLE", "党务文件操作暂不可用，请稍后重试", details=str(exc), retryable=True)
        error_code, error_message = _map_party_file_write_error(exc)
        return tool_failure(error_code, error_message, details=str(exc))
    draft=saved.get("draft") if isinstance(saved.get("draft"),dict) else payload
    draft = {**draft, "draftId": did, "approvalId": aid, "operationId": runtime.operation_id}
    runtime.close()
    emit(get_stream_writer(), "draft.created", "党务文件草稿已生成，等待用户确认", toolName=tool_name, toolCallId=tool_call_id, draftId=did, approvalId=aid, draft=draft)
    return tool_success({"requires_confirmation":True,"confirmation_token":did,"draftId":did,"approvalId":aid,"draft":draft}, {"blockType":"card","cardType":"party_file_approval"})

@tool
def create_party_file_draft(operation: str = "CREATE", title: str = "", category_id: int | None = None,
                            category_name: str = "", distribute_to_self: bool = False,
                            summary: str = "", content: str = "", attachment_file_ids: str = "",
                            storage_type: int | None = None, status: int | None = None,
                            publish_time: str = "", targets: list[dict] | None = None,
                            source_party_file_id: int | None = None,
                            document_type: str = "",
                            tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """生成 CREATE 党务文件草稿；分类/发布时间/全员分发有确定性业务默认值。"""
    action = operation.strip().upper()
    if action != "CREATE":
        return tool_failure("PARTY_FILE_TOOL_BOUNDARY", "CREATE 工具只允许 CREATE；UPDATE/DELETE 请调用对应操作工具")
    return _save_party_file_draft(action, title, category_id, category_name, distribute_to_self, summary, content, attachment_file_ids,
                                  storage_type, status, publish_time, targets, source_party_file_id,
                                  tool_call_id, "create_party_file_draft", document_type)

@tool
def update_party_file_draft(source_party_file_id: int | None = None, title: str = "", category_id: int | None = None,
                            category_name: str = "", distribute_to_self: bool = False,
                            summary: str = "", content: str = "", attachment_file_ids: str = "",
                            storage_type: int | None = None, status: int | None = None,
                            publish_time: str = "", targets: list[dict] | None = None,
                            document_type: str = "",
                            tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """生成 UPDATE 党务文件草稿。"""
    return _save_party_file_draft("UPDATE", title, category_id, category_name, distribute_to_self, summary, content, attachment_file_ids,
                                  storage_type, status, publish_time, targets, source_party_file_id,
                                  tool_call_id, "update_party_file_draft", document_type)

@tool
def delete_party_file_draft(source_party_file_id: int | None = None,
                            tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """生成 DELETE 党务文件草稿。"""
    return _save_party_file_draft("DELETE", source_party_file_id=source_party_file_id,
                                  tool_call_id=tool_call_id, tool_name="delete_party_file_draft")

def _confirm(operation: str, confirmation_token: str, draft_id: str, approval_id: str, tool_call_id: str) -> ToolResponse:
    bind_tool_call_id(tool_call_id)
    if confirmation_token != draft_id: return tool_failure("APPROVAL_CONTEXT_INVALID", "文件确认令牌与草稿不匹配")
    coordinator: EffectCommitCoordinator | None = None
    runtime: OperationRuntime | None = None
    try:
        from ...services.party_file_approval import (
            approval_status,
            consume_party_file_resume,
            load_party_file_confirmation,
        )
        context, error = load_party_file_confirmation(draft_id, approval_id)
        if context is None:
            return tool_failure("APPROVAL_CONTEXT_INVALID", "党务文件审批不属于当前用户或当前会话", details=str(error or "binding_failed"))
        status = approval_status(context)
        if status == "REJECTED": return tool_failure("APPROVAL_REJECTED", "用户已取消党务文件操作")
        if status == "EXPIRED": return tool_failure("APPROVAL_EXPIRED", "党务文件确认已过期，请重新生成草稿")
        if status == "COMPLETED":
            # Java Approval completion is durable evidence that the business
            # commit already succeeded. Let the Effect coordinator replay or
            # reconcile its result instead of requiring a second card resume.
            mark_run_resumed()
        else:
            if status != "APPROVED": return tool_failure("APPROVAL_REQUIRED", "党务文件仍等待用户确认，不能提交")
            if not consume_party_file_resume(context):
                return tool_failure("APPROVAL_RESUME_REQUIRED", "请通过当前 ApprovalCard 确认后再提交党务文件")
            mark_run_resumed()
        draft = context.draft
        operation_id = str(draft.get("operationId") or "").strip()
        if not operation_id:
            return tool_failure("OPERATION_REQUIRED", "党务文件缺少持久化 Operation，已拒绝直接写入业务系统")
        runtime = OperationRuntime.open_existing(operation_id, required=True)
        if runtime is None:
            return tool_failure("OPERATION_RUNTIME_UNAVAILABLE", "党务文件持久化操作不可用，请稍后重试", retryable=True)
        expected_action = _party_file_action_id(draft)
        coordinator = EffectCommitCoordinator(
            runtime=runtime,
            expected_action_id=expected_action,
            request_data={
                "operationId": operation_id,
                "draftId": draft_id,
                "approvalId": approval_id,
                "operation": str(draft.get("operation") or operation).upper(),
                "sourcePartyFileId": draft.get("sourcePartyFileId"),
            },
            idempotency_key=f"{operation_id}:party-file.commit:{draft_id}",
            reconcile_strategy="party_file.commit.status",
            lease_owner=f"{current_agent_context().get('runId') or 'run'}:{tool_call_id or 'party-file-commit'}",
        )
        start = coordinator.prepare()
        if start.reconciliation_required:
            result = coordinator.reconcile(
                lambda effect: _resolved_party_file_result(
                    effect, draft_id=draft_id, approval_id=approval_id, operation_id=operation_id,
                ),
                pending_message="党务文件提交结果仍在核对中，请稍后重试",
            )
        elif start.recovered_result is not None:
            result = start.recovered_result
        else:
            result = java_post(
                f"/agent/tools/party-files/commit/{operation.lower()}",
                {"draftId": draft_id, "approvalId": approval_id, "operationId": operation_id},
            )
            coordinator.settle_success(result)
    except ReconciliationPending as exc:
        return tool_failure("PARTY_FILE_RECONCILIATION_PENDING", str(exc), retryable=True)
    except CommitInProgress as exc:
        return tool_failure("PARTY_FILE_COMMIT_IN_PROGRESS", str(exc), retryable=True)
    except StoredFinalFailure as exc:
        return tool_failure(exc.code, exc.message, retryable=False)
    except CommitKernelError as exc:
        return tool_failure(exc.code, exc.message, retryable=False)
    except JavaFacadeBusinessError as exc:
        if coordinator is not None:
            try:
                coordinator.record_failure(exc, unknown=False, code="PARTY_FILE_BUSINESS_REJECTED")
            except Exception:
                pass
        code, message = _map_party_file_write_error(exc)
        if "版本" in str(exc.message) or "VERSION_CONFLICT" in str(exc.message):
            code, message = "PARTY_FILE_VERSION_CONFLICT", "党务文件已被其他操作修改，请重新读取后生成新的草稿。"
        elif code == "PARTY_FILE_DRAFT_SAVE_FAILED":
            code, message = "PARTY_FILE_COMMIT_REJECTED", "党务文件未被业务系统接受，请检查最新状态或权限。"
        return tool_failure(code, message, details=str(exc))
    except Exception as exc:
        if coordinator is not None:
            unknown = _is_unknown_commit_error(exc)
            try:
                coordinator.record_failure(
                    exc,
                    unknown=unknown,
                    code="PARTY_FILE_COMMIT_UNKNOWN" if unknown else "PARTY_FILE_COMMIT_FAILED",
                )
            except Exception:
                pass
            return tool_failure(
                "PARTY_FILE_COMMIT_UNKNOWN" if unknown else "PARTY_FILE_COMMIT_FAILED",
                "党务文件提交结果未知，请稍后重试并先核对提交结果" if unknown else "党务文件提交失败，请稍后重试",
                details=str(exc),
                retryable=unknown,
            )
        return tool_failure("PARTY_FILE_COMMIT_FAILED", "党务文件未被业务系统接受，请检查最新状态或权限", details=str(exc))
    finally:
        if runtime is not None:
            runtime.close()
    emit(get_stream_writer(), "approval.approved", "党务文件已提交", toolName="confirm_party_file", toolCallId=tool_call_id, draftId=draft_id, approvalId=approval_id)
    return tool_success(result)

@tool
def confirm_create_party_file(confirmation_token: str, draft_id: str, approval_id: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """确认并发布 CREATE 党务文件草稿。"""
    return _confirm("CREATE", confirmation_token, draft_id, approval_id, tool_call_id)

@tool
def confirm_update_party_file(confirmation_token: str, draft_id: str, approval_id: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """确认并提交 UPDATE 党务文件草稿。"""
    return _confirm("UPDATE", confirmation_token, draft_id, approval_id, tool_call_id)

@tool
def confirm_delete_party_file(confirmation_token: str, draft_id: str, approval_id: str, tool_call_id: Annotated[str, InjectedToolCallId] = "") -> ToolResponse:
    """确认并提交 DELETE 党务文件草稿。"""
    return _confirm("DELETE", confirmation_token, draft_id, approval_id, tool_call_id)
