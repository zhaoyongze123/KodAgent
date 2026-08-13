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


__all__ = [
    "DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION",
    "DRAFT_RECEIPT_KIND", "EXECUTION_RECEIPT_KIND", "MEETING_DRAFT_RECEIPT_KIND",
    "DelegatedApprovalDraftReceipt", "DelegatedPartyFileDraftReceipt",
    "DelegatedPersonalScheduleDraftReceipt",
    "DelegatedExecutionStatus",
    "DelegatedMeetingDraftReceipt",
    "DelegatedExecutionReceipt",
    "execution_receipt_from_tool_response",
    "draft_receipt_from_tool_response",
    "meeting_workflow_receipt_from_workflow_message",
    "parse_execution_receipt",
    "parse_approval_draft_receipt", "parse_party_file_draft_receipt",
    "parse_personal_schedule_draft_receipt",
    "parse_meeting_draft_receipt",
]
