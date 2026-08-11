"""审批写操作的统一模型入口。

本文件不实现审批业务；它只把主 Agent 编译后的操作类型分派给既有的
草稿/预览工具。这样审批子 Agent 不必在多个写工具之间自行选择。
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from langchain.tools import InjectedToolCallId, tool
from pydantic import Field

from ..approval.actions import preview_approval_batch_action, preview_approval_task_action
from ..approval.requests import create_approval_withdraw_draft, create_generic_approval_request_draft
from ..common import ToolResponse, tool_failure


def _tool_response(result: Any) -> ToolResponse:
    """兼容被运行时契约包装前后的既有工具返回值。"""
    if isinstance(result, ToolResponse):
        return result
    if isinstance(result, str):
        try:
            return ToolResponse.model_validate_json(result)
        except ValueError:
            pass
    if isinstance(result, dict):
        try:
            return ToolResponse.model_validate(result)
        except ValueError:
            pass
    return tool_failure("APPROVAL_WORKFLOW_RESPONSE_INVALID", "审批草稿服务返回了无效结果")


@tool
def run_approval_write_workflow(
    operation: Annotated[
        Literal["REQUEST", "WITHDRAW", "TASK_ACTION", "BATCH_ACTION"],
        Field(description="审批操作：REQUEST 发起申请，WITHDRAW 撤回，TASK_ACTION 处理单条待办，BATCH_ACTION 批量处理待办。"),
    ],
    process_definition: Annotated[str, Field(description="审批模板定义标识；仅 REQUEST 使用，必须来自可发起模板查询结果。")] = "",
    variables: Annotated[dict[str, Any] | None, Field(description="审批表单字段；仅 REQUEST 使用，字段由模板定义。")] = None,
    start_user_select_assignees: Annotated[dict[str, list[int]] | None, Field(description="发起人指定的审批人映射；仅 REQUEST 使用。")] = None,
    process_instance_id: Annotated[str, Field(description="要撤回的流程实例编号；仅 WITHDRAW 使用。")] = "",
    task_id: Annotated[str, Field(description="要处理的待办编号；仅 TASK_ACTION 使用。")] = "",
    task_ids: Annotated[list[str] | None, Field(description="要批量处理的待办编号列表；仅 BATCH_ACTION 使用。")] = None,
    action: Annotated[str, Field(description="待办动作：APPROVE 或 REJECT；处理待办时必填。")] = "",
    reason: Annotated[str, Field(description="撤回或驳回理由。REJECT 和 WITHDRAW 通常必填。")] = "",
    criteria: Annotated[dict[str, Any] | None, Field(description="批量筛选条件；仅 BATCH_ACTION 使用，不能与 task_ids 同时提供。")] = None,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """审批子 Agent 的唯一写入入口；只生成预览或草稿，绝不直接提交审批。"""
    if operation == "REQUEST":
        return _tool_response(create_generic_approval_request_draft.func(
            process_definition=process_definition,
            variables=variables,
            start_user_select_assignees=start_user_select_assignees,
            tool_call_id=tool_call_id,
        ))
    if operation == "WITHDRAW":
        return _tool_response(create_approval_withdraw_draft.func(
            process_instance_id=process_instance_id, reason=reason, tool_call_id=tool_call_id,
        ))
    if operation == "TASK_ACTION":
        return _tool_response(preview_approval_task_action.func(
            task_id=task_id, action=action, reason=reason, tool_call_id=tool_call_id,
        ))
    batch_criteria = dict(criteria or {})
    return _tool_response(preview_approval_batch_action.func(
        action=action, reason=reason, task_ids=task_ids, tool_call_id=tool_call_id,
        **batch_criteria,
    ))
