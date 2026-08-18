"""Contracts for domain sub-agents.

Sub-agents are executors, not secondary routers.  Each one therefore has a
declared capability, tool allow-list, result shape and recovery policy.  The
registry validates these declarations at graph construction so a typo or an
empty tool projection fails at startup instead of during a user request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..orchestration.execution_contracts import validate_execution_contracts


@dataclass(frozen=True)
class DomainAgentContract:
    name: str
    capability_id: str
    result_contract: str
    failure_policy: str
    write_boundary: str
    skill_id: str | None = None


DOMAIN_AGENT_CONTRACTS: tuple[DomainAgentContract, ...] = (
    DomainAgentContract(
        "approvals_agent", "approval_write", "facts|clarification|approval_card|error", "return_structured_error", "draft_then_hitl", "approval.operations",
    ),
    DomainAgentContract(
        "meeting_rooms_agent", "meeting", "facts|clarification|approval_card|error", "replan_on_conflict", "draft_then_hitl", "meeting.booking",
    ),
    DomainAgentContract(
        "schedules_agent", "schedule", "facts|clarification|approval_card|error", "replan_on_conflict", "draft_then_hitl", "schedule.personal",
    ),
    DomainAgentContract(
        "party_files_agent", "party_file", "facts|clarification|citation|error", "return_structured_error", "read_only_parent_owns_writes", "party-file.operations",
    ),
    DomainAgentContract(
        "projects_agent", "project", "facts|clarification|citation|report|error", "return_structured_error", "read_only_no_project_mutation", "project.analysis",
    ),
)


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or "").strip()


def validate_subagent_specs(
    specs: list[dict[str, Any]], *, required_names: set[str] | None = None,
    validate_execution: bool = True,
) -> list[dict[str, Any]]:
    """Validate and enrich the dict shape consumed by DeepAgents."""
    contracts = {item.name: item for item in DOMAIN_AGENT_CONTRACTS}
    seen: set[str] = set()
    enriched: list[dict[str, Any]] = []
    for spec in specs:
        name = str(spec.get("name") or "").strip()
        if not name:
            raise RuntimeError("子 Agent 缺少 name")
        if name in seen:
            raise RuntimeError(f"子 Agent 重复注册: {name}")
        seen.add(name)
        contract = contracts.get(name)
        if contract is None:
            raise RuntimeError(f"子 Agent 未登记领域契约: {name}")
        if not str(spec.get("description") or "").strip():
            raise RuntimeError(f"子 Agent 缺少 description: {name}")
        if not str(spec.get("system_prompt") or "").strip():
            raise RuntimeError(f"子 Agent 缺少 system_prompt: {name}")
        tools = list(spec.get("tools") or [])
        names = [_tool_name(tool) for tool in tools]
        if not tools or any(not item for item in names):
            raise RuntimeError(f"子 Agent 工具目录为空或包含匿名工具: {name}")
        if len(names) != len(set(names)):
            raise RuntimeError(f"子 Agent 工具重复注册: {name}")
        item = dict(spec)
        item["contract"] = {
            "capabilityId": contract.capability_id,
            "resultContract": contract.result_contract,
            "failurePolicy": contract.failure_policy,
            "writeBoundary": contract.write_boundary,
            "toolNames": names,
        }
        item["domainPlanner"] = {
            "capabilityId": contract.capability_id,
            "agentName": contract.name,
            "skillId": contract.skill_id,
            "role": "domain_fallback_executor",
            "actionSource": "action_catalog",
            "writeBoundary": contract.write_boundary,
        }
        enriched.append(item)
    # 只做结构形状校验的单元测试/离线调用不会要求传入全部领域实现；真正的
    # registry 启动校验仍默认要求 DOMAIN_AGENT_CONTRACTS 全量落地。这样新增只读
    # 领域不会破坏只关注某一个旧领域的通用 fixture，同时不会放松生产启动检查。
    expected = required_names if required_names is not None else (
        {item.name for item in DOMAIN_AGENT_CONTRACTS} if validate_execution else set()
    )
    missing = expected - seen
    if missing:
        raise RuntimeError(f"子 Agent 领域契约未注册实现: {', '.join(sorted(missing))}")
    # 在 DeepAgents 真正创建子 Agent 前检查执行闭包。这样“主 Agent 已编译，
    # 子 Agent 却没有工具”的错误会在启动时失败，而不是用户请求时才出现。
    if validate_execution:
        validate_execution_contracts({
            item["name"]: set(item["contract"]["toolNames"])
            for item in enriched
        })
    return enriched


__all__ = ["DOMAIN_AGENT_CONTRACTS", "DomainAgentContract", "validate_subagent_specs"]
