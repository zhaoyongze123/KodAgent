"""Lightweight conversational continuation for incomplete compiled plans.

This is deliberately smaller than a durable business ``Operation``.  It
lives in the LangGraph thread checkpoint only while the compiler is waiting
for user fields.  Once a plan is resolved, normal workflow/Operation
lifecycle ownership takes over.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .route_state import (
    current_turn_messages,
    message_content,
    message_name,
    message_type,
    route_action_id,
    route_capability,
    route_execution_class,
    route_result,
    route_state,
)


class PendingPlan(BaseModel):
    """One compiler-owned plan waiting for user-supplied fields."""

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="forbid")

    plan_id: str = Field(alias="planId", min_length=1, max_length=128)
    capability_id: str = Field(alias="capabilityId", min_length=1, max_length=64)
    action_id: str = Field(alias="actionId", min_length=1, max_length=128)
    execution_class: str = Field(alias="executionClass", min_length=1, max_length=64)
    canonical_plan: dict[str, Any] = Field(alias="canonicalPlan")
    missing_fields: tuple[str, ...] = Field(alias="missingFields", min_length=1)
    revision: int = Field(default=1, ge=1)


ContinuationMode = Literal["resume", "new"]


def _route_plan(route: dict[str, Any]) -> dict[str, Any]:
    value = route.get("plan")
    return dict(value) if isinstance(value, dict) else {}


def pending_plan_from_route(route: dict[str, Any] | None) -> PendingPlan | None:
    """Project a field clarification into a checkpoint-resident PendingPlan."""
    if not isinstance(route, dict) or route_state(route) != "FIELD_CLARIFICATION":
        return None
    plan = _route_plan(route)
    clarification = route.get("clarification") if isinstance(route.get("clarification"), dict) else {}
    canonical = plan.get("canonical") if isinstance(plan.get("canonical"), dict) else {}
    missing = clarification.get("missingFields") or clarification.get("missing_fields") or plan.get("missing_fields") or []
    missing = tuple(str(item).strip() for item in missing if str(item).strip())
    plan_id = str(route.get("planId") or plan.get("plan_id") or "").strip()
    capability = route_capability(route) or str(plan.get("capability_id") or "").strip()
    action = route_action_id(route) or str(canonical.get("action_id") or canonical.get("actionId") or "").strip()
    execution_class = route_execution_class(route) or str(plan.get("execution_class") or "").strip()
    if not (plan_id and capability and action and execution_class and canonical and missing):
        return None
    trace = route.get("routingTrace") if isinstance(route.get("routingTrace"), dict) else {}
    revision = trace.get("plan_revision") or 1
    try:
        return PendingPlan(
            planId=plan_id,
            capabilityId=capability,
            actionId=action,
            executionClass=execution_class,
            canonicalPlan=canonical,
            missingFields=missing,
            revision=int(revision),
        )
    except (TypeError, ValueError):
        return None


def current_turn_route(messages: list[Any]) -> dict[str, Any] | None:
    """Read a route emitted after the latest user message, if any."""
    turn = current_turn_messages(list(messages or []))
    return route_result(turn) if turn else None


def pending_plan_state_update(state: dict[str, Any]) -> dict[str, Any] | None:
    """Store/clear a PendingPlan after the current turn's route has returned."""
    messages = list((state or {}).get("messages") or [])
    route = current_turn_route(messages)
    if route is None:
        return None
    pending = pending_plan_from_route(route)
    if pending is not None:
        return {"pending_plan": pending.model_dump(by_alias=True, mode="json")}
    # A route result for this new turn is an explicit new compiler decision.
    # It supersedes a previous incomplete plan rather than leaving stale
    # context attached to later conversation.
    return {"pending_plan": None}


def _as_pending(value: Any) -> PendingPlan | None:
    try:
        return PendingPlan.model_validate(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def merge_resume_route_call(call: dict[str, Any], pending_value: Any) -> dict[str, Any]:
    """Merge a model-declared continuation patch into the prior canonical plan.

    A normal new request remains untouched.  The model therefore decides
    whether the short reply continues the pending interaction; code merely
    preserves fields and enforces the preselected action when it does.
    """
    pending = _as_pending(pending_value)
    if pending is None or str(call.get("name") or "") != "route_conversation":
        return call
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    if str(args.get("continuation_mode") or "").strip().lower() != "resume":
        return call
    patch = args.get("candidate_plan")
    if not isinstance(patch, dict):
        patch = {}
    # The explicit control value must not reach the Action payload.
    patch.pop("continuation_mode", None)
    merged = {**pending.canonical_plan, **patch}
    updated = dict(call)
    updated["args"] = {
        **args,
        "capability_id": pending.capability_id,
        "action_id": pending.action_id,
        "execution_class": pending.execution_class,
        "candidate_plan": merged,
    }
    return updated


def pending_plan_prompt(value: Any) -> str:
    """Render a compact model context without exposing arbitrary history."""
    pending = _as_pending(value)
    if pending is None:
        return ""
    payload = pending.model_dump(by_alias=True, mode="json")
    return (
        "当前 Thread 有一项待补充的已编译计划：\n"
        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n"
        "请根据本轮用户输入判断：若它是在补充该计划，调用 route_conversation 时必须传 "
        "continuation_mode='resume'，candidate_plan 中仅填写新增/修改字段；若它是新请求，"
        "传 continuation_mode='new' 并按普通路由处理。不要自行执行工具。"
    )


__all__ = [
    "ContinuationMode", "PendingPlan", "current_turn_route", "merge_resume_route_call",
    "pending_plan_from_route", "pending_plan_prompt", "pending_plan_state_update",
]
