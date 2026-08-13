"""投影和执行守卫共享的规范路由事实。

主图会产出 ``route_conversation`` ToolMessage；从此以后中间件不得再从用户自然
语言重新识别意图，当前回合唯一事实源是已编译路由。把解析、当前回合切分和状态
分类集中在本文件，可避免计划投影、任务守卫和观测钩子各自实现后逐渐漂移。
"""

from __future__ import annotations

import json
from typing import Any, Literal

from .capabilities import actions_for_capability, canonical_capability_id


RouteState = Literal[
    "UNROUTED",
    "ACTION_SELECTION",
    "RESOLVED",
    "FIELD_CLARIFICATION",
    "UNSUPPORTED",
    "CONFIRMATION_REQUIRED",
    "FALLBACK",
]

_KNOWN_ROUTE_STATES = frozenset(
    {
        "UNROUTED",
        "ACTION_SELECTION",
        "RESOLVED",
        "FIELD_CLARIFICATION",
        "UNSUPPORTED",
        "CONFIRMATION_REQUIRED",
        "FALLBACK",
    }
)


def message_type(message: Any) -> str:
    value = message.get("type") if isinstance(message, dict) else getattr(message, "type", "")
    return str(value or "").lower()


def message_name(message: Any) -> str:
    value = message.get("name") if isinstance(message, dict) else getattr(message, "name", "")
    return str(value or "")


def message_content(message: Any) -> Any:
    return message.get("content") if isinstance(message, dict) else getattr(message, "content", "")


def current_turn_messages(messages: list[Any]) -> list[Any]:
    """返回最新用户消息之后的当前回合消息。

    上一回合的已解析路由绝不能在新请求尚未分类前解锁工具。
    """
    latest_human = max(
        (index for index, message in enumerate(messages) if message_type(message) in {"human", "user"}),
        default=-1,
    )
    return messages[latest_human + 1 :] if latest_human >= 0 else messages


def route_result(messages: list[Any]) -> dict[str, Any] | None:
    """读取当前回合最新的结构化路由结果。

    新 HumanMessage 会形成硬路由边界。当前回合尚无 ``route_conversation`` 结果时
    就是未路由状态，不能把上一回合已解析 WorkOrder 重放到新用户文本上。合法的
    补字段续接必须在新路由调用中显式使用 ``continuation_mode='resume'``，并且
    只能由该调用边界的 ``pending_plan`` 合并。
    """
    return _latest_route(current_turn_messages(list(messages or [])))


def _latest_route(messages: list[Any]) -> dict[str, Any] | None:
    """Read the last valid route envelope from an already-scoped sequence."""
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
                continue
        if isinstance(value, dict) and isinstance(value.get("data"), dict):
            value = value["data"]
        return value if isinstance(value, dict) else None
    return None


def route_result_anywhere(messages: list[Any]) -> dict[str, Any] | None:
    """Search the given list of messages for the latest route.

    Provided as a helper for callers that need to bypass the current-turn
    restriction (e.g. ``_route_result`` callers that have already passed the
    current turn slice and want to fall back to the broader history).
    """
    return _latest_route(list(messages or []))


def route_result_fallback_all(messages: list[Any]) -> dict[str, Any] | None:
    """Search the entire message history for the most recent route.

    Used by callers that pass only the current turn; the base
    :func:`route_result` already walks the list it receives, so this helper
    is the same algorithm but always scans the full message list.
    """
    return _latest_route(list(messages or []))


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


def route_state(route: dict[str, Any] | None) -> RouteState:
    """Classify the route lifecycle once for every middleware boundary.

    ``planStatus`` describes the compiler result, while ``routePhase``
    describes the protocol handshake. They are different dimensions: an
    action-selection handshake can carry ``planStatus=CLARIFY`` and must stay
    executable by the next model turn. Consumers must use this classifier
    instead of independently combining ``planStatus``, ``actionId`` and
    ``executionClass``.

    Explicit ``routeState`` is emitted by the route tool. The fallback parsing
    keeps checkpointed messages from older runs readable. An unmarked legacy
    action-selection message is recognized only when the registered capability
    has no action/executor and the clarification carries no business-field
    error. This keeps old checkpoints resumable without turning an actual
    missing-field clarification into a second planning loop.
    """
    if not isinstance(route, dict):
        return "UNROUTED"

    explicit = str(route.get("routeState") or route.get("route_state") or "").strip().upper()
    if explicit in _KNOWN_ROUTE_STATES:
        return explicit  # type: ignore[return-value]

    phase = str(route.get("routePhase") or route.get("route_phase") or "").strip().upper()
    action_selection = route.get("actionSelection") or route.get("action_selection") or {}
    clarification = route.get("clarification") or {}
    clarification_status = str(
        clarification.get("status") if isinstance(clarification, dict) else ""
    ).strip().upper()
    if phase == "ACTION_SELECTION" or (
        isinstance(action_selection, dict) and bool(action_selection.get("required"))
    ) or clarification_status == "ACTION_SELECTION":
        return "ACTION_SELECTION"

    status = str(route.get("planStatus") or route.get("plan_status") or "").strip().upper()
    if status == "CLARIFY":
        capability = route_capability(route)
        missing_fields = clarification.get("missingFields") or clarification.get("missing_fields") or []
        issues = clarification.get("issues") or []
        no_business_error = not missing_fields and not issues
        action_id_missing = set(str(value).strip() for value in missing_fields) <= {"", "action_id"}
        if (
            capability not in {"", "general_agent", "general"}
            and bool(actions_for_capability(capability))
            and not route_action_id(route)
            and not route_execution_tool(route)
            and (no_business_error or action_id_missing)
        ):
            return "ACTION_SELECTION"
    if status == "RESOLVED":
        return "RESOLVED" if route_execution_tool(route) else "UNSUPPORTED"
    if status == "UNSUPPORTED":
        return "UNSUPPORTED"
    if status == "CLARIFY":
        if bool(route.get("confirmationRequired") or route.get("confirmation_required")):
            return "CONFIRMATION_REQUIRED"
        return "FIELD_CLARIFICATION"
    if status == "FALLBACK":
        return "FALLBACK"
    return "UNROUTED"


def route_requires_action_selection(route: dict[str, Any] | None) -> bool:
    """Whether the two-stage route handshake still needs an action id."""
    return route_state(route) == "ACTION_SELECTION"


def is_terminal_structured_failure(route: dict[str, Any] | None) -> bool:
    """Whether a structured route is terminal and must stop delegation.

    The historical function name is retained for callers, but the boundary is
    now lifecycle-based. In particular, ``ACTION_SELECTION`` is deliberately
    excluded even when its compiler result is ``CLARIFY`` and its execution
    class is ``workflow``.
    """
    return route_state(route) in {
        "FIELD_CLARIFICATION",
        "UNSUPPORTED",
        "CONFIRMATION_REQUIRED",
    }


def is_resolved_route(route: dict[str, Any] | None) -> bool:
    return route_state(route) == "RESOLVED"


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
    "route_state",
    "route_requires_action_selection",
    "route_result",
]
