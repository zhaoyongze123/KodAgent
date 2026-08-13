"""中央执行契约：连接编译器、领域子 Agent 与工具授权边界。

文件职责：声明每一个已经进入 ActionCatalog 的执行工具由哪个子 Agent
负责、是否受 workflow 开关控制，以及执行前允许哪些“安全只读核验”工具。
这里保存的是稳定的领域能力事实；本次请求的动态数据仍只在 WorkOrder 中。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..tools.common.contracts import TOOL_CONTRACTS
from ..workflows.registry import workflow_registry


HelperMode = Literal["inherit_domain_default", "explicit"]


@dataclass(frozen=True)
class ExecutionContract:
    """一个编译执行器的稳定契约。

    ``owner_agent``：真正执行该工具的唯一领域子 Agent。
    ``workflow_type``：非空时表示该工具受 workflow feature flag 控制。
    ``helper_mode``：默认继承领域安全核验工具；少数动作可显式覆盖。
    ``allowed_helper_tools``：仅在 explicit 模式下生效，且必须全部只读。
    """

    owner_agent: str
    executor_tool: str
    workflow_type: str | None = None
    helper_mode: HelperMode = "inherit_domain_default"
    allowed_helper_tools: tuple[str, ...] = ()

    def is_available(self) -> bool:
        """返回当前部署是否允许编译并派发这个执行器。"""
        return self.workflow_type is None or workflow_registry.enabled(self.workflow_type)

    def helper_tools(self) -> tuple[str, ...]:
        """返回本执行器可用于核验的只读工具，不能包含另一个写执行器。"""
        if self.helper_mode == "explicit":
            return self.allowed_helper_tools
        return DOMAIN_DEFAULT_HELPERS.get(self.owner_agent, ())


# 领域默认核验集只声明一次。它不是“本领域全部 read-only 工具”的自动集合：
# 读取详情也可能产生已读记录、暴露编辑数据或成本很高，因此只有可安全复核
# 编译事实的工具才能进入这里。
DOMAIN_DEFAULT_HELPERS: dict[str, tuple[str, ...]] = {
    "approvals_agent": (
        "list_startable_approval_types", "preview_approval_request",
        "list_my_approval_applications", "get_my_approval_application",
        "list_my_approval_history", "list_my_pending_approvals",
        "search_my_pending_approvals", "analyze_my_pending_approvals",
        "run_approval_query_plan", "get_approval_task_detail",
    ),
    "meeting_rooms_agent": (
        "list_my_meeting_bookings", "get_my_meeting_booking",
        "list_available_meeting_rooms", "search_meeting_attendees",
        "get_current_meeting_user", "get_meeting_attendees_calendar",
        "check_meeting_room_conflict", "check_meeting_availability",
        "check_meeting_availability_batch", "prepare_meeting_booking_request",
    ),
    "schedules_agent": (
        "get_my_calendar", "find_calendar_conflicts", "get_personal_schedule",
    ),
    "party_files_agent": (
        "search_party_files", "execute_party_file_metadata_plan",
        "search_party_knowledge", "list_party_file_categories",
    ),
}


def _contracts(owner_agent: str, *tools: str, workflow_tools: dict[str, str] | None = None) -> tuple[ExecutionContract, ...]:
    """用紧凑写法登记同一领域的多个执行器，避免复制 owner 信息。"""
    workflow_tools = workflow_tools or {}
    return tuple(
        ExecutionContract(owner_agent, tool, workflow_tools.get(tool))
        for tool in tools
    )


# 这是替代 domain_dispatch 中两张手工映射表的唯一执行器目录。确认类工具
# 故意不在其中：它们属于主 Agent 的 HITL 控制面，不能被子 Agent 派发。
EXECUTION_CONTRACTS: tuple[ExecutionContract, ...] = (
    *_contracts(
        "approvals_agent",
        "run_approval_query_plan", "analyze_my_pending_approvals",
        "list_my_approval_applications", "get_my_approval_application",
        "list_my_approval_history", "run_approval_write_workflow", "approval_report",
    ),
    *_contracts(
        "meeting_rooms_agent",
        "list_my_meeting_bookings", "get_my_meeting_booking", "meeting_report",
        "run_meeting_booking_workflow",
        workflow_tools={"run_meeting_booking_workflow": "meeting_booking"},
    ),
    *_contracts(
        "schedules_agent",
        "get_my_calendar", "get_personal_schedule", "schedule_report",
        "run_personal_schedule_workflow",
        workflow_tools={"run_personal_schedule_workflow": "personal_schedule"},
    ),
    *_contracts(
        "party_files_agent",
        "execute_party_file_metadata_plan", "search_party_knowledge",
        "get_party_file_attachments", "run_party_file_compare",
        "check_approval_against_party_file", "party_file_report",
        "run_party_file_write_workflow",
        workflow_tools={
            "run_party_file_compare": "party_file_compare",
            "check_approval_against_party_file": "party_file_approval_check",
        },
    ),
)

_BY_EXECUTOR = {item.executor_tool: item for item in EXECUTION_CONTRACTS}
if len(_BY_EXECUTOR) != len(EXECUTION_CONTRACTS):  # import-time programmer error
    raise RuntimeError("执行契约存在重复 executor_tool")


def contract_for_executor(executor_tool: str | None) -> ExecutionContract | None:
    """按编译器选出的工具名称返回唯一执行契约。"""
    return _BY_EXECUTOR.get(str(executor_tool or "").strip())


def allowed_tools_for_executor(executor_tool: str | None) -> frozenset[str]:
    """返回本次 WorkOrder 可见/可调用的业务工具集合。"""
    contract = contract_for_executor(executor_tool)
    if contract is None:
        return frozenset()
    return frozenset((contract.executor_tool, *contract.helper_tools()))


def validate_execution_contracts(agent_tool_names: dict[str, set[str]]) -> None:
    """启动时验证“编译出的计划一定能由真实子 Agent 执行”。"""
    # ActionCatalog 是编译器的输入事实源；每个声明了 execution_tool 的动作
    # 都必须能在本目录找到唯一 owner，防止以后新增 Action 时漏改派发表。
    from .capabilities import ACTION_SPECS

    for action in ACTION_SPECS:
        if action.execution_tool and contract_for_executor(action.execution_tool) is None:
            raise RuntimeError(
                f"Action {action.action_id} 缺少执行契约: {action.execution_tool}"
            )
    for contract in EXECUTION_CONTRACTS:
        palette = agent_tool_names.get(contract.owner_agent)
        if palette is None:
            raise RuntimeError(f"执行契约引用了未注册子 Agent: {contract.owner_agent}")
        if contract.executor_tool not in palette:
            raise RuntimeError(
                f"执行器 {contract.executor_tool} 未暴露给 {contract.owner_agent}"
            )
        for helper_name in contract.helper_tools():
            if helper_name not in palette:
                raise RuntimeError(
                    f"核验工具 {helper_name} 未暴露给 {contract.owner_agent}"
                )
            tool_contract = TOOL_CONTRACTS.get(helper_name)
            if tool_contract is None or not tool_contract.read_only or tool_contract.side_effect:
                raise RuntimeError(f"核验工具必须是安全只读工具: {helper_name}")


__all__ = [
    "DOMAIN_DEFAULT_HELPERS", "EXECUTION_CONTRACTS", "ExecutionContract",
    "allowed_tools_for_executor", "contract_for_executor", "validate_execution_contracts",
]
