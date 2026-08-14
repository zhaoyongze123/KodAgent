"""路由回合策略：把已编译路由映射为下一次模型调用行为的唯一事实源。

文件职责
========
历史上，``plan_projection`` 的多个分支各自组合 ``planStatus``、``actionId`` 与
``executionClass``，导致字段澄清被过早终止、无法唯一推导动作时仍强制握手、以及
用户补齐字段后路由工具被移出工具列表等问题。本模块将这些分散判断收敛为一张纯
决策表，所有调用方只能消费同一份 ``TurnPolicy``。

四种模式
========
* ``DETERMINISTIC_TERMINAL``：代码直接回复，模型不参与。仅用于模型绝不能
  解释的边界，例如 ``UNSUPPORTED`` 与 ``CONFIRMATION_REQUIRED``。
* ``MODEL_RESPONSE``：模型可自然语言澄清，但工具列表仍被代码收紧。
* ``HANDSHAKE``：只有能唯一推导已注册动作时，模型才必须提交协议调用。
* ``EXECUTE``：模型只能调用已编译执行器，否则代码返回确定性执行澄清。

安全不变量
==========
``route_state.is_terminal_structured_failure`` 保证字段澄清不开放委派或业务工具。
``route_conversation`` 始终可见，因为它是路由协议而不是业务工具；用户补齐字段后
模型必须能够重新路由修正后的载荷，而不是进入死路。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from typing import Any

from .capabilities import (
    resolve_action,
    suggest_action_id_from_payload,
)
from .route_state import (
    route_action_id,
    route_capability,
    route_execution_class,
    route_execution_tool,
    route_state,
)
from .domain_dispatch import domain_agent_for_route

_WRITE_WORKFLOW_CAPABILITIES = frozenset({"party_file", "meeting", "schedule"})

_PLANNING_PALETTE = frozenset({"report_progress", "route_conversation"})
_HANDSHAKE_PALETTE = frozenset({"report_progress", "route_conversation"})
# 终态回合不会调用模型，因此仅保留面向用户的进度播报。
_TERMINAL_PALETTE = frozenset({"report_progress"})
# 字段澄清必须保留路由协议：用户补齐字段后模型要能重新路由修正载荷；业务工具和
# 委派仍然关闭，具体原因见本文件顶部的安全不变量。
_FIELD_CLARIFICATION_WRITE_PALETTE = frozenset({"report_progress", "route_conversation"})
_FIELD_CLARIFICATION_READ_PALETTE = frozenset({"task", "report_progress", "route_conversation"})
_FALLBACK_PALETTE = frozenset({"task", "report_progress"})

class TurnMode(str, Enum):
    DETERMINISTIC_TERMINAL = "deterministic_terminal"
    MODEL_RESPONSE = "model_response"
    HANDSHAKE = "handshake"
    EXECUTE = "execute"


@dataclass(frozen=True)
class TurnPolicy:
    """描述下一次模型调用允许做什么、且必须做什么的不可变策略。"""

    mode: TurnMode
    planning_tools: frozenset[str] = field(default_factory=frozenset)
    terminal_content: str | None = None
    terminal_metadata: dict[str, Any] | None = None
    delegate_agent: str | None = None


def eval_route_only_enabled() -> bool:
    return os.getenv("OA_AGENT_INTENT_EVAL_ROUTE_ONLY", "false").lower() in {
        "1", "true", "yes", "on",
    }


def selection_action(route: dict[str, Any] | None):
    """从路由载荷推导唯一动作；不能唯一推导时返回 ``None``。

    此时用户尚未提供足够结构化字段来选择已注册动作，合法模型输出应是澄清，
    不能伪造 ``action_id``。
    """
    if not isinstance(route, dict):
        return None
    selection = route.get("actionSelection") or route.get("action_selection") or {}
    if not isinstance(selection, dict):
        return None
    capability = route_capability(route)
    if not capability:
        return None
    candidate = selection.get("candidatePlan") or selection.get("candidate_plan") or {}
    query = selection.get("queryIntent") or selection.get("query_intent") or {}
    if not isinstance(candidate, dict):
        candidate = {}
    if not isinstance(query, dict):
        query = {}
    execution_class = str(
        route.get("executionClass")
        or route.get("execution_class")
        or ((route.get("routeDecision") or {}).get("executionClass") or "")
    ).strip() or None
    clarification = route.get("clarification") or {}
    suggested = (
        clarification.get("suggestedActionId")
        if isinstance(clarification, dict)
        else None
    ) or selection.get("suggestedActionId")
    action = resolve_action(capability, str(suggested or "").strip()) if suggested else None
    # 服务端仅在“会议写动词被误选为读取动作”的窄边界标记此开关。这里的
    # suggestedActionId 仍只是下一阶段的受限枚举，不携带业务字段、更不授予
    # 执行权；模型必须据当前用户原文填写 candidate_plan 后重新调用路由工具。
    force_structured_submission = bool(
        selection.get("requiresStructuredSubmission")
        or selection.get("requires_structured_submission")
    )
    if force_structured_submission:
        return (action, candidate, query) if action is not None else None
    if action is None or suggest_action_id_from_payload(
        capability, candidate, query, execution_class
    ) != action.action_id:
        action_id = suggest_action_id_from_payload(capability, candidate, query, execution_class)
        action = resolve_action(capability, action_id) if action_id else None
    if action is None:
        return None
    # The helper above has already validated the full schema. Keep this
    # final check so a suggested id can never bypass the same contract.
    if suggest_action_id_from_payload(capability, candidate, query, execution_class) != action.action_id:
        return None
    return action, candidate, query


def workflow_delegate_agent(route: dict[str, Any] | None) -> str | None:
    """Backward-compatible alias for the code-owned domain dispatcher.

    Callers historically used this name for the two write workflows.  Keeping
    the symbol avoids a migration flag day, while the dispatcher now covers
    all migrated read and report executors too.
    """
    return domain_agent_for_route(route)


def _route_looks_like_fallback(route: dict[str, Any]) -> bool:
    """Legacy/checkpointed delegate routes may omit ``planStatus``/``routeState``."""
    state = str(route.get("routeState") or route.get("route_state") or "").upper()
    decision = route.get("routeDecision") or {}
    strategy = str(
        route.get("strategy")
        or decision.get("strategy")
        or ""
    ).strip().lower()
    return state == "FALLBACK" or strategy in {"delegate", "fallback"}


def _field_clarification_palette(route: dict[str, Any] | None) -> frozenset[str]:
    status = str((route or {}).get("planStatus") or (route or {}).get("plan_status") or "").upper()
    execution_class = str(route_execution_class(route) or "").strip().lower()
    capability = route_capability(route)
    is_write_workflow = (
        status in {"CLARIFY", "UNSUPPORTED"}
        and execution_class == "workflow"
        and capability in _WRITE_WORKFLOW_CAPABILITIES
    )
    if is_write_workflow:
        return _FIELD_CLARIFICATION_WRITE_PALETTE
    return _FIELD_CLARIFICATION_READ_PALETTE


def _terminal_policy(route: dict[str, Any], state: str) -> TurnPolicy:
    clarification = route.get("clarification") or {}
    if not isinstance(clarification, dict):
        clarification = {}
    question = str(clarification.get("question") or "").strip()
    issues = [
        str(item).strip()
        for item in (clarification.get("issues") or [])
        if str(item).strip()
    ]
    action_id = route_action_id(route)
    if state == "UNSUPPORTED":
        content = "当前请求未匹配到可执行的已注册业务动作。"
        if issues:
            content += f"{issues[0]}。"
        content += "未调用业务服务，请重新发起请求。"
    else:
        content = question or "请通过确认卡完成此操作，或补充必要的信息后继续。"
    return TurnPolicy(
        mode=TurnMode.DETERMINISTIC_TERMINAL,
        planning_tools=_TERMINAL_PALETTE,
        terminal_content=content,
        terminal_metadata={
            "deterministicTerminal": True,
            "routeStatus": str(route.get("planStatus") or "").upper(),
            "routeActionId": action_id,
            "routeState": state,
            "routeFailure": "structured_plan_boundary",
        },
    )


def decide_turn_policy(route: dict[str, Any] | None) -> TurnPolicy:
    """Decide, from the compiled route alone, how the next turn behaves.

    This is the single decision table consumed by the projection middleware.
    No caller re-combines ``planStatus``/``actionId``/``executionClass`` any
    more; the state classifier owns that, and this function owns behaviour.
    """
    if not isinstance(route, dict):
        return TurnPolicy(mode=TurnMode.MODEL_RESPONSE, planning_tools=_PLANNING_PALETTE)

    state = route_state(route)

    if state in {"UNSUPPORTED", "CONFIRMATION_REQUIRED"}:
        return _terminal_policy(route, state)

    if state == "FIELD_CLARIFICATION":
        # Missing user fields are interaction, not failure. The model authors
        # the clarification (it owns wording); code only restricts tools.
        return TurnPolicy(
            mode=TurnMode.MODEL_RESPONSE,
            planning_tools=_field_clarification_palette(route),
        )

    if state == "ACTION_SELECTION":
        if selection_action(route) is not None:
            # The payload already uniquely identifies a registered action.
            # The model must submit it; a prose-only answer is a protocol miss.
            return TurnPolicy(mode=TurnMode.HANDSHAKE, planning_tools=_HANDSHAKE_PALETTE)
        # The payload cannot infer an action because the user has not supplied
        # the required fields. A natural clarification is the legal output and
        # must not be forced through a second routing call.
        return TurnPolicy(
            mode=TurnMode.MODEL_RESPONSE,
            planning_tools=_PLANNING_PALETTE,
        )

    if state == "RESOLVED":
        if eval_route_only_enabled():
            # Golden-set evaluation measures routing without creating effects.
            return TurnPolicy(mode=TurnMode.MODEL_RESPONSE, planning_tools=frozenset())
        executor = route_execution_tool(route)
        if not executor:
            return TurnPolicy(mode=TurnMode.MODEL_RESPONSE, planning_tools=frozenset())
        delegate_agent = domain_agent_for_route(route)
        if delegate_agent:
            # The compiled executor belongs to a domain child.  The parent
            # exposes only the code-owned task handoff, never this business
            # executor itself.
            return TurnPolicy(
                mode=TurnMode.EXECUTE,
                planning_tools=frozenset({"task"}),
                delegate_agent=delegate_agent,
            )
        return TurnPolicy(
            mode=TurnMode.EXECUTE,
            planning_tools=frozenset({executor}),
        )

    if state == "COORDINATION_READY":
        # 跨领域批次没有单一业务 executor。它只能由后续协调执行桥读取已持久化
        # 的 CoordinationBatch 后派发，不能掉回普通规划工具让模型重新拆分步骤。
        # 这里关闭模型工具，执行桥接入后会在同一状态前接管实际派发。
        return TurnPolicy(mode=TurnMode.MODEL_RESPONSE, planning_tools=frozenset())

    if state == "FALLBACK":
        # The route tool asked for the domain ReAct fallback. Delegation and
        # narration stay visible so the child can handle it without touching
        # a structured executor.
        return TurnPolicy(
            mode=TurnMode.MODEL_RESPONSE,
            planning_tools=_FALLBACK_PALETTE,
        )

    # UNROUTED / unknown plan status: keep the parent planning palette
    # visible, unless a checkpointed delegate route still needs the fallback.
    if _route_looks_like_fallback(route):
        return TurnPolicy(
            mode=TurnMode.MODEL_RESPONSE,
            planning_tools=_FALLBACK_PALETTE,
        )
    return TurnPolicy(mode=TurnMode.MODEL_RESPONSE, planning_tools=_PLANNING_PALETTE)


__all__ = [
    "TurnMode",
    "TurnPolicy",
    "decide_turn_policy",
    "eval_route_only_enabled",
    "selection_action",
    "workflow_delegate_agent",
]
