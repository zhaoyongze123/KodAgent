"""主 Agent 与领域子 Agent 之间由代码拥有的派发契约。

文件职责
========
主 Agent 是控制面：理解请求、产出类型化计划、呈现已验证结果。计划编译完成后，
它不得再挑选业务工具。本模块是小而纯的数据面边界，把 ``RESOLVED`` 路由结果
转换为唯一执行器所属子 Agent 的不可变 WorkOrder。

数据流
======
``route_conversation`` -> 编译路由 -> ``domain_agent_for_route`` 校验执行契约
-> ``work_order_from_route`` 构造 WorkOrder -> ``task.description`` 传递给子 Agent。
``task.description`` 仍是 DeepAgents 的传输通道，但其中只允许版本化 WorkOrder，
不再允许主模型编写自然语言执行指令；子 Agent 只能以 ``canonicalPlan`` 作为业务
字段的权威来源。
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
from .target_resolution import is_target_resolution_route, target_resolution_spec


WORK_ORDER_MARKER = "KODAGENT_WORK_ORDER:"
WORK_ORDER_SCHEMA_VERSION = 1


class WorkOrder(BaseModel):
    """从控制面传给领域子 Agent 的不可变、版本化工作指令。

    ``userContext`` 仅用于理解和澄清，不能替代 ``canonicalPlan`` 中的业务字段。
    ``allowedCapabilities`` 与 ``allowedActions`` 固定语义范围；
    ``allowedExecutors`` 固定唯一终态业务效果。子 Agent 可使用允许的只读 helper
    核验事实，但不能替换写执行器或工作流执行器。
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
    """领域执行器返回的稳定结果信封。

    迁移期间既有领域工具仍返回 Java 信封；在此明确跨 Agent 契约，避免把展示文本
    或工具协议文本误当成事实 API。
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    status: str
    facts: dict[str, Any] = Field(default_factory=dict)
    presentation: dict[str, Any] = Field(default_factory=dict)
    missing_fields: tuple[str, ...] = Field(default=(), alias="missingFields")
    error_code: str | None = Field(default=None, alias="errorCode")
    user_message: str | None = Field(default=None, alias="userMessage")


def domain_agent_for_route(route: dict[str, Any] | None) -> str | None:
    """返回已解析计划的执行器所属领域子 Agent。

    参数：route 为编译后的结构化路由事实。
    返回：唯一 owner 名称；计划未解析、动作与执行器错配或工作流关闭时返回 ``None``。

    派发必须以执行器为依据，而非模型可见的领域猜测：一个能力域可有多个动作，
    但编译器已经为当前计划选定唯一执行契约。
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
        # 多轮目标核验是唯一例外：路由语义仍是 schedule.update / meeting.cancel，
        # 但第一段必须先把候选内部 ID 交给只读详情工具核验。它不是让模型改选
        # executor，而是由 target_resolution.py 签发的内部两段式计划。
        spec = target_resolution_spec(route_capability(route), route_action_id(route))
        if not (
            is_target_resolution_route(route)
            and spec is not None
            and spec.verification_tool == executor
        ):
            return None
    contract = contract_for_executor(executor)
    # feature flag 是编译期可用性的一部分。关闭的 party workflow 也必须在
    # 此处停止派发，不能把“工具不可用”拖到子 Agent 运行时才暴露。
    return contract.owner_agent if contract is not None and contract.is_available() else None


def work_order_from_route(
    route: dict[str, Any] | None, *, user_context: str | None = None,
) -> WorkOrder | None:
    """仅从编译器已解析的路由构造 WorkOrder。

    参数：
        route：包含计划 ID、规范计划与执行器的编译结果。
        user_context：可选原始用户上下文，只供子 Agent 理解请求。

    返回 ``None`` 表示路由尚无迁移后的领域执行器；调用方必须进入显式旧链路或
    控制面链路，绝不能重新根据用户自然语言挑选 Agent。
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
    """将 WorkOrder 序列化为 ``task.description`` 可识别的单行标记。"""
    return WORK_ORDER_MARKER + json.dumps(
        work_order.model_dump(by_alias=True, mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_work_order(text: str) -> WorkOrder | None:
    """解析单行 WorkOrder 标记；旧回合或无标记文本返回 ``None``。"""
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
