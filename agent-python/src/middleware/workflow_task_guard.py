"""Block direct sub-agent delegation for deterministic write workflows.

DeepAgents exposes the generated ``task`` tool independently of the normal
tool projection. A provider can therefore skip ``route_conversation`` and
delegate a covered write directly to a ReAct sub-agent. This middleware is a
runtime boundary for domains that already have a deterministic draft -> HITL
workflow; read-only and unsupported requests remain delegated normally.
"""

from __future__ import annotations

import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from ..tools.common.events import current_agent_context, turn_id_from_context
from ..orchestration.route_state import (
    current_turn_messages,
    is_terminal_structured_failure,
    route_capability,
    route_execution_class,
    route_result,
    route_requires_action_selection,
)


# This pattern is a safety boundary only.  It never selects a business domain
# or executor; the route result remains responsible for that decision.  It is
# retained solely for malformed provider calls that skip the route tool.
_WRITE_SAFETY_MARKER = re.compile(r"创建|新建|发布|修改|更新|编辑|调整|取消|删除|撤销|改为|改到")


def _message_type(message: Any) -> str:
    value = getattr(message, "type", None)
    if isinstance(message, dict):
        value = message.get("type") or message.get("role")
    return str(value or "").lower()


def _message_content(message: Any) -> str:
    value = getattr(message, "content", "")
    if isinstance(message, dict):
        value = message.get("content", "")
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in value)
    return str(value or "")


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    calls = getattr(message, "tool_calls", None)
    if isinstance(message, dict):
        calls = message.get("tool_calls")
    return [call for call in (calls or []) if isinstance(call, dict)]


def _latest_user_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if _message_type(message) in {"human", "user"}:
            return _message_content(message)
    return ""


def _task_target(call: dict[str, Any]) -> str:
    args = call.get("args") or {}
    return str(args.get("subagent_type") or args.get("subagentType") or "").strip()


def _guard(state: dict[str, Any]) -> dict[str, Any] | None:
    messages = list(state.get("messages") or [])
    if not messages or _message_type(messages[-1]) != "ai":
        return None
    # The route result is the only authority for whether a deterministic
    # workflow is required.  Re-inspecting user prose here used to duplicate
    # routing rules and could disagree with PlanToolProjectionMiddleware,
    # causing repeated task calls or a missing confirmation card.
    route = route_result(current_turn_messages(messages))
    if route is None:
        # A read-only delegation remains valid when a provider skipped the
        # route call.  For a write-shaped request, block only the known
        # deterministic child targets.  This is a last-resort safety check,
        # not a route decision; it is removed automatically once route facts
        # exist in the message stream.
        if not _WRITE_SAFETY_MARKER.search(_latest_user_text(messages)):
            return None
        targets = {_task_target(call) for call in _tool_calls(messages[-1])}
        if not targets & {"schedules_agent", "party_files_agent", "meeting_rooms_agent", "approvals_agent"}:
            return None
        domain = "registered business domain"
        guard_reason = "当前请求尚未完成业务路由，不能直接委派子 Agent。请先完成 route_conversation。"
        if "schedules_agent" in targets:
            guard_reason += "个人日程写操作必须进入 run_personal_schedule_workflow。"
        elif "party_files_agent" in targets:
            guard_reason += "党务文件写操作必须进入受控草稿工作流。"
    else:
        status = str(route.get("planStatus") or "").upper()
        strategy = str((route.get("routeDecision") or {}).get("strategy") or route.get("strategy") or "").lower()
        if strategy == "delegate" and status not in {"CLARIFY", "UNSUPPORTED"}:
            return None
        if status == "FALLBACK" and strategy in {"fallback", "delegate"}:
            return None
        if not (
            route_requires_action_selection(route)
            or is_terminal_structured_failure(route)
            or route_execution_class(route) in {"workflow", "metadata_query", "approval_query", "report"}
        ):
            return None
        domain = route_capability(route) or "registered business domain"
        guard_reason = "当前路由已选择确定性业务路径，不能绕过计划直接委派子 Agent；请按路由返回的执行器继续。"
    blocked: list[ToolMessage] = []
    context = current_agent_context()
    turn_id = turn_id_from_context(context)
    for call in _tool_calls(messages[-1]):
        if call.get("name") != "task":
            continue
        blocked.append(ToolMessage(
            content=guard_reason,
            tool_call_id=str(call.get("id") or "task"),
            name="task",
            status="error",
            response_metadata={
                "guard": "deterministic_workflow_task_required",
                "domain": domain,
                "runId": context.get("runId"),
                "messageId": context.get("messageId") or turn_id,
                "turnId": turn_id,
            },
        ))
    return {"messages": blocked} if blocked else None


class DeterministicWorkflowTaskGuardMiddleware(AgentMiddleware):
    """Prevent covered writes from bypassing their deterministic workflow."""

    name = "DeterministicWorkflowTaskGuardMiddleware"

    def after_model(self, state, runtime):
        return _guard(state)

    async def aafter_model(self, state, runtime):
        return _guard(state)


__all__ = ["DeterministicWorkflowTaskGuardMiddleware"]
