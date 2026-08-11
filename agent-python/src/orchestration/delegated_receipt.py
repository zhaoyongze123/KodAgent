"""Trusted result envelopes passed from a domain child to the root graph.

DeepAgents' generic ``task`` transport normally returns the child's final AI
text.  That text is presentation, not a business contract.  Draft-producing
workflows therefore use this narrow receipt at the child/root boundary so the
root approval projector never has to infer an Operation from model prose.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..tools.common import ToolResponse
from ..workflows.meeting_booking.contracts import MeetingBookingWorkflowOutcome


DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION = 1
MEETING_DRAFT_RECEIPT_KIND = "execution_result"


class DelegatedMeetingDraftReceipt(BaseModel):
    """Code-owned proof that the meeting child produced one pending draft."""

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


class DelegatedExecutionReceipt(BaseModel):
    """所有普通领域委托共用的完成凭据。

    子 Agent 仅仅返回 ``task`` 并不说明已执行成功：它可能只调用了 helper，
    或收到了一条授权拒绝。这个回执只由真正 executor 的成功 ToolMessage 生成，
    主 Agent 用它而不是模型文本判断任务完成。
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: Literal[DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION] = Field(
        default=DELEGATED_EXECUTION_RECEIPT_SCHEMA_VERSION, alias="schemaVersion"
    )
    kind: Literal[MEETING_DRAFT_RECEIPT_KIND] = MEETING_DRAFT_RECEIPT_KIND
    plan_id: str = Field(alias="planId", min_length=1)
    executor_tool: str = Field(alias="executorTool", min_length=1)
    status: Literal["SUCCEEDED"] = "SUCCEEDED"


def meeting_draft_receipt_from_workflow_message(message: Any) -> DelegatedMeetingDraftReceipt | None:
    """Build a receipt only from the deterministic workflow ToolMessage.

    The message originates in LangChain's tool node.  We intentionally do not
    look at an AIMessage, a task description, or arbitrary historical state.
    """
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    if not isinstance(content, str):
        return None
    try:
        envelope = ToolResponse.model_validate_json(content)
    except (ValidationError, TypeError, ValueError):
        return None
    if not envelope.ok or not isinstance(envelope.data, dict):
        return None
    try:
        outcome = MeetingBookingWorkflowOutcome.model_validate(envelope.data)
    except ValidationError:
        return None
    if outcome.status != "DRAFT_READY":
        return None
    try:
        return DelegatedMeetingDraftReceipt(
            operationId=outcome.operation_id or "",
            draftId=outcome.draft_id or "",
            approvalId=outcome.approval_id or "",
            confirmationToken=outcome.confirmation_token or "",
        )
    except ValidationError:
        return None


def parse_meeting_draft_receipt(content: Any) -> DelegatedMeetingDraftReceipt | None:
    """Validate a serialized child receipt received by the root task tool."""
    if not isinstance(content, str):
        return None
    try:
        payload = json.loads(content)
        return DelegatedMeetingDraftReceipt.model_validate(payload)
    except (ValidationError, TypeError, ValueError, json.JSONDecodeError):
        return None


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
    "MEETING_DRAFT_RECEIPT_KIND",
    "DelegatedMeetingDraftReceipt",
    "DelegatedExecutionReceipt",
    "meeting_draft_receipt_from_workflow_message",
    "parse_execution_receipt",
    "parse_meeting_draft_receipt",
]
