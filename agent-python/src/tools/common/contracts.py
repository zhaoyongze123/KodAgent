"""Agent Tool 的统一契约、结果和运行策略。"""

from dataclasses import dataclass
from functools import wraps
from typing import Any, Iterable
from pydantic import BaseModel
from ...domain.errors import describe_error_code

# Re-exported here for callers that treat this module as the canonical tool
# contract entry point.  ``presentation.py`` imports ToolResponse lazily to
# keep this dependency cycle-free.
from .presentation import PresentationSpec

try:
    # Official LangGraph ToolNode handling re-raises GraphBubbleUp before its
    # broad Exception handler. GraphInterrupt inherits from it, so this also
    # preserves interrupt/resume control flow.
    from langgraph.errors import GraphBubbleUp
except ImportError:  # pragma: no cover - compatibility with older LangGraph
    from langgraph.pregel import GraphBubbleUp


class ToolError(BaseModel):
    code: str
    message: str
    details: Any = None
    # Machine-readable category for recovery/UI; optional for compatibility
    # with existing callers that only provide code and message.
    kind: str | None = None
    retryable: bool | None = None
    user_action: str | None = None


class ToolResponse(BaseModel):
    ok: bool
    data: Any = None
    error: ToolError | None = None
    presentation: dict[str, Any] | None = None

    def to_tool_content(self) -> str:
        """Serialize the response at the LangChain tool boundary.

        Tool implementations keep using the typed model internally.  LangChain
        may otherwise turn a Pydantic object into ``ok=True data=...`` repr text,
        which is not reliably consumable by clients after a stream/reload.
        """
        return self.model_dump_json(exclude_none=True)


@dataclass(frozen=True)
class ToolContract:
    name: str
    description: str
    read_only: bool
    side_effect: bool
    approval_required: bool
    permission: str = "agent:read"
    timeout_seconds: float = 15.0
    retryable: bool = False
    max_retries: int = 0
    idempotency: str = "none"
    sensitive_fields: tuple[str, ...] = ()
    input_schema: str = "generated-from-function-signature"
    version: str = "1"
    error_codes: tuple[str, ...] = ()

    def metadata(self) -> dict[str, Any]:
        return {
            "contract": {
                "description": self.description,
                "readOnly": self.read_only,
                "sideEffect": self.side_effect,
                "approvalRequired": self.approval_required,
                "permission": self.permission,
                "timeoutSeconds": self.timeout_seconds,
                "retryable": self.retryable,
                "maxRetries": self.max_retries,
                "idempotency": self.idempotency,
                "sensitiveFields": list(self.sensitive_fields),
                "inputSchema": self.input_schema,
                "version": self.version,
                "errorCodes": list(self.error_codes),
            }
        }


