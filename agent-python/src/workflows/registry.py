"""Central registry for deterministic workflow contracts.

The registry is deliberately small and local.  It is not a second routing
engine: the parent Agent may decide *when* to call a workflow, while this
module is the single source of truth for its name, schemas, feature flag and
confirmation boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from .contracts import ConfirmationPolicy, WorkflowContract


class WorkflowRegistry:
    def __init__(self, contracts: Iterable[WorkflowContract] = ()) -> None:
        self._contracts: dict[str, WorkflowContract] = {}
        for contract in contracts:
            self.register(contract)

    def register(self, contract: WorkflowContract, *, replace: bool = False) -> WorkflowContract:
        if not contract.workflow_type.strip():
            raise ValueError("工作流类型不能为空")
        if not contract.tool_name.strip():
            raise ValueError(f"工作流 {contract.workflow_type} 的 Tool 名称不能为空")
        if contract.workflow_type in self._contracts and not replace:
            raise ValueError(f"工作流已注册: {contract.workflow_type}")
        self._contracts[contract.workflow_type] = contract
        return contract

    def get(self, workflow_type: str) -> WorkflowContract | None:
        return self._contracts.get(workflow_type)

    def require(self, workflow_type: str) -> WorkflowContract:
        contract = self.get(workflow_type)
        if contract is None:
            raise KeyError(f"未注册工作流: {workflow_type}")
        return contract

    def enabled(self, workflow_type: str, *, environ: dict[str, str] | None = None) -> bool:
        return self.require(workflow_type).is_enabled(environ)

    def list(self, *, enabled_only: bool = False, environ: dict[str, str] | None = None) -> list[WorkflowContract]:
        values = list(self._contracts.values())
        if enabled_only:
            values = [item for item in values if item.is_enabled(environ)]
        return values

    def __contains__(self, workflow_type: str) -> bool:
        return workflow_type in self._contracts

    def __iter__(self) -> Iterator[WorkflowContract]:
        return iter(self._contracts.values())


def _meeting_booking_contract() -> WorkflowContract:
    from .meeting_booking.contracts import MeetingBookingWorkflowInput, MeetingBookingWorkflowOutcome

    # Import the graph lazily.  Registry discovery must remain cheap and must
    # not initialize LangGraph or issue any external request at import time.
    def runner(**kwargs: Any) -> Any:
        from .meeting_booking.graph import run_meeting_booking_workflow

        return run_meeting_booking_workflow(**kwargs)

    return WorkflowContract(
        workflow_type="meeting_booking",
        tool_name="run_meeting_booking_workflow",
        input_schema=MeetingBookingWorkflowInput,
        outcome_schema=MeetingBookingWorkflowOutcome,
        confirmation_policy=ConfirmationPolicy(
            required=True,
            tool_name="confirm_meeting_booking",
            card_type="meeting_booking",
        ),
        feature_flag="OA_AGENT_MEETING_WORKFLOW_V2",
        # 会议预约的唯一写入入口已经是该工作流：它会固化请求、检查可用性、
        # 生成草稿。默认启用，避免子 Agent 落回可由模型自由拼接低层工具的
        # 旧链路；仍可显式设置 false 作为紧急回滚开关。
        feature_flag_default=True,
        version="1",
        runner=runner,
        description="按固定顺序整理会议预约、检查冲突并生成待确认草稿",
    )


def _personal_schedule_contract() -> WorkflowContract:
    from .personal_schedule.contracts import PersonalScheduleWorkflowInput, PersonalScheduleWorkflowOutcome

    def runner(**kwargs: Any) -> Any:
        from .personal_schedule.graph import run_personal_schedule_workflow
        return run_personal_schedule_workflow(**kwargs)

    return WorkflowContract(
        workflow_type="personal_schedule",
        tool_name="run_personal_schedule_workflow",
        input_schema=PersonalScheduleWorkflowInput,
        outcome_schema=PersonalScheduleWorkflowOutcome,
        confirmation_policy=ConfirmationPolicy(
            required=True,
            tool_name="confirm_personal_schedule",
            card_type="personal_schedule",
        ),
        feature_flag="OA_AGENT_SCHEDULE_WORKFLOW_V2",
        # 与会议预约一致：个人日程的创建、修改、取消都必须经过固定工作流。
        # 保留显式 false 作为紧急回滚，而不是默认让模型拼接查询和草稿工具。
        feature_flag_default=True,
        version="1",
        runner=runner,
        description="按固定顺序校验个人日程并生成待确认草稿",
    )


def _party_file_contract(workflow_type: str, tool_name: str, description: str, feature_flag: str = "OA_AGENT_PARTY_KNOWLEDGE_V1") -> WorkflowContract:
    def runner(**kwargs: Any) -> Any:
        from .party_files.graph import (
            run_party_file_approval_check_workflow,
            run_party_file_compare_workflow,
            run_party_file_understanding_workflow,
        )
        if workflow_type == "party_file_compare":
            function = run_party_file_compare_workflow
        elif workflow_type == "party_file_approval_check":
            function = run_party_file_approval_check_workflow
        else:
            function = run_party_file_understanding_workflow
        return function(**kwargs)
    return WorkflowContract(
        workflow_type=workflow_type, tool_name=tool_name,
        input_schema=None, outcome_schema=None, confirmation_policy=ConfirmationPolicy(required=False),
        feature_flag=feature_flag, feature_flag_default=False,
        version="1", runner=runner, description=description,
    )


workflow_registry = WorkflowRegistry([
    _meeting_booking_contract(), _personal_schedule_contract(),
    _party_file_contract("party_file_understanding", "run_party_file_understanding", "读取授权党务文件并返回带引用的内容证据"),
    _party_file_contract("party_file_compare", "run_party_file_compare", "对比两个授权党务文件版本并返回确定性差异", "OA_AGENT_PARTY_COMPARE_V1"),
    _party_file_contract("party_file_approval_check", "check_approval_against_party_file", "按授权制度条款校验审批材料完整性", "OA_AGENT_PARTY_APPROVAL_CHECK_V1"),
])


def get_workflow(workflow_type: str) -> WorkflowContract:
    """Short alias used by runtime/tool adapters."""
    return workflow_registry.require(workflow_type)


def confirmation_route(workflow_type: str) -> dict[str, Any] | None:
    """Return the registered HITL bridge for a task type, if any.

    Middleware uses this lookup instead of copying a growing task-type to
    tool-name mapping.  A future schedule/approval workflow only needs a
    registry entry; its domain context validation remains in its own bridge.
    """
    for contract in workflow_registry:
        if contract.workflow_type == workflow_type and contract.confirmation_policy.required:
            return {
                "workflowType": contract.workflow_type,
                "toolName": contract.confirmation_policy.tool_name,
                "cardType": contract.confirmation_policy.card_type,
                "version": contract.version,
            }
    return None


__all__ = ["WorkflowRegistry", "confirmation_route", "get_workflow", "workflow_registry"]
