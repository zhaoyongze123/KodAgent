"""Canonical route facts shared by projection and execution guards.

The parent graph emits a ``route_conversation`` ToolMessage.  Middleware must
not rediscover intent from user prose after that point: the compiled route is
the only source of truth for the current turn.  Keeping parsing and state
classification here prevents projection, task guards and future observability
hooks from drifting apart.
"""

from __future__ import annotations

import json
from typing import Any

from .capabilities import actions_for_capability, canonical_capability_id


def message_type(message: Any) -> str:
    value = message.get("type") if isinstance(message, dict) else getattr(message, "type", "")
    return str(value or "").lower()


def message_name(message: Any) -> str:
    value = message.get("name") if isinstance(message, dict) else getattr(message, "name", "")
    return str(value or "")


def message_content(message: Any) -> Any:
    return message.get("content") if isinstance(message, dict) else getattr(message, "content", "")


def current_turn_messages(messages: list[Any]) -> list[Any]:
    """Return messages after the latest user turn.

    A previous turn's resolved route must never unlock tools for a new user
    request before the new request has been classified.
    """
    latest_human = max(
        (index for index, message in enumerate(messages) if message_type(message) in {"human", "user"}),
        default=-1,
    )
    return messages[latest_human + 1 :] if latest_human >= 0 else messages


def route_result(messages: list[Any]) -> dict[str, Any] | None:
    """Read the latest structured route result from the current turn."""
    for message in reversed(messages):
        if message_type(message) != "tool" or message_name(message) != "route_conversation":
            continue
        content = message_content(message)
        if isinstance(content, dict):
            value = content
        else:
            if isinstance(content, list):
                content = "".join(
                    str(item.get("text", "")) if isinstance(item, dict) else str(item)
                    for item in content
                )
            try:
                value = json.loads(content or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                return None
        if isinstance(value, dict) and isinstance(value.get("data"), dict):
            value = value["data"]
        return value if isinstance(value, dict) else None
    return None


def route_capability(route: dict[str, Any] | None) -> str:
    if not isinstance(route, dict):
        return ""
    decision = route.get("routeDecision") or {}
    return canonical_capability_id(
        route.get("capabilityId")
        or route.get("capability_id")
        or decision.get("capabilityId")
        or decision.get("capability_id")
    )


def route_action_id(route: dict[str, Any] | None) -> str:
    if not isinstance(route, dict):
        return ""
    decision = route.get("routeDecision") or {}
    return str(
        route.get("actionId")
        or route.get("action_id")
        or decision.get("actionId")
        or decision.get("action_id")
        or ""
    ).strip()


def route_execution_tool(route: dict[str, Any] | None) -> str:
    if not isinstance(route, dict):
        return ""
    decision = route.get("routeDecision") or {}
    return str(route.get("executionTool") or decision.get("executionTool") or "").strip()


def route_execution_class(route: dict[str, Any] | None) -> str:
    if not isinstance(route, dict):
        return ""
    plan = route.get("plan") or {}
    return str(
        route.get("execution_class")
        or route.get("executionClass")
        or plan.get("execution_class")
        or plan.get("executionClass")
        or ""
    ).strip().lower()


def route_requires_action_selection(route: dict[str, Any] | None) -> bool:
    """Whether the two-stage route handshake still needs an action id."""
    if not isinstance(route, dict):
        return False
    if str(route.get("routePhase") or "").upper() == "ACTION_SELECTION":
        return True
    if str(route.get("planStatus") or "").upper() != "CLARIFY":
        return False
    capability = route_capability(route)
    if capability in {"", "general_agent", "general"}:
        return False
    return not route_action_id(route) and not route_execution_tool(route) and bool(actions_for_capability(capability))


def is_terminal_structured_failure(route: dict[str, Any] | None) -> bool:
    """Whether a failed structured route must stop instead of delegating."""
    if not isinstance(route, dict) or str(route.get("planStatus") or "").upper() not in {"CLARIFY", "UNSUPPORTED"}:
        return False
    if route_action_id(route):
        return True
    return route_capability(route) in {
        "approval_read", "approval_process", "approval_write", "meeting", "schedule", "party_file", "reporting",
    } and route_execution_class(route) in {"metadata_query", "approval_query", "workflow", "report"}


def is_resolved_route(route: dict[str, Any] | None) -> bool:
    return bool(isinstance(route, dict) and str(route.get("planStatus") or "").upper() == "RESOLVED" and route_execution_tool(route))


__all__ = [
    "current_turn_messages",
    "is_resolved_route",
    "is_terminal_structured_failure",
    "message_content",
    "message_name",
    "message_type",
    "route_action_id",
    "route_capability",
    "route_execution_class",
    "route_execution_tool",
    "route_requires_action_selection",
    "route_result",
]