TOOL_CONTRACTS = {
    "report_progress": ToolContract("report_progress", "播报用户可见的执行摘要", True, False, False, permission="agent:progress", timeout_seconds=5),
    "resolve_agent_model": ToolContract("resolve_agent_model", "解析当前 Run 允许使用的模型配置", True, False, False, permission="model:read", timeout_seconds=10),
    "route_conversation": ToolContract("route_conversation", "校验能力 ID、执行策略和任务复杂度，生成结构化路由决策", True, False, False, permission="agent:conversation", timeout_seconds=3),
    "get_agent_action_catalog": ToolContract("get_agent_action_catalog", "读取 Java 权威 Agent 业务动作契约", True, False, False, permission="agent:contract", timeout_seconds=10, retryable=True, max_retries=1, input_schema="AgentActionCatalog"),
    "prepare_meeting_booking_request": ToolContract("prepare_meeting_booking_request", "解析并校验会议预约请求，不产生业务变更", True, False, False, permission="meeting:read", timeout_seconds=15),
    "list_my_meeting_bookings": ToolContract("list_my_meeting_bookings", "查询当前用户可见的会议预约", True, False, False, permission="meeting:read", timeout_seconds=10, retryable=True, max_retries=2),
    "get_my_meeting_booking": ToolContract("get_my_meeting_booking", "读取当前用户可见的会议预约详情", True, False, False, permission="meeting:read", timeout_seconds=10),
    "get_meeting_booking_commit_status": ToolContract("get_meeting_booking_commit_status", "查询会议预约提交结果以恢复丢失响应", True, False, False, permission="meeting:read", timeout_seconds=10),
    "get_personal_schedule_commit_status": ToolContract("get_personal_schedule_commit_status", "查询个人日程提交结果以恢复丢失响应", True, False, False, permission="schedule:read", timeout_seconds=10),
    "create_meeting_booking_cancellation_draft": ToolContract("create_meeting_booking_cancellation_draft", "生成取消本人会议预约的确认草稿", False, True, False, permission="meeting:booking:create", timeout_seconds=15, idempotency="request-key"),
    "list_available_meeting_rooms": ToolContract("list_available_meeting_rooms", "查询启用会议室", True, False, False, permission="meeting:read", timeout_seconds=10, retryable=True, max_retries=2),
    "search_meeting_attendees": ToolContract("search_meeting_attendees", "查询可作为参会人的用户", True, False, False, permission="meeting:read", timeout_seconds=10, retryable=True, max_retries=2),
    "get_current_meeting_user": ToolContract("get_current_meeting_user", "获取认证上下文中的当前用户", True, False, False, permission="meeting:read", timeout_seconds=10),
    "get_meeting_attendees_calendar": ToolContract("get_meeting_attendees_calendar", "查询参会人日程", True, False, False, permission="meeting:read", timeout_seconds=10, retryable=True, max_retries=2),
    "check_meeting_room_conflict": ToolContract("check_meeting_room_conflict", "检查会议室预约冲突", True, False, False, permission="meeting:read", timeout_seconds=10, retryable=True, max_retries=2),
    "check_meeting_availability": ToolContract("check_meeting_availability", "统一检查会议室和参会人可预约性", True, False, False, permission="meeting:read", timeout_seconds=15, retryable=True, max_retries=2),
    "check_meeting_availability_batch": ToolContract("check_meeting_availability_batch", "批量检查候选会议室和参会人可预约性并确定性选择会议室", True, False, False, permission="meeting:read", timeout_seconds=30, retryable=True, max_retries=1),
    "create_meeting_booking_draft": ToolContract("create_meeting_booking_draft", "保存会议预约草稿，不提交最终业务变更", False, True, False, permission="meeting:booking:create", timeout_seconds=15, idempotency="request-key"),
    "confirm_meeting_booking": ToolContract("confirm_meeting_booking", "提交会议室预约", False, True, True, permission="meeting:booking:create", timeout_seconds=15, idempotency="draft-id", sensitive_fields=("identityTicket",)),
    "run_meeting_booking_workflow": ToolContract("run_meeting_booking_workflow", "按固定顺序整理会议预约、检查冲突并生成草稿", False, True, False, permission="meeting:booking:create", timeout_seconds=60, retryable=True, max_retries=1, idempotency="request-key"),
    "run_personal_schedule_workflow": ToolContract("run_personal_schedule_workflow", "按固定顺序校验个人日程并生成草稿", False, True, False, permission="schedule:write", timeout_seconds=45, retryable=True, max_retries=1, idempotency="request-key"),
    # These are Agent-internal Java calls. They still need a contract so a
    # support operation cannot silently fall back to report_progress.
    "get_meeting_booking_draft": ToolContract("get_meeting_booking_draft", "读取已保存的会议预约草稿", True, False, False, permission="meeting:booking:create", timeout_seconds=10),
    "get_meeting_booking_approval": ToolContract("get_meeting_booking_approval", "读取当前用户的 Agent 审批状态", True, False, False, permission="approval:read", timeout_seconds=10),
    "delete_meeting_booking_draft": ToolContract("delete_meeting_booking_draft", "取消会议预约草稿", False, True, False, permission="meeting:booking:create", timeout_seconds=10, idempotency="draft-id"),
    "update_meeting_booking_draft_status": ToolContract("update_meeting_booking_draft_status", "更新会议预约草稿状态", False, True, False, permission="meeting:booking:create", timeout_seconds=10, idempotency="draft-id"),
    "agent_event_persist": ToolContract("agent_event_persist", "保存 Agent 运行审计事件", False, True, False, permission="agent:audit", timeout_seconds=5, retryable=True, max_retries=3),
    "get_agent_run_events": ToolContract("get_agent_run_events", "读取 Agent Run 审计事件", True, False, False, permission="agent:audit", timeout_seconds=10),
    "cancel_agent_run": ToolContract("cancel_agent_run", "记录 Agent Run 已取消", False, True, False, permission="agent:audit", timeout_seconds=10, idempotency="run-id"),
    "record_agent_run_metric": ToolContract("record_agent_run_metric", "记录 Agent Run 前端指标", False, True, False, permission="agent:audit", timeout_seconds=10),
    "get_agent_thread_events": ToolContract("get_agent_thread_events", "读取 Agent Thread 事件", True, False, False, permission="agent:audit", timeout_seconds=10),
    "decide_agent_approval": ToolContract("decide_agent_approval", "写入 Agent 审批卡片决定或恢复审计", False, True, True, permission="approval:write", timeout_seconds=10, idempotency="approval-decision"),
    "list_agent_models": ToolContract("list_agent_models", "读取当前用户可选择的 Agent 模型", True, False, False, permission="model:read", timeout_seconds=10),
    "list_my_pending_approvals": ToolContract("list_my_pending_approvals", "仅查询未指定筛选和排序条件的当前用户待办审批；涉及金额、流程类型、部门、积压天数或排序时必须使用 search_my_pending_approvals", True, False, False, permission="approval:read", timeout_seconds=10, retryable=True, max_retries=2),
    "search_my_pending_approvals": ToolContract("search_my_pending_approvals", "按结构化条件筛选、排序当前用户待办审批；必须承载用户提出的金额、流程类型、部门、时间和积压条件", True, False, False, permission="approval:read", timeout_seconds=20, retryable=True, max_retries=2),
    "analyze_my_pending_approvals": ToolContract("analyze_my_pending_approvals", "分析当前用户待办审批", True, False, False, permission="approval:read", timeout_seconds=30, retryable=True, max_retries=1),
    "run_approval_query_plan": ToolContract("run_approval_query_plan", "执行已由规则层规范化的审批查询计划，固定过滤、排序、空值和分页语义", True, False, False, permission="approval:read", timeout_seconds=30, retryable=True, max_retries=2, input_schema="CanonicalQueryPlan"),
    "list_my_approval_applications": ToolContract("list_my_approval_applications", "查询当前用户自己发起的审批流程", True, False, False, permission="approval:read", timeout_seconds=20, retryable=True, max_retries=2),
    "get_my_approval_application": ToolContract("get_my_approval_application", "读取当前用户自己发起的审批流程详情", True, False, False, permission="approval:read", timeout_seconds=15, retryable=True, max_retries=1),
    "list_my_approval_history": ToolContract("list_my_approval_history", "查询当前用户已办审批历史", True, False, False, permission="approval:read", timeout_seconds=20, retryable=True, max_retries=2),
    "preview_approval_batch_action": ToolContract("preview_approval_batch_action", "预览审批批量处理动作", True, False, False, permission="approval:read", timeout_seconds=30, retryable=True, max_retries=1, idempotency="batch-preview"),
    "confirm_approval_batch_action": ToolContract("confirm_approval_batch_action", "确认并执行审批批量处理动作", False, True, True, permission="approval:write", timeout_seconds=60, idempotency="batch-id"),
    "reconcile_approval_batch_action": ToolContract("reconcile_approval_batch_action", "核对批量审批外部结果并恢复原子提交事实", False, True, False, permission="approval:write", timeout_seconds=10, retryable=True, max_retries=2, idempotency="batch-reconcile"),
    "preview_approval_task_action": ToolContract("preview_approval_task_action", "预览单条待办审批动作", True, False, False, permission="approval:read", timeout_seconds=30, retryable=True, max_retries=1, idempotency="task-action-preview"),
    "confirm_approval_task_action": ToolContract("confirm_approval_task_action", "确认并执行单条待办审批动作", False, True, True, permission="approval:write", timeout_seconds=30, idempotency="task-action"),
    "get_approval_task_action_status": ToolContract("get_approval_task_action_status", "查询单条待办审批动作的最终状态", True, False, False, permission="approval:read", timeout_seconds=10, retryable=True, max_retries=2),
    "reconcile_approval_task_action": ToolContract("reconcile_approval_task_action", "核对外部待办结果并完成单条审批事实", False, True, False, permission="approval:write", timeout_seconds=10, retryable=True, max_retries=2, idempotency="task-action-reconcile"),
    "meeting_report": ToolContract("meeting_report", "会议只读报表", True, False, False, permission="meeting:read", timeout_seconds=30, retryable=True, max_retries=1, idempotency="report"),
    "schedule_report": ToolContract("schedule_report", "日程只读报表", True, False, False, permission="schedule:read", timeout_seconds=30, retryable=True, max_retries=1, idempotency="report"),
    "party_file_report": ToolContract("party_file_report", "党务文件只读报表", True, False, False, permission="party-file:read", timeout_seconds=30, retryable=True, max_retries=1, idempotency="report"),
    "approval_report": ToolContract("approval_report", "审批只读报表", True, False, False, permission="approval:read", timeout_seconds=30, retryable=True, max_retries=1, idempotency="report"),
    "get_manage_party_file": ToolContract("get_manage_party_file", "读取可编辑党务文件", True, False, False, permission="party-file:update", timeout_seconds=10),
    "create_party_file_draft": ToolContract("create_party_file_draft", "生成党务文件发布、修改或删除草稿", False, True, False, permission="party-file:create", timeout_seconds=15, idempotency="request-key"),
    "update_party_file_draft": ToolContract("update_party_file_draft", "生成党务文件更新草稿", False, True, False, permission="party-file:update", timeout_seconds=15, idempotency="request-key"),
    "delete_party_file_draft": ToolContract("delete_party_file_draft", "生成党务文件删除草稿", False, True, False, permission="party-file:delete", timeout_seconds=15, idempotency="request-key"),
    "get_party_file_draft": ToolContract("get_party_file_draft", "读取当前用户的党务文件草稿", True, False, False, permission="party-file:read", timeout_seconds=10),
    "get_party_file_commit_status": ToolContract("get_party_file_commit_status", "查询党务文件提交结果以恢复丢失响应", True, False, False, permission="party-file:read", timeout_seconds=10, retryable=True, max_retries=2),
    "confirm_create_party_file": ToolContract("confirm_create_party_file", "确认并发布党务文件草稿", False, True, True, permission="party-file:create", timeout_seconds=20, idempotency="draft-id"),
    "confirm_update_party_file": ToolContract("confirm_update_party_file", "确认并更新党务文件草稿", False, True, True, permission="party-file:update", timeout_seconds=20, idempotency="draft-id"),
    "confirm_delete_party_file": ToolContract("confirm_delete_party_file", "确认并删除党务文件草稿", False, True, True, permission="party-file:delete", timeout_seconds=20, idempotency="draft-id"),
    "list_startable_approval_types": ToolContract("list_startable_approval_types", "查询可由 Agent 发起的审批模板", True, False, False, permission="approval:read", timeout_seconds=10, retryable=True, max_retries=2),
    "preview_approval_request": ToolContract("preview_approval_request", "预览请假或出差审批链", True, False, False, permission="approval:read", timeout_seconds=15, retryable=True, max_retries=1),
    "create_approval_request_draft": ToolContract("create_approval_request_draft", "生成请假或出差审批申请草稿", False, True, False, permission="approval:write", timeout_seconds=30, idempotency="request-key"),
    "create_generic_approval_request_draft": ToolContract("create_generic_approval_request_draft", "按模板字段生成通用审批申请草稿", False, True, False, permission="approval:write", timeout_seconds=30, idempotency="request-key"),
    "create_approval_withdraw_draft": ToolContract("create_approval_withdraw_draft", "生成本人审批流程撤回草稿", False, True, False, permission="approval:write", timeout_seconds=20, idempotency="request-key"),
    "confirm_approval_request_action": ToolContract("confirm_approval_request_action", "确认并提交请假或出差审批申请", False, True, True, permission="approval:write", timeout_seconds=30, idempotency="approval-request"),
    "confirm_approval_withdraw_action": ToolContract("confirm_approval_withdraw_action", "确认并撤回本人审批流程", False, True, True, permission="approval:write", timeout_seconds=30, idempotency="approval-withdraw"),
    "get_approval_task_detail": ToolContract("get_approval_task_detail", "读取当前用户待办审批详情", True, False, False, permission="approval:read", timeout_seconds=10),
    "get_my_calendar": ToolContract("get_my_calendar", "查询当前用户日历", True, False, False, permission="schedule:read", timeout_seconds=10, retryable=True, max_retries=2),
    "find_calendar_conflicts": ToolContract("find_calendar_conflicts", "查询日历时间冲突", True, False, False, permission="schedule:read", timeout_seconds=15, retryable=True, max_retries=1),
    "get_personal_schedule": ToolContract("get_personal_schedule", "读取当前用户的个人日程详情", True, False, False, permission="schedule:read", timeout_seconds=10),
    "get_personal_schedule_draft": ToolContract("get_personal_schedule_draft", "读取当前用户的个人日程草稿", True, False, False, permission="schedule:write", timeout_seconds=10),
    "create_personal_schedule_draft": ToolContract("create_personal_schedule_draft", "生成个人日程创建、修改或取消草稿，不提交最终变更", False, True, False, permission="schedule:write", timeout_seconds=15, idempotency="request-key"),
    "confirm_personal_schedule": ToolContract("confirm_personal_schedule", "确认并提交个人日程草稿", False, True, True, permission="schedule:write", timeout_seconds=15, idempotency="draft-id"),
    "search_party_files": ToolContract("search_party_files", "查询当前用户有权限的党务文件", True, False, False, permission="party-file:read", timeout_seconds=10, retryable=True, max_retries=2),
    "execute_party_file_metadata_plan": ToolContract("execute_party_file_metadata_plan", "执行已编译的党务文件元数据筛选、排序和分页计划", True, False, False, permission="party-file:read", timeout_seconds=30, retryable=True, max_retries=1, input_schema="PartyFileMetadataQueryPlan"),
    # These look like reads to the caller, but Java durably records the
    # current user's detail/preview/download receipt.  Model-facing tools
    # must describe that fact accurately while keeping it outside HITL: it is
    # a user-scoped, reversible audit marker rather than an irreversible
    # content mutation.
    "get_party_file_detail": ToolContract("get_party_file_detail", "读取党务文件详情并记录当前用户已读", False, True, False, permission="party-file:read", timeout_seconds=10, idempotency="user-read-receipt"),
    "get_party_file_attachments": ToolContract("get_party_file_attachments", "核对当前用户可见党务文件是否包含附件并返回预览/下载入口信息", False, True, False, permission="party-file:read", timeout_seconds=10, idempotency="user-read-receipt"),
    "get_party_file_attachment": ToolContract("get_party_file_attachment", "读取党务文件附件元数据并记录当前用户预览或下载", False, True, False, permission="party-file:read", timeout_seconds=10, idempotency="user-read-receipt"),
    "list_party_file_categories": ToolContract("list_party_file_categories", "查询党务文件分类", True, False, False, permission="party-file:read", timeout_seconds=10, retryable=True, max_retries=2),
    "search_party_knowledge": ToolContract("search_party_knowledge", "检索授权党务知识并返回引用", True, False, False, permission="party-file:read", timeout_seconds=30, retryable=True, max_retries=1),
    "check_party_knowledge_health": ToolContract("check_party_knowledge_health", "读取党务知识索引和向量检索健康状态", True, False, False, permission="party-file:read", timeout_seconds=10),
    "get_party_knowledge_document": ToolContract("get_party_knowledge_document", "读取授权党务知识文档", True, False, False, permission="party-file:read", timeout_seconds=10),
    "get_party_knowledge_chunk": ToolContract("get_party_knowledge_chunk", "读取授权党务知识片段", True, False, False, permission="party-file:read", timeout_seconds=10),
    "run_party_file_understanding": ToolContract("run_party_file_understanding", "理解授权党务文件内容", True, False, False, permission="party-file:read", timeout_seconds=45, retryable=True, max_retries=1),
    "run_party_file_compare": ToolContract("run_party_file_compare", "比较授权党务文件版本", True, False, False, permission="party-file:read", timeout_seconds=60, retryable=True, max_retries=1),
    "check_approval_against_party_file": ToolContract("check_approval_against_party_file", "按授权制度校验审批材料", True, False, False, permission="approval:read", timeout_seconds=60, retryable=True, max_retries=1),
}


