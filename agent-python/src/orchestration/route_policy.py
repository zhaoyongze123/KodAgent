"""Route turn policy: the single source of truth that maps a compiled route
to how the next model call must behave.

The previous design scattered the same decision across ``_terminal_route_response``,
``_selection_response`` and ``_override`` in ``plan_projection``. Each branch
re-combined ``planStatus``, ``actionId`` and ``executionClass`` on its own, which
let three symptoms reinforce each other:

1. ``FIELD_CLARIFICATION`` (missing user fields) was treated like a terminal
   failure, so the model never got a chance to author a natural clarification
   and the user received a terse fixed string.
2. ``ACTION_SELECTION`` forced a second routing call even when the payload
   could not infer any action, producing an extra model call that then landed
   in the terminal short-circuit above.
3. Clarification copy was a hard-coded generic sentence that did not say which
   fields were missing.
4. ``FIELD_CLARIFICATION`` also stripped ``route_conversation`` from the
   palette, so after the user supplied the missing fields the model could not
   re-route the corrected payload: its natural re-route call was treated as an
   out-of-palette violation and replaced by a dead-end terminal, aborting the
   booking before execution.

This module replaces those branches with one pure decision table. A turn is one
of four modes:

- ``DETERMINISTIC_TERMINAL``: code answers; the model is not called. This is
  reserved for boundaries the model must not interpret (``UNSUPPORTED`` so a
  provider cannot fabricate a service outage, ``CONFIRMATION_REQUIRED`` so a
  confirmation card cannot be bypassed by prose).
- ``MODEL_RESPONSE``: the model answers naturally while code keeps the tool
  palette restricted. Used for field clarifications and for action selection
  when the payload cannot infer an action yet (the user must provide more
  fields; a clarification is the legal output, not a protocol violation).
- ``HANDSHAKE``: the model must emit the protocol call. Used for action
  selection only when the payload can uniquely infer a registered action.
- ``EXECUTE``: the model must call the compiled executor (or the run ends
  with the deterministic execution clarification).

Safety invariants stay in ``route_state.is_terminal_structured_failure`` and
are unchanged: field clarifications never open delegation or business tools.
``route_conversation`` stays visible because it is the routing protocol, not a
business tool: once the user supplies the missing fields the model must be able
to re-route the corrected payload instead of being forced into a dead-end.
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
# Terminal turns never call the model, so only narration stays relevant.
_TERMINAL_PALETTE = frozenset({"report_progress"})
# Field clarifications keep the routing protocol visible: after the user
# supplies the missing fields the model must be able to re-route the corrected
# payload. Business tools and delegation remain closed (see module docstring).
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
    """What the next model call is allowed and required to do."""

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
    """Return the unique action inferred from the route payload, if any.

    ``None`` means the user has not supplied enough structured fields to pick
    a registered action; a clarification is then the legal model output.
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
