"""Code-owned dispatch contract between the planner and domain agents.

The parent agent is a control-plane component: it understands a request,
produces a typed plan and presents a verified result.  It must not select a
business tool after a plan has been compiled.  This module is the small,
pure data-plane boundary that turns a resolved route into an immutable work
order for the one domain agent that owns its executor.

``task.description`` remains the transport required by DeepAgents, but it is
no longer a natural-language instruction authored by the parent model.  It
contains this versioned WorkOrder only; the child treats ``canonicalPlan`` as
the authority for business fields.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .capabilities import resolve_action
from .route_state import (
    route_action_id,
    route_capability,
    route_execution_tool,
    route_state,
)
from .execution_contracts import contract_for_executor


WORK_ORDER_MARKER = "KODAGENT_WORK_ORDER:"
WORK_ORDER_SCHEMA_VERSION = 1


class WorkOrder(BaseModel):
    """Immutable, versioned command passed from the control plane to a domain.

    The optional user request is context only.  A child may use it to phrase a
    clarification, but may never treat it as a replacement for canonical plan
    fields. ``allowedCapabilities`` and ``allowedActions`` preserve semantic
    scope; ``allowedExecutors`` pins the one terminal business effect. A child
    may use local read helpers for validation but cannot substitute a write or
    workflow executor.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    schema_version: int = Field(default=WORK_ORDER_SCHEMA_VERSION, alias="schemaVersion", ge=1)
    plan_id: str = Field(alias="planId", min_length=1, max_length=128)
    operation_id: str | None = Field(default=None, alias="operationId", max_length=128)
    domain: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=128)
    execution_tool: str = Field(alias="executionTool", min_length=1, max_length=128)
    canonical_plan: dict[str, Any] = Field(alias="canonicalPlan")
    allowed_capabilities: tuple[str, ...] = Field(alias="allowedCapabilities", min_length=1)
    allowed_actions: tuple[str, ...] = Field(alias="allowedActions", min_length=1)
    allowed_executors: tuple[str, ...] = Field(alias="allowedExecutors", min_length=1)
    revision: int = Field(default=1, ge=1)
    user_context: str | None = Field(default=None, alias="userContext", max_length=8_000)


class ExecutionResult(BaseModel):
    """Stable result envelope expected from a domain executor.

    Existing domain tools still return their Java envelopes during migration;
    declaring this contract here prevents presentation and tool-protocol text
    from becoming the de-facto cross-agent API again.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    status: str
    facts: dict[str, Any] = Field(default_factory=dict)
    presentation: dict[str, Any] = Field(default_factory=dict)
    missing_fields: tuple[str, ...] = Field(default=(), alias="missingFields")
    error_code: str | None = Field(default=None, alias="errorCode")
    user_message: str | None = Field(default=None, alias="userMessage")


def domain_agent_for_route(route: dict[str, Any] | None) -> str | None:
    """Return the child that owns this resolved plan's executor.

    This is intentionally executor-based rather than a model-facing domain
    heuristic: a capability may contain multiple actions, while the compiler
    has already selected exactly one execution contract.
    """
    if not isinstance(route, dict):
        return None
    # ``planStatus`` is the compiler's primary state fact.  Do not let a
    # stale routeState from an earlier checkpoint reopen a clarified plan.
    if str(route.get("planStatus") or route.get("plan_status") or "").upper() != "RESOLVED":
        return None
    if route_state(route) != "RESOLVED":
        return None
    executor = route_execution_tool(route)
    action = resolve_action(route_capability(route), route_action_id(route))
    # 编译状态同时携带 action 和 executor 时，两者必须来自同一份
    # ActionCatalog。否则即使 executor 本身存在，也不能把错配计划派发。
    if action is not None and action.execution_tool != executor:
        return None
    contract = contract_for_executor(executor)
    # feature flag 是编译期可用性的一部分。关闭的 party workflow 也必须在
    # 此处停止派发，不能把“工具不可用”拖到子 Agent 运行时才暴露。
    return contract.owner_agent if contract is not None and contract.is_available() else None


def work_order_from_route(
    route: dict[str, Any] | None, *, user_context: str | None = None,
) -> WorkOrder | None:
    """Build a WorkOrder only from a compiler-resolved route.

    ``None`` means this route has no migrated domain executor.  Callers must
    then use the explicit legacy/control-plane route, never choose an agent by
    interpreting user prose.
    """
    agent = domain_agent_for_route(route)
    if not agent or not isinstance(route, dict):
        return None
    canonical = route.get("executionPlan")
    if not isinstance(canonical, dict):
        return None
    execution_tool = route_execution_tool(route)
    domain = route_capability(route)
    action = route_action_id(route) or str(canonical.get("action_id") or canonical.get("actionId") or "").strip()
    plan_id = str(route.get("planId") or route.get("plan_id") or "").strip()
    if not (plan_id and domain and action and execution_tool):
        return None
    operation_id = route.get("operationId") or route.get("operation_id")
    revision = route.get("planRevision") or route.get("plan_revision") or 1
    try:
        return WorkOrder(
            planId=plan_id,
            operationId=str(operation_id).strip() or None if operation_id is not None else None,
            domain=domain,
            action=action,
            executionTool=execution_tool,
            canonicalPlan=canonical,
            allowedCapabilities=(domain,),
            allowedActions=(action,),
            allowedExecutors=(execution_tool,),
            revision=int(revision),
            userContext=user_context.strip() if isinstance(user_context, str) and user_context.strip() else None,
        )
    except (TypeError, ValueError):
        return None


def serialize_work_order(work_order: WorkOrder) -> str:
    return WORK_ORDER_MARKER + json.dumps(
        work_order.model_dump(by_alias=True, mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_work_order(text: str) -> WorkOrder | None:
    """Parse one compact WorkOrder marker, returning ``None`` for old turns."""
    marker_index = str(text or "").find(WORK_ORDER_MARKER)
    if marker_index < 0:
        return None
    payload = str(text)[marker_index + len(WORK_ORDER_MARKER):].splitlines()[0].strip()
    try:
        return WorkOrder.model_validate_json(payload)
    except (TypeError, ValueError):
        return None


__all__ = [
    "ExecutionResult", "WORK_ORDER_MARKER", "WORK_ORDER_SCHEMA_VERSION", "WorkOrder",
    "domain_agent_for_route", "parse_work_order", "serialize_work_order", "work_order_from_route",
]