def apply_tool_contracts(tools: Iterable[Any]) -> list[Any]:
    """把契约挂到 Tool，并在运行时校验输入、输出和异常。"""
    result = list(tools)
    missing = []
    for item in result:
        contract = TOOL_CONTRACTS.get(getattr(item, "name", ""))
        if not contract:
            missing.append(getattr(item, "name", "<unnamed>"))
            continue
        metadata = contract.metadata()
        schema = getattr(item, "args_schema", None)
        if schema is not None and hasattr(schema, "model_json_schema"):
            metadata["contract"]["inputSchema"] = schema.model_json_schema()
            original_func = getattr(item, "func", None)
            if original_func is not None and not getattr(original_func, "_oa_contract_guarded", False):
                @wraps(original_func)
                def guarded(*args: Any, __func=original_func, __schema=schema,
                            __contract=contract, **kwargs: Any) -> ToolResponse:
                    try:
                        # StructuredTool normally performs this validation too;
                        # keeping it here makes direct/unit calls obey the same contract.
                        if hasattr(__schema, "model_validate"):
                            __schema.model_validate(kwargs)
                        result = __func(*args, **kwargs)
                        validated = validate_tool_result(__contract, result)
                        # Keep the implementation contract typed, but expose
                        # one canonical JSON representation to LangChain.
                        return validated.to_tool_content()
                    except GraphBubbleUp:
                        # Never serialize GraphInterrupt/GraphBubbleUp as a
                        # normal ToolResponse. The graph must receive the
                        # control-flow exception unchanged to checkpoint and
                        # expose the interrupt to the caller.
                        raise
                    except Exception as exc:
                        return _exception_failure(exc).to_tool_content()

                guarded._oa_contract_guarded = True
                item.func = guarded
        item.metadata = {**(item.metadata or {}), **metadata}
    if missing:
        raise RuntimeError(f"未登记 Tool 契约，禁止启动 Agent: {', '.join(missing)}")
    return result


