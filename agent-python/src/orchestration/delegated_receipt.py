"""领域子 Agent 向主 Agent 传递已核验业务结果的回执契约。

DeepAgents 默认会把子 Agent 最后一段自然语言作为 ``task`` 结果传回主图，
但自然语言只是展示内容，不能作为业务事实。这里定义由中间件根据真实
executor 的 ``ToolResponse`` 创建的结构化回执：主 Agent 可以据此汇总查询
结果、追问缺失信息或展示业务失败，同时绝不相信子 Agent 自己编造的文本。

会议草稿仍使用专用 ``DelegatedMeetingDraftReceipt``，以保持确认卡所需的
operation、draft、approval 与 confirmation token 的严格边界不变。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..tools.common import ToolResponse
from ..workflows.meeting_booking.contracts import MeetingBookingWorkflowOutcome


DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION = 1
EXECUTION_RECEIPT_KIND = "execution_result"
DRAFT_RECEIPT_KIND = "draft_ready"
PROJECT_INVESTIGATION_RECEIPT_KIND = "project_investigation"
# 会议回执已对接根图与历史 checkpoint，保留它既有的 kind，避免本次扩展
# 日程/党务/审批回执时破坏已上线的会议确认链路。
MEETING_DRAFT_RECEIPT_KIND = EXECUTION_RECEIPT_KIND
DelegatedExecutionStatus = Literal[
    "SUCCEEDED",
    "NEEDS_INPUT",
    "AMBIGUOUS_ENTITY",
    "CONFLICT_BLOCKED",
    "FAILED",
]


class DelegatedMeetingDraftReceipt(BaseModel):
    """会议子 Agent 已产生一个待确认草稿的代码凭据。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: Literal[DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION] = Field(
        default=DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION, alias="schemaVersion"
    )
    kind: Literal[MEETING_DRAFT_RECEIPT_KIND] = MEETING_DRAFT_RECEIPT_KIND
    domain: Literal["meeting"] = "meeting"
    status: Literal["DRAFT_READY"] = "DRAFT_READY"
    operation_id: str = Field(alias="operationId", min_length=1)
    draft_id: str = Field(alias="draftId", min_length=1)
    approval_id: str = Field(alias="approvalId", min_length=1)
    confirmation_token: str = Field(alias="confirmationToken", min_length=1)


class DelegatedPersonalScheduleDraftReceipt(BaseModel):
    """个人日程子 Agent 已生成待确认草稿的跨图凭据。

    ``operation`` 由 Java 草稿保存，是 CREATE、UPDATE、CANCEL 的唯一事实源；
    因此一个领域回执即可覆盖个人日程的增、改、取消。
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: Literal[DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION] = Field(
        default=DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION, alias="schemaVersion"
    )
    kind: Literal[DRAFT_RECEIPT_KIND] = DRAFT_RECEIPT_KIND
    domain: Literal["schedule"] = "schedule"
    status: Literal["DRAFT_READY"] = "DRAFT_READY"
    operation_id: str = Field(alias="operationId", min_length=1)
    draft_id: str = Field(alias="draftId", min_length=1)
    approval_id: str = Field(alias="approvalId", min_length=1)
    confirmation_token: str = Field(alias="confirmationToken", min_length=1)


class DelegatedPartyFileDraftReceipt(BaseModel):
    """党务文件子 Agent 已生成待确认草稿的跨图凭据。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: Literal[DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION] = Field(
        default=DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION, alias="schemaVersion"
    )
    kind: Literal[DRAFT_RECEIPT_KIND] = DRAFT_RECEIPT_KIND
    domain: Literal["party_file"] = "party_file"
    status: Literal["DRAFT_READY"] = "DRAFT_READY"
    operation_id: str = Field(alias="operationId", min_length=1)
    draft_id: str = Field(alias="draftId", min_length=1)
    approval_id: str = Field(alias="approvalId", min_length=1)
    confirmation_token: str = Field(alias="confirmationToken", min_length=1)


