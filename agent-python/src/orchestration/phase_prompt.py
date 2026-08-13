"""主 Agent 的阶段识别与提示词组装。

文件职责
========
本模块根据当前回合消息判断主 Agent 正处于“规划、执行还是汇总”阶段，并将
对应提示词、当前业务时间、能力目录和已选领域 Skill 组装为 SystemMessage。
它只决定提示词组合方式，不解释业务规则；动作、权限和字段约束仍由 Action
Catalog 与已选 Skill 提供，避免父提示词复制业务事实。

调用关系
========
``oa_agent`` -> ``MainAgentPhasePromptMiddleware`` -> 本模块 -> 模型。
模型返回的 ``route_conversation`` ToolMessage 会反过来成为下一次组装提示词的
路由事实来源。

结构导读
========
* ``classify_main_agent_phase``：从本轮消息判定阶段；
* ``_route_skill_prompt``：仅在需要时加载当前领域 Skill；
* ``main_agent_phase_instructions``：组合阶段提示词和能力目录；
* ``MainAgentPhasePromptMiddleware``：模型调用前注入最终 SystemMessage。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Literal, Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

from ..tools.common import AGENT_TIMEZONE
from .capability_registry import CapabilityRegistry
from .prompts import (
    COMMON_PROMPT,
    DOMAIN_PLANNER_PROMPT,
    EXECUTION_PROMPT,
    INTENT_ROUTER_PROMPT,
    PROMPT_VERSION,
    SYNTHESIS_PROMPT,
)
from .skill_registry import skill_registry
from .route_state import route_state
from .pending_plan import pending_plan_prompt
from .conversation_context import context_prompt

MainAgentPhase = Literal["planning", "executing", "synthesizing"]

MAIN_AGENT_COMMON_PROMPT = COMMON_PROMPT
MAIN_AGENT_PLANNING_PROMPT = INTENT_ROUTER_PROMPT
MAIN_AGENT_EXECUTION_PROMPT = EXECUTION_PROMPT
MAIN_AGENT_SYNTHESIS_PROMPT = SYNTHESIS_PROMPT


def _business_clock_prompt() -> str:
    now = datetime.now(AGENT_TIMEZONE)
    return (
        f"当前业务时间：{now.strftime('%Y-%m-%d %H:%M:%S')}（Asia/Shanghai）。\n"
        "相对日期必须以当前业务时间换算成明确公历日期；本轮用户明确给出的日期优先。"
    )


def _message_type(message: Any) -> str:
    value = (
        message.get("type") or message.get("role", "")
        if isinstance(message, dict)
        else getattr(message, "type", "") or getattr(message, "role", "")
    )
    return str(value).lower()


def _message_tool_name(message: Any) -> str:
    if isinstance(message, dict):
        name = message.get("name")
        calls = message.get("tool_calls") or []
    else:
        name = getattr(message, "name", None)
        calls = getattr(message, "tool_calls", None) or []
    if name:
        return str(name)
    call = calls[-1] if isinstance(calls, list) and calls else calls
    if isinstance(call, dict):
        return str(call.get("name") or call.get("function", {}).get("name") or "")
    return ""


def _task_result_requires_execution(message: Any) -> bool:
    content = message.get("content", "") if isinstance(message, dict) else getattr(message, "content", "")
    try:
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    except (TypeError, ValueError):
        text = str(content or "")
    lowered = text.lower()
    return (
        '"requires_confirmation":true' in lowered
        or '"valid":false' in lowered
        or bool(re.search(r'"confirmation_token"\s*:\s*"(?:[^"\\]|\\.)+"', text))
    )


def classify_main_agent_phase(messages) -> MainAgentPhase:
    """根据当前用户回合后的消息判定主 Agent 阶段。

    参数：
        messages：LangGraph 保存的完整会话消息，可同时包含对象和字典形式。

    返回：
        ``planning`` 表示等待路由，``executing`` 表示仍需执行计划，
        ``synthesizing`` 表示子 Agent/工具已经返回可汇总结果。
    """
    messages = list(messages or [])
    latest_human = max(
        (i for i, message in enumerate(messages) if _message_type(message) in {"human", "user"}),
        default=-1,
    )
    turn_messages = messages[latest_human + 1 :] if latest_human >= 0 else messages
    if not turn_messages or all(_message_type(m) in {"human", "user"} for m in turn_messages):
        return "planning"
    task_ids = {
        str(call.get("id") or call.get("tool_call_id"))
        for message in turn_messages
        if _message_type(message) == "ai"
        for call in (
            message.get("tool_calls", [])
            if isinstance(message, dict)
            else getattr(message, "tool_calls", None) or []
        )
        if isinstance(call, dict) and call.get("name") in {"task", "task_tool"}
    }
    for message in reversed(turn_messages):
        if _message_type(message) != "tool":
            continue
        tool_name = _message_tool_name(message)
        if not tool_name:
            tool_id = str(
                message.get("tool_call_id")
                if isinstance(message, dict)
                else getattr(message, "tool_call_id", "")
            )
            if tool_id in task_ids:
                tool_name = "task"
        if tool_name in {"task", "task_tool"} and not _task_result_requires_execution(message):
            return "synthesizing"
        return "executing"
    return "planning"


def _route_skill_prompt(route: dict[str, Any] | None) -> str:
    if not isinstance(route, dict):
        return ""
    capability = str(
        route.get("capabilityId")
        or (route.get("routeDecision") or {}).get("capabilityId")
        or ""
    ).strip()
    if not capability or capability in {"general_agent", "general"}:
        return ""
    current_state = route_state(route)
    if current_state not in {"ACTION_SELECTION", "FALLBACK"}:
        return ""
    action_id = str(
        route.get("actionId")
        or (route.get("routeDecision") or {}).get("actionId")
        or ""
    ).strip() or None
    skill_prompt = skill_registry.prompt_for(capability, action_id=action_id)
    return f"\n\n{DOMAIN_PLANNER_PROMPT}\n\n{skill_prompt}" if skill_prompt else DOMAIN_PLANNER_PROMPT


def main_agent_phase_instructions(
    phase: MainAgentPhase,
    *,
    route: dict[str, Any] | None = None,
) -> str:
    """返回指定阶段应追加的中文提示词。

    参数：
        phase：已判定的主 Agent 阶段。
        route：当前回合最近一次路由工具返回的结构化事实；规划或执行阶段会据此
            追加对应领域 Skill，缺失时保持通用提示词。
    """
    prompts = {
        "planning": MAIN_AGENT_PLANNING_PROMPT,
        "executing": MAIN_AGENT_EXECUTION_PROMPT,
        "synthesizing": MAIN_AGENT_SYNTHESIS_PROMPT,
    }
    if phase not in prompts:
        raise ValueError(f"unknown main-agent phase: {phase}")
    value = prompts[phase]
    if phase == "planning":
        value += "\n\n" + CapabilityRegistry().catalog_prompt()
    if phase in {"planning", "executing"} and route is not None:
        value += _route_skill_prompt(route)
    return value


def main_agent_prompt_for_phase(
    phase: MainAgentPhase,
    *,
    route: dict[str, Any] | None = None,
) -> str:
    return "\n\n".join(
        (MAIN_AGENT_COMMON_PROMPT, _business_clock_prompt(), main_agent_phase_instructions(phase, route=route))
    )


def system_prompt() -> str:
    """返回兼容控制台的完整提示词。

    生产请求使用 ``MainAgentPhasePromptMiddleware`` 按回合动态注入；控制台和
    兼容调用没有中间件时，才使用这个包含全部阶段规则的静态版本。
    """
    return "\n\n".join(
        (
            main_agent_prompt_for_phase("planning"),
            MAIN_AGENT_EXECUTION_PROMPT,
            MAIN_AGENT_SYNTHESIS_PROMPT,
        )
    )


class MainAgentPhasePromptMiddleware(AgentMiddleware):
    name = "MainAgentPhasePromptMiddleware"

    @staticmethod
    def _override(request):
        state = getattr(request, "state", {}) or {}
        messages = list(state.get("messages") or [])
        phase = classify_main_agent_phase(messages)
        current_turn = messages
        latest_human = max(
            (i for i, message in enumerate(messages) if _message_type(message) in {"human", "user"}),
            default=-1,
        )
        if latest_human >= 0:
            current_turn = messages[latest_human + 1 :]
        route = None
        for message in reversed(current_turn):
            if _message_type(message) != "tool" or _message_tool_name(message) != "route_conversation":
                continue
            content = message.get("content") if isinstance(message, dict) else getattr(message, "content", "")
            try:
                parsed = content if isinstance(content, dict) else json.loads(content or "{}")
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict):
                parsed = parsed["data"]
            if isinstance(parsed, dict):
                route = parsed
            break
        base = getattr(request, "system_message", None)
        base_text = base.text if base is not None else ""
        marker = "<!-- kodagent-main-agent-phase:"
        if marker in base_text:
            base_text = base_text.split(marker, 1)[0].rstrip()
        text = (
            f"{base_text}\n\n{marker}{phase} -->\n"
            f"{_business_clock_prompt()}\n\n"
            f"{main_agent_phase_instructions(phase, route=route)}"
        )
        if phase == "planning":
            pending_prompt = pending_plan_prompt(state.get("pending_plan"))
            if pending_prompt:
                text += f"\n\n{pending_prompt}"
            # 候选摘要只帮助模型理解短句或指代；正式来源字段仍留在 checkpoint，
            # 必须由计划投影层按候选 ID 重新绑定，不能出现在系统提示词中。
            candidate_prompt = context_prompt(
                state.get("context_candidates"),
                messages=list(state.get("messages") or []),
            )
            if candidate_prompt:
                text += f"\n\n{candidate_prompt}"
        return request.override(system_message=SystemMessage(content=text))

    def wrap_model_call(self, request, handler):
        return handler(self._override(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._override(request))


__all__ = [
    "MAIN_AGENT_COMMON_PROMPT",
    "MAIN_AGENT_EXECUTION_PROMPT",
    "MAIN_AGENT_PLANNING_PROMPT",
    "MAIN_AGENT_SYNTHESIS_PROMPT",
    "MainAgentPhasePromptMiddleware",
    "classify_main_agent_phase",
    "main_agent_phase_instructions",
    "main_agent_prompt_for_phase",
    "system_prompt",
    "PROMPT_VERSION",
]