def get_tool_contract(name: str) -> ToolContract:
    """运行时读取契约；调用策略不得自行复制一份 Tool 配置。"""
    try:
        return TOOL_CONTRACTS[name]
    except KeyError as exc:
        raise RuntimeError(f"Tool 未登记契约: {name}") from exc


def validate_tool_result(contract: ToolContract, result: Any) -> ToolResponse:
    """所有 Agent Tool 必须返回结构化 ToolResponse，禁止透明字符串泄漏。"""
    if isinstance(result, ToolResponse):
        # The guarded LangChain boundary is the first place shared by every
        # Tool.  Normalize legacy card metadata here so new renderers receive
        # one contract while direct/unit callers can still inspect the old
        # ``blockType``/``cardType`` shape before the guard runs.
        from .presentation import presentation_for_response

        return presentation_for_response(result)
    if isinstance(result, dict) and "ok" in result:
        from .presentation import presentation_for_response

        return presentation_for_response(ToolResponse.model_validate(result))
    return tool_failure(
        "TOOL_OUTPUT_INVALID",
        f"Tool {contract.name} 返回了不符合契约的结果",
    )


def _exception_failure(exc: Exception) -> ToolResponse:
    """Convert integration exceptions without leaking transport internals."""
    code = str(getattr(exc, "error_code", "") or "").strip().upper()
    if not code or code.isdigit():
        code = "TOOL_EXECUTION_FAILED"
    descriptor = describe_error_code(code)
    if descriptor.kind == "authorization":
        message = "当前身份没有执行该操作的权限，或登录凭据已失效"
    elif descriptor.kind == "not_found":
        message = "目标业务记录不存在、已过期或当前用户不可见"
    elif descriptor.kind == "conflict":
        message = "业务数据已发生变化，请重新查询后再试"
    elif descriptor.kind == "dependency":
        message = "OA 服务暂时不可用，请稍后重试"
    elif descriptor.kind == "validation":
        message = "请求参数不符合业务契约，请补充或修正后重试"
    else:
        message = "工具执行失败，请稍后重试"
    details: Any = None
    if hasattr(exc, "status_code"):
        details = {"statusCode": getattr(exc, "status_code")}
    elif hasattr(exc, "path"):
        details = {"path": getattr(exc, "path")}
    return tool_failure(code, message, details=details)


def redact_sensitive(value: Any, fields: Iterable[str] = ()) -> Any:
    """递归脱敏审计数据，避免 API key、票据等进入事件或日志。"""
    sensitive = {str(field).lower() for field in fields}
    if isinstance(value, dict):
        return {
            key: ("***REDACTED***" if str(key).lower() in sensitive else redact_sensitive(item, fields))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item, fields) for item in value]
    return value


def tool_success(data: Any, presentation: dict[str, Any] | None = None) -> ToolResponse:
    return ToolResponse(ok=True, data=data, presentation=presentation)


def tool_failure(
    code: str,
    message: str,
    details: Any = None,
    *,
    kind: str | None = None,
    retryable: bool | None = None,
    user_action: str | None = None,
) -> ToolResponse:
    descriptor = describe_error_code(code)
    return ToolResponse(
        ok=False,
        error=ToolError(
            code=descriptor.code,
            message=message,
            details=details,
            kind=kind or descriptor.kind,
            retryable=descriptor.retryable if retryable is None else retryable,
            user_action=user_action or descriptor.user_action,
        ),
    )
