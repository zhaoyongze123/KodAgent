"""Contracts for domain sub-agents.

Sub-agents are executors, not secondary routers.  Each one therefore has a
declared capability, tool allow-list, result shape and recovery policy.  The
registry validates these declarations at graph construction so a typo or an
empty tool projection fails at startup instead of during a user request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainAgentContract:
    name: str
    capability_id: str
    result_contract: str
    failure_policy: str
    write_boundary: str


DOMAIN_AGENT_CONTRACTS: tuple[DomainAgentContract, ...] = (
    DomainAgentContract(
        "approvals_agent", "approval_write", "facts|clarification|approval_card|error", "return_structured_error", "draft_then_hitl",
    ),
    DomainAgentContract(
        "meeting_rooms_agent", "meeting", "facts|clarification|approval_card|error", "replan_on_conflict", "draft_then_hitl",
    ),
    DomainAgentContract(
        "schedules_agent", "schedule", "facts|clarification|approval_card|error", "replan_on_conflict", "draft_then_hitl",
    ),
    DomainAgentContract(
        "party_files_agent", "party_file", "facts|clarification|citation|error", "return_structured_error", "read_only_parent_owns_writes",
    ),
)


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or "").strip()


def validate_subagent_specs(
    specs: list[dict[str, Any]], *, required_names: set[str] | None = None,
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
        enriched.append(item)
    expected = required_names if required_names is not None else {item.name for item in DOMAIN_AGENT_CONTRACTS}
    missing = expected - seen
    if missing:
        raise RuntimeError(f"子 Agent 领域契约未注册实现: {', '.join(sorted(missing))}")
    return enriched


__all__ = ["DOMAIN_AGENT_CONTRACTS", "DomainAgentContract", "validate_subagent_specs"]