class DelegatedApprovalDraftReceipt(BaseModel):
    """审批子 Agent 已生成草稿或预览的跨图凭据。

    ``confirmation_type`` 只选择既有的三条官方确认通道，不能由主模型自由
    指定：申请/撤回使用 request，单条待办使用 task，批量待办使用 batch。
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: Literal[DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION] = Field(
        default=DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION, alias="schemaVersion"
    )
    kind: Literal[DRAFT_RECEIPT_KIND] = DRAFT_RECEIPT_KIND
    domain: Literal["approval"] = "approval"
    status: Literal["DRAFT_READY"] = "DRAFT_READY"
    confirmation_type: Literal["request", "task", "batch"] = Field(alias="confirmationType")
    operation_id: str = Field(alias="operationId", min_length=1)
    draft_id: str = Field(alias="draftId", min_length=1)
    approval_id: str = Field(alias="approvalId", min_length=1)
    confirmation_token: str = Field(alias="confirmationToken", min_length=1)


class DelegatedExecutionReceipt(BaseModel):
    """所有普通领域委托共用的已核验结果凭据。

    ``result``、``facts`` 与错误字段只能来自真正 executor 的 ToolResponse。
    子 Agent 仅返回 ``task`` 并不说明实际执行过 executor；主 Agent 必须先校验
    该回执的计划编号、执行器名称与父级 task 调用，再把它视为本轮结果。
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: Literal[DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION] = Field(
        default=DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION, alias="schemaVersion"
    )
    kind: Literal[EXECUTION_RECEIPT_KIND] = EXECUTION_RECEIPT_KIND
    plan_id: str = Field(alias="planId", min_length=1)
    executor_tool: str = Field(alias="executorTool", min_length=1)
    status: DelegatedExecutionStatus = "SUCCEEDED"
    result: Any | None = None
    presentation: dict[str, Any] | None = None
    message: str | None = None
    facts: dict[str, Any] | None = None
    error_code: str | None = Field(default=None, alias="errorCode")
    retryable: bool = False


class ProjectInvestigationToolTrace(BaseModel):
    """一次项目调查中由真实 ToolResponse 产生的工具轨迹。"""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    tool: str
    status: Literal["SUCCEEDED", "FAILED"]
    error_code: str | None = Field(default=None, alias="errorCode")


class DelegatedProjectInvestigationReceipt(BaseModel):
    """项目子 Agent 的多工具调查回执。

    该回执由中间件从所有真实项目工具响应汇总，模型自由文本不能创建或补写
    ``facts``、``citations`` 和 ``exports``。项目子 Agent 的自由文本不再作为
    跨 Agent 协议的一部分：主图只消费这些结构化事实，避免将内部工作笔记、协议
    字段或未经核验的推断直接呈现在用户界面。它与普通单 executor 回执分开，避免
    将一次 helper 查询误判为整个项目调查的唯一事实。
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: Literal[DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION] = Field(
        default=DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION, alias="schemaVersion"
    )
    kind: Literal[PROJECT_INVESTIGATION_RECEIPT_KIND] = PROJECT_INVESTIGATION_RECEIPT_KIND
    plan_id: str = Field(alias="planId", min_length=1)
    domain: Literal["project"] = "project"
    project_id: str = Field(alias="projectId", min_length=1)
    status: Literal["SUCCEEDED", "FAILED"]
    tool_trace: tuple[ProjectInvestigationToolTrace, ...] = Field(alias="toolTrace", min_length=1)
    facts: dict[str, tuple[Any, ...]] = Field(default_factory=dict)
    presentations: dict[str, tuple[dict[str, Any], ...]] = Field(default_factory=dict)
    citations: tuple[dict[str, Any], ...] = ()
    # 仅用于读取历史 checkpoint。新项目调查不再在子 Agent 阶段导出文件；文件
    # 只能由主 Agent 最终正文的交付步骤创建。
    exports: tuple[dict[str, Any], ...] = ()
    data_gaps: tuple[str, ...] = Field(default=(), alias="dataGaps")
    snapshot_at: str | None = Field(default=None, alias="snapshotAt")
    # 兼容已持久化的旧回执。新回执不会写入，主图也不会读取或转交它。
    narrative: str | None = Field(default=None, max_length=1800)


_PROJECT_INVESTIGATION_TOOLS = frozenset({
    "analyze_project", "get_project_snapshot", "get_project_tasks",
    "get_project_activity", "get_project_documents", "search_project_knowledge",
})


def _compact_project_task(value: Any) -> Any:
    """把任务原始行投影为主 Agent 汇总真正需要的字段。

    参数：
        value：Java Project Provider 返回的一条任务记录。

    返回：保留任务编号、名称、负责人、完成/优先级/截止时间和最近修改时间的
    小对象。原始描述、创建修改人详情、参与人列表等仍保留在项目子 Agent 的
    工具 checkpoint 中，不应跨 Agent 重复注入模型上下文。
    """
    if not isinstance(value, dict):
        return value
    meta = value.get("metaInfo") if isinstance(value.get("metaInfo"), dict) else {}
    owner = value.get("ownerUserInfo") if isinstance(value.get("ownerUserInfo"), dict) else {}
    return {
        "taskID": value.get("taskID"),
        "name": value.get("name"),
        "ownerUser": value.get("ownerUser"),
        "ownerName": owner.get("nickName") or owner.get("name"),
        "status": value.get("status"),
        "taskCheck": meta.get("taskCheck"),
        "taskLevel": meta.get("taskLevel"),
        "timeTo": meta.get("timeTo"),
        "modifyTime": value.get("modifyTime"),
    }


def _compact_project_activity(value: Any) -> Any:
    """投影项目动态，防止完整历史日志占满最终总结上下文。"""
    if not isinstance(value, dict):
        return value
    return {
        "id": value.get("id"),
        "taskID": value.get("taskID"),
        "userID": value.get("userID"),
        "logType": value.get("logType"),
        "createdAt": value.get("createdAt"),
        "description": value.get("description"),
    }


def _compact_project_document(value: Any) -> Any:
    """投影资料元信息，不向父 Agent 传递无关存储字段。"""
    if not isinstance(value, dict):
        return value
    return {
        "fileID": value.get("fileID"),
        "name": value.get("name"),
        "mimeType": value.get("mimeType"),
        "modifiedAt": value.get("modifiedAt"),
        "version": value.get("version"),
        "supported": value.get("supported"),
    }


def _compact_project_analysis(value: Any) -> Any:
    """生成项目分析的跨 Agent 事实投影。

    ``analyze_project`` 原始响应包含完整任务树和全部活动日志，适合项目子 Agent
    在同一 ReAct 回合继续调查，却不适合主 Agent 最终排版。这里保留统计、风险、
    成员和可追溯的轻量任务/动态/资料字段，使最终回复仍有事实依据，且不因大段
    重复 JSON 增加模型生成等待。
    """
    if not isinstance(value, dict):
        return value
    result = dict(value)
    if isinstance(value.get("tasks"), list):
        result["tasks"] = [_compact_project_task(item) for item in value["tasks"]]
    if isinstance(value.get("activity"), list):
        # 当前页面只需说明近期活跃依据；完整日志由项目动态卡片按需加载。
        result["activity"] = [_compact_project_activity(item) for item in value["activity"][:12]]
    if isinstance(value.get("documents"), list):
        result["documents"] = [_compact_project_document(item) for item in value["documents"]]
    return result


def _project_parent_fact(tool_name: str, value: Any) -> Any:
    """按工具类型生成可跨 Agent 传递的只读事实投影。"""
    if tool_name == "analyze_project":
        return _compact_project_analysis(value)
    if tool_name == "get_project_tasks" and isinstance(value, dict):
        result = dict(value)
        for key in ("items", "tasks", "records"):
            if isinstance(value.get(key), list):
                result[key] = [_compact_project_task(item) for item in value[key]]
        return result
    if tool_name == "get_project_activity" and isinstance(value, dict):
        result = dict(value)
        for key in ("items", "activity", "records"):
            if isinstance(value.get(key), list):
                result[key] = [_compact_project_activity(item) for item in value[key][:12]]
        return result
    if tool_name == "get_project_documents" and isinstance(value, dict):
        result = dict(value)
        for key in ("items", "documents", "records"):
            if isinstance(value.get(key), list):
                result[key] = [_compact_project_document(item) for item in value[key]]
        return result
    return value


def project_investigation_receipt_from_tool_messages(
    messages: list[Any], *, plan_id: str, project_id: str,
) -> DelegatedProjectInvestigationReceipt | None:
    """从一次子 Agent 调查的全部项目工具结果构造强类型回执。

    子 Agent 的最终自由文本不会进入跨 Agent 回执。事实、权限、引用和导出文件
    都只从真实 ToolResponse 构造；主图需要生成资料语义结论时，会以这个回执的
    受控事实投影作为唯一输入。
    """
    trace: list[ProjectInvestigationToolTrace] = []
    facts: dict[str, list[Any]] = {}
    presentations: dict[str, list[dict[str, Any]]] = {}
    citations: list[dict[str, Any]] = []
    exports: list[dict[str, Any]] = []
    data_gaps: list[str] = []
    snapshot_at: str | None = None
    for message in messages:
        name = str(getattr(message, "name", "") or "")
        if name not in _PROJECT_INVESTIGATION_TOOLS:
            continue
        try:
            result = ToolResponse.model_validate_json(str(getattr(message, "content", "") or ""))
        except (TypeError, ValueError):
            continue
        if result.ok:
            trace.append(ProjectInvestigationToolTrace(tool=name, status="SUCCEEDED"))
            # 父图只接收完成总结所需的投影；子 Agent 原始工具结果仍存在于
            # 自己的 checkpoint，便于审计和后续工具调用，不会被这一步丢弃。
            facts.setdefault(name, []).append(_project_parent_fact(name, result.data))
            if isinstance(result.presentation, dict):
                presentations.setdefault(name, []).append(result.presentation)
            if name == "search_project_knowledge" and isinstance(result.data, dict):
                citations.extend(item for item in result.data.get("hits") or [] if isinstance(item, dict))
            if name == "analyze_project" and isinstance(result.data, dict):
                kpis = result.data.get("kpis") if isinstance(result.data.get("kpis"), dict) else {}
                snapshot_at = str(result.data.get("asOf") or kpis.get("asOf") or "").strip() or snapshot_at
        else:
            error = result.error
            code = str(error.code) if error is not None else "PROJECT_TOOL_FAILED"
            trace.append(ProjectInvestigationToolTrace(tool=name, status="FAILED", errorCode=code))
            data_gaps.append(str(error.message) if error is not None else f"{name} 未返回可用结果。")
    if not trace:
        return None
    return DelegatedProjectInvestigationReceipt(
        planId=plan_id,
        projectId=str(project_id),
        status="SUCCEEDED" if facts else "FAILED",
        toolTrace=tuple(trace),
        facts={name: tuple(values) for name, values in facts.items()},
        presentations={name: tuple(values) for name, values in presentations.items()},
        citations=tuple(citations),
        exports=tuple(exports),
        dataGaps=tuple(data_gaps),
        snapshotAt=snapshot_at,
    )


def execution_receipt_from_tool_response(
    response: ToolResponse,
    *,
    plan_id: str,
    executor_tool: str,
) -> DelegatedExecutionReceipt:
    """把已解析的工具响应转换成可传给主图的通用回执。

    参数：
        response：真实 executor 返回且已通过 ToolResponse 契约校验的结果。
        plan_id：本次中央编译计划的唯一编号。
        executor_tool：执行该计划的唯一 executor 工具名。
    """
    if response.ok:
        return DelegatedExecutionReceipt(
            planId=plan_id,
            executorTool=executor_tool,
            result=response.data,
            presentation=response.presentation,
        )
    error = response.error
    return DelegatedExecutionReceipt(
        planId=plan_id,
        executorTool=executor_tool,
        status="FAILED",
        message=str(error.message if error is not None else "执行器未返回可用结果。"),
        errorCode=str(error.code) if error is not None else "EXECUTOR_RESPONSE_FAILED",
        retryable=bool(error.retryable) if error is not None and error.retryable is not None else False,
    )


def _draft_identity(data: dict[str, Any]) -> tuple[str, str, str, str] | None:
    """从真实工具结果抽取确认边界四元组，不接受模型自由文本。"""
    facts = data.get("facts") if isinstance(data.get("facts"), dict) else {}
    draft = data.get("draft") if isinstance(data.get("draft"), dict) else {}
    operation_id = str(data.get("operationId") or facts.get("operationId") or draft.get("operationId") or "").strip()
    draft_id = str(data.get("draftId") or facts.get("draftId") or draft.get("draftId") or "").strip()
    approval_id = str(data.get("approvalId") or facts.get("approvalId") or draft.get("approvalId") or "").strip()
    token = str(data.get("confirmation_token") or data.get("confirmationToken") or facts.get("confirmation_token") or draft_id).strip()
    return (operation_id, draft_id, approval_id, token) if all((operation_id, draft_id, approval_id, token)) else None


def draft_receipt_from_tool_response(
    response: ToolResponse,
    *,
    domain: str,
    operation: str,
) -> DelegatedPersonalScheduleDraftReceipt | DelegatedPartyFileDraftReceipt | DelegatedApprovalDraftReceipt | None:
    """按领域把真实草稿结果提升为可触发 HITL 的强类型回执。

    非草稿结果一律返回 ``None``，调用方再降级为通用执行回执。这样“成功执行”
    不会被误当成“允许创建确认卡”。
    """
    if not response.ok or not isinstance(response.data, dict):
        return None
    data = response.data
    # 批量审批预览没有 draftId/approvalId，而是以 previewId 作为同一待确认
    # 对象的稳定标识；先在这里规范化，避免通用回执吞掉这个确认边界。
    batch_preview = domain == "approval" and str(operation or "").upper() == "BATCH_ACTION"
    if batch_preview:
        preview_id = str(data.get("previewId") or "").strip()
        operation_id = str(data.get("operationId") or "").strip()
        token = str(data.get("confirmationToken") or "").strip()
        identity = (operation_id, preview_id, preview_id, token) if all((operation_id, preview_id, token)) else None
    else:
        identity = _draft_identity(data)
    if identity is None:
        return None
    operation_id, draft_id, approval_id, token = identity
    if domain == "schedule" and str(data.get("status") or "").upper() == "DRAFT_READY":
        return DelegatedPersonalScheduleDraftReceipt(
            operationId=operation_id, draftId=draft_id, approvalId=approval_id, confirmationToken=token,
        )
    if domain == "party_file" and bool(data.get("requires_confirmation")):
        return DelegatedPartyFileDraftReceipt(
            operationId=operation_id, draftId=draft_id, approvalId=approval_id, confirmationToken=token,
        )
    if domain == "approval":
        confirmation_type = {
            # ActionCatalog 中“发起审批申请”使用 CREATE；工作流内部才转换为
            # REQUEST。跨 Agent 契约以编译计划的操作名称为准。
            "CREATE": "request", "REQUEST": "request", "WITHDRAW": "request",
            "TASK_ACTION": "task", "BATCH_ACTION": "batch",
        }.get(str(operation or "").upper())
        if confirmation_type is None:
            return None
        # 批量预览以 previewId 同时充当 approval/draft 标识，且必须有自己的令牌。
        return DelegatedApprovalDraftReceipt(
            confirmationType=confirmation_type, operationId=operation_id,
            draftId=draft_id, approvalId=approval_id, confirmationToken=token,
        )
    return None


def meeting_workflow_receipt_from_workflow_message(
    message: Any,
    *,
    plan_id: str,
) -> DelegatedMeetingDraftReceipt | DelegatedExecutionReceipt | None:
    """仅从会议工作流 ToolMessage 构建严格草稿或正常流程结果回执。

    ``DRAFT_READY`` 必须继续走专用草稿回执，确保确认卡边界不被放宽；其余
    正常流程结果（如 ``NEEDS_INPUT``）走通用回执，让主 Agent 基于真实缺项
    继续澄清，而不是把它误判成系统错误。
    """
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    if not isinstance(content, str):
        return None
    try:
        envelope = ToolResponse.model_validate_json(content)
    except (ValidationError, TypeError, ValueError):
        return None
    if not envelope.ok:
        return execution_receipt_from_tool_response(
            envelope,
            plan_id=plan_id,
            executor_tool="run_meeting_booking_workflow",
        )
    if not isinstance(envelope.data, dict):
        return None
    try:
        outcome = MeetingBookingWorkflowOutcome.model_validate(envelope.data)
    except ValidationError:
        return None
    if outcome.status == "DRAFT_READY":
        try:
            return DelegatedMeetingDraftReceipt(
                operationId=outcome.operation_id or "",
                draftId=outcome.draft_id or "",
                approvalId=outcome.approval_id or "",
                confirmationToken=outcome.confirmation_token or "",
            )
        except ValidationError:
            return None
    return DelegatedExecutionReceipt(
        planId=plan_id,
        executorTool="run_meeting_booking_workflow",
        status=outcome.status,
        message=outcome.message,
        facts=outcome.facts,
        errorCode=outcome.error_code,
        retryable=outcome.retryable,
    )


def parse_meeting_draft_receipt(content: Any) -> DelegatedMeetingDraftReceipt | None:
    """解析会议子 Agent 返回的专用草稿回执。"""
    return _parse_draft_receipt(content, DelegatedMeetingDraftReceipt)


def _parse_draft_receipt(content: Any, receipt_type: type[BaseModel]) -> Any | None:
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    try:
        return receipt_type.model_validate(content)
    except (ValidationError, TypeError, ValueError):
        return None


def parse_personal_schedule_draft_receipt(content: Any) -> DelegatedPersonalScheduleDraftReceipt | None:
    return _parse_draft_receipt(content, DelegatedPersonalScheduleDraftReceipt)


def parse_party_file_draft_receipt(content: Any) -> DelegatedPartyFileDraftReceipt | None:
    return _parse_draft_receipt(content, DelegatedPartyFileDraftReceipt)


def parse_approval_draft_receipt(content: Any) -> DelegatedApprovalDraftReceipt | None:
    return _parse_draft_receipt(content, DelegatedApprovalDraftReceipt)


def parse_execution_receipt(content: Any) -> DelegatedExecutionReceipt | None:
    """解析通用子 Agent 回执；不接受普通叙述文本作为执行成功证明。"""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    try:
        return DelegatedExecutionReceipt.model_validate(content)
    except (ValidationError, TypeError, ValueError):
        return None


def parse_project_investigation_receipt(content: Any) -> DelegatedProjectInvestigationReceipt | None:
    """解析项目调查专用回执；普通子 Agent 文本一律不视为调查结果。"""
    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
    try:
        return DelegatedProjectInvestigationReceipt.model_validate(content)
    except (ValidationError, TypeError, ValueError):
        return None


def _short_text(value: Any, *, maximum: int) -> str:
    """将跨 Agent 证据压缩为有限长度的可见文本。"""

    text = str(value or "").strip()
    return text[:maximum]


def _project_analysis_model_facts(receipt: DelegatedProjectInvestigationReceipt) -> dict[str, Any]:
    """生成项目调查回执的主 Agent 可见事实投影。

    项目子 Agent 需要完整任务树、动态和资料元数据执行受控 ReAct；主 Agent 的
    职责只是根据已核验事实写面向用户的总结。两者的上下文需求不同，若把原始
    ``task`` 回执再次传给主模型，会同时造成延迟上升、来源 ID 泄露和“主 Agent
    重新计算 KPI”的风险。因此该投影是跨图通信的第二层契约：只保留最终说明
    所需的有限事实，不改变 checkpoint 中的原始回执。
    """

    analyses = receipt.facts.get("analyze_project") or ()
    analysis = analyses[-1] if analyses and isinstance(analyses[-1], dict) else {}
    project = analysis.get("project") if isinstance(analysis.get("project"), dict) else {}
    kpis = analysis.get("kpis") if isinstance(analysis.get("kpis"), dict) else {}
    risks = analysis.get("risks") if isinstance(analysis.get("risks"), list) else []
    members = analysis.get("members") if isinstance(analysis.get("members"), list) else []
    documents = analysis.get("documents") if isinstance(analysis.get("documents"), list) else []

    risk_facts = [
        {
            "severity": _short_text(item.get("severity"), maximum=24),
            "type": _short_text(item.get("type"), maximum=40),
            "taskName": _short_text(item.get("taskName"), maximum=120),
            "message": _short_text(item.get("message"), maximum=240),
        }
        for item in risks[:4]
        if isinstance(item, dict)
    ]
    member_facts = [
        {
            "name": _short_text(item.get("name"), maximum=80),
            "assigned": item.get("assigned"),
            "completed": item.get("completed"),
            "overdue": item.get("overdue"),
        }
        for item in members[:16]
        if isinstance(item, dict)
    ]
    document_facts = [
        {
            "name": _short_text(item.get("name"), maximum=160),
            "documentType": _short_text(item.get("documentType") or item.get("mimeType"), maximum=80),
            "supported": item.get("supported"),
        }
        for item in documents[:12]
        if isinstance(item, dict)
    ]
    citation_facts = [
        {
            "citationId": _short_text(item.get("citationId") or item.get("citation_id"), maximum=40),
            "sourceType": _short_text(item.get("sourceType"), maximum=40),
            "name": _short_text(item.get("name"), maximum=160),
            "section": _short_text(item.get("section"), maximum=120),
            "contentVersion": _short_text(item.get("contentVersion") or item.get("content_version"), maximum=128),
            "retrievalMethod": _short_text(item.get("retrievalMethod") or item.get("retrieval_method"), maximum=24),
            # Java 侧只输出受限摘录；content 仅作为旧回执兼容，不再把正文全量
            # 透传给主 Agent。
            "excerpt": _short_text(item.get("excerpt") or item.get("content"), maximum=280),
        }
        for item in receipt.citations[:5]
        if isinstance(item, dict)
    ]
    export_facts = [
        {
            "format": _short_text(item.get("format"), maximum=12).lower(),
            "filename": _short_text(item.get("filename"), maximum=200),
        }
        for item in receipt.exports
        if isinstance(item, dict)
    ]
    return {
        "schemaVersion": receipt.schema_version,
        "kind": receipt.kind,
        "domain": receipt.domain,
        "status": receipt.status,
        "toolTrace": [
            {
                "tool": item.tool,
                "status": item.status,
                "errorCode": item.error_code,
            }
            for item in receipt.tool_trace
        ],
        "facts": {
            "project": {"name": _short_text(project.get("name"), maximum=160)},
            # KPI 只能由 Java Project Provider 计算；主模型只可引用，不能按
            # 任务明细或自然语言自行重算。
            "kpis": {
                key: kpis.get(key)
                for key in (
                    "total", "completed", "overdue", "withoutOwner", "completionRate",
                    "manualProgress", "asOf",
                )
                if key in kpis
            },
            "risks": risk_facts,
            "members": member_facts,
            "documents": document_facts,
            "methodology": [
                _short_text(item, maximum=240)
                for item in (analysis.get("methodology") or [])[:5]
                if _short_text(item, maximum=240)
            ],
        },
        "knowledge": {"total": len(citation_facts), "citations": citation_facts},
        "exports": export_facts,
        "dataGaps": [_short_text(item, maximum=240) for item in receipt.data_gaps[:5]],
        "snapshotAt": receipt.snapshot_at,
    }


def model_visible_delegated_receipt(content: Any) -> dict[str, Any] | None:
    """返回可提交给父级模型的受控领域事实，未知回执保持原有处理。

    这不是把回执“摘要化后重新作为事实源”，而是明确区分：完整回执保留在
    checkpoint 供审计与程序消费；本函数输出仅是一次模型调用的输入视图。新增
    领域级多工具回执时应在这里登记对应投影，不能让其原始 ``task`` 内容穿透
    到父级提示词。
    """

    receipt = parse_project_investigation_receipt(content)
    if receipt is not None:
        return _project_analysis_model_facts(receipt)
    return None


__all__ = [
    "DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION",
    "DRAFT_RECEIPT_KIND", "EXECUTION_RECEIPT_KIND", "MEETING_DRAFT_RECEIPT_KIND",
    "PROJECT_INVESTIGATION_RECEIPT_KIND",
    "DelegatedApprovalDraftReceipt", "DelegatedPartyFileDraftReceipt",
    "DelegatedPersonalScheduleDraftReceipt",
    "DelegatedExecutionStatus",
    "DelegatedMeetingDraftReceipt",
    "DelegatedExecutionReceipt",
    "DelegatedProjectInvestigationReceipt", "ProjectInvestigationToolTrace",
    "execution_receipt_from_tool_response",
    "draft_receipt_from_tool_response",
    "meeting_workflow_receipt_from_workflow_message",
    "parse_execution_receipt",
    "parse_project_investigation_receipt", "project_investigation_receipt_from_tool_messages",
    "model_visible_delegated_receipt",
    "parse_approval_draft_receipt", "parse_party_file_draft_receipt",
    "parse_personal_schedule_draft_receipt",
    "parse_meeting_draft_receipt",
]
