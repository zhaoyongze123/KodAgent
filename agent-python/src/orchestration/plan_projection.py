"""把“已编译的 TaskPlan”投影成下一步真正会发生的模型调用。

模块定位
========
主 Agent 的每一次模型调用都会经过本中间件。它的职责不是“回答用户”，
而是保证模型的行为永远落在路由工具（route_conversation）已经编译好的
计划边界内，具体分三层：

1. 模型调用前（wrap_model_call / _override / _override_for_policy）
   按当前回合的路由状态把模型可见的工具列表（palette）裁剪成很小的集合：
   澄清回合只给 {report_progress, route_conversation}，已解析回合只给
   {executor}。模型永远看不到几十个业务工具，这是“工具少、不易出错”
   的关键机制。

2. 模型调用后（_enforce_handshake / _enforce_model_response / _execution_response）
   检查模型这次输出是否符合协议：该交握时有没有提交合法的 route_conversation
   调用、该执行时有没有调用编译出的执行器。不符合时用“代码拥有”的确定性
   行为替换模型输出，而不是让越权调用继续向下执行（即“兼容层/规范化”而非
   “直接中断报错”）。

3. 工具调用边界（wrap_tool_call / _bind_compiled_call / _inject_compiled_plan）
   把路由编译好的 canonical plan 规范化（重填参数）到工具调用上，防止模型
   改参数、漏参数、或把 UPDATE 误变成 CREATE。多轮候选先走 Java 核验，不会
   直接成为 canonical 写计划的来源。

为什么需要它
============
主图沿用 DeepAgents 的 ReAct 循环，但业务域有自己的路由状态机（route_state /
route_policy）。没有这层投影，模型既可以直接挑一个无关业务工具、也可以绕过
路由直接委派子 Agent，还会在已确定执行器的回合里“自由发挥”。本中间件是唯一
允许把“路由结果”变成“实际行为”的地方。

关键代码导航（按阅读顺序）
========================
- wrap_model_call / awrap_model_call          入口：四种回合模式的分派
- _override / _override_for_policy            工具列表裁剪（palette 屏蔽）
- decide_turn_policy（route_policy.py）        路由状态 -> 回合模式的决策表
- _enforce_handshake / _selection_tool_response / _selection_clarification
                                              交握回合的协议强制与兜底澄清
- _enforce_model_response                     澄清回合的越权工具拦截
- _execution_response / _execution_clarification  已解析回合的执行强制
- _bind_compiled_call / _inject_compiled_plan  工具边界参数规范化（兼容层）
- _terminal_route_response                    确定性终态回复
"""

from __future__ import annotations

import json
from copy import copy
from dataclasses import replace
import os
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage

from .capabilities import action_execution_class, resolve_action
from .phase_prompt import classify_main_agent_phase
from .route_policy import (
    TurnMode,
    TurnPolicy,
    decide_turn_policy,
    selection_action,
)
from .pending_plan import merge_resume_route_call
from .conversation_context import (
    audit_context_decision,
    context_candidate_for_route_call,
    context_candidate_is_recent_for_direct_lookup,
    context_candidate_proof,
    context_candidate_reference_is_unambiguous,
    context_shadow_mode,
)
from .target_resolution import is_target_resolution_route
from .domain_dispatch import (
    domain_agent_for_route,
    serialize_work_order,
    work_order_from_route,
)
from .delegated_receipt import (
    parse_approval_draft_receipt,
    parse_execution_receipt,
    parse_meeting_draft_receipt,
    parse_party_file_draft_receipt,
    parse_personal_schedule_draft_receipt,
)
from .route_state import (
    current_turn_messages as _current_turn_messages,
    message_content as _content,
    message_name as _tool_name,
    message_type as _message_type,
    route_action_id as _route_action_id,
    route_capability as _route_capability,
    route_result as _route_result,
)
from ..tools.common.conversation import route_conversation_model_schema
from ..tools.common.events import narration_validation_issues


class PlanToolProjectionMiddleware(AgentMiddleware):
    """在计划编译完成后投影工具，并强制模型遵守计划边界。

    ``route_conversation`` 返回前保留 DeepAgents 的常规控制面工具；一旦返回
    ``RESOLVED`` 计划，本中间件只向模型暴露该计划绑定的执行器。这样既保留
    原有 ReAct 循环和 checkpoint 语义，又消除跨领域误选工具与绕过编译器的路径。
    """

    name = "PlanToolProjectionMiddleware"

    _AUTO_SELECTION_MARKER = "auto_action_selection_route"
    _AUTO_EXECUTION_MARKER = "auto_compiled_executor_call"
    _PROTOCOL_MARKERS = (
        "<|dsml|>", "<tool_calls", "</tool_calls>", "<invoke name=",
        "<function_calls>", "</function_calls>",
    )

    @staticmethod
    def _tool_name(tool: Any) -> str:
        if isinstance(tool, dict):
            direct = tool.get("name")
            function = tool.get("function")
            nested = function.get("name") if isinstance(function, dict) else None
            return str(direct or nested or "")
        return str(getattr(tool, "name", "") or "")

    @staticmethod
    def _response_messages(response):
        if isinstance(response, AIMessage):
            return [response]
        return list(getattr(response, "result", None) or [])

    @staticmethod
    def _replace_response_messages(response, messages):
        if isinstance(response, AIMessage):
            return messages[0] if messages else response
        try:
            return replace(response, result=messages)
        except TypeError:
            updated = copy(response)
            updated.result = messages
            return updated

    @classmethod
    def _has_auto_selection_attempt(cls, request) -> bool:
        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        return any(
            _message_type(message) == "ai"
            and (
                getattr(message, "response_metadata", {}) or {}
            ).get(cls._AUTO_SELECTION_MARKER) is True
            for message in messages
        )

    @staticmethod
    def _current_user_message(request) -> str:
        messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        for message in reversed(messages):
            if _message_type(message) not in {"human", "user"}:
                continue
            content = _content(message)
            if isinstance(content, str) and content.strip():
                return content.strip()
        return ""

    @classmethod
    def _selection_tool_response(cls, request, response, route):
        # 交握回合专用：当模型这次“只回了一段话、没有提交任何工具调用”，
        # 而路由事实又能唯一推断出动作时，这里代模型合成一个 route_conversation
        # 调用（并打上 _AUTO_SELECTION_MARKER 标记，防止下一回合重复合成）。
        # 相当于把“该交握却没说协议语言”的模型输出规范化成合法调用。
        if cls._has_auto_selection_attempt(request):
            return None
        messages = cls._response_messages(response)
        target_index = next(
            (
                index for index in range(len(messages) - 1, -1, -1)
                if _message_type(messages[index]) == "ai"
            ),
            None,
        )
        if target_index is None:
            return None
        target = messages[target_index]
        if getattr(target, "tool_calls", None) or (
            isinstance(target, dict) and target.get("tool_calls")
        ):
            return None
        selection = selection_action(route)
        if selection is None:
            return None
        action, candidate, query = selection
        # “预约”动词只能把模型带到 Action Catalog，不能让代码用空计划替它
        # 提交第二阶段调用。缺少模型结构化字段时留给一次 route-only 重试，模型
        # 仍能读取当前用户原文和字段 schema；两次都未提交才确定性澄清。
        if not candidate and not query:
            return None
        args = {
            "message": cls._current_user_message(request),
            "capability_id": action.capability_id,
            "action_id": action.action_id,
            "candidate_plan": candidate,
            "query_intent": query,
        }
        execution_class = action_execution_class(action).strip()
        if execution_class:
            args["execution_class"] = execution_class
        call = {
            "name": "route_conversation",
            "args": args,
            "id": f"action-selection-{target_index + 1}",
            "type": "tool_call",
        }
        metadata = {
            **(getattr(target, "response_metadata", {}) or {}),
            cls._AUTO_SELECTION_MARKER: True,
        }
        replacement = target.model_copy(
            deep=True,
            update={"content": "", "tool_calls": [call], "response_metadata": metadata},
        )
        updated = list(messages)
        updated[target_index] = replacement
        return cls._replace_response_messages(response, updated)

    @classmethod
    def _has_valid_route_tool_call(cls, response, route) -> bool:
        messages = cls._response_messages(response)
        target = next(
            (message for message in reversed(messages) if _message_type(message) == "ai"),
            None,
        )
        calls = getattr(target, "tool_calls", None) or (
            target.get("tool_calls") if isinstance(target, dict) else []
        )
        if not calls:
            return False
        capability = _route_capability(route)
        for call in calls:
            if not isinstance(call, dict) or str(call.get("name") or "") != "route_conversation":
                return False
            args = call.get("args") if isinstance(call.get("args"), dict) else {}
            if str(args.get("capability_id") or "").strip() != capability:
                return False
            requested = str(args.get("action_id") or "").strip()
            action = resolve_action(capability, requested)
            # Aliases may be accepted by the transport adapter, but the
            # second-stage protocol must emit the catalog's formal id.
            if action is None or requested != action.action_id:
                return False
        return True

    @staticmethod
    def _route_only_retry(request):
        allowed = []
        for item in request.tools:
            name = getattr(item, "name", None)
            if isinstance(item, dict):
                name = name or item.get("name")
            if name == "route_conversation":
                allowed.append(item)
        return request.override(tools=allowed)

    @staticmethod
    def _selection_clarification():
        # 交握彻底失败后的确定性兜底消息（不再调用模型）。
        # 只有“自动合成路由调用”也失败、且重试也失败时才会走到这里；
        # 正常回合不应触发。一旦高频出现，说明路由事实缺失或消息流被占位
        # ToolMessage（do-not-render-*）污染，需要查 route_result 的解析。
        return AIMessage(
            name="oa-main-agent",
            content="请明确您希望完成的具体业务操作，并补充必要的信息后继续。",
            response_metadata={
                "deterministicTerminal": True,
                "routeState": "ACTION_SELECTION",
                "routeFailure": "action_selection_boundary",
            },
        )

    @classmethod
    def _enforce_handshake(cls, request, response, route, handler):
        """HANDSHAKE turns must submit the registered action.

        # 交握模式（ACTION_SELECTION 且已能唯一推断出动作）：模型必须提交
        # 合法路由调用。优先级：
        #   1. 模型只回了正文 -> 自动合成 route_conversation 调用；
        #   2. 模型已提交合法调用 -> 放行；
        #   3. 历史里已有自动合成标记但这次又失败 -> 确定性澄清（硬兜底）；
        #   4. 否则把工具列表裁剪成只剩 route_conversation 重试一次，
        #      再失败才走确定性澄清。
        This is the only place a second model call can still be forced:
        the payload already uniquely identifies an action, so a prose-only
        answer or an invalid tool call is a protocol miss. The synthesized
        call consumes the one retry; afterwards code answers deterministically.
        """
        projected = cls._selection_tool_response(request, response, route)
        if projected is not None:
            return projected
        if cls._has_valid_route_tool_call(response, route):
            return response
        if cls._has_auto_selection_attempt(request):
            return cls._selection_clarification()
        retry_request = cls._route_only_retry(request)
        retry_response = handler(retry_request)
        projected = cls._selection_tool_response(retry_request, retry_response, route)
        if projected is not None:
            return projected
        if cls._has_valid_route_tool_call(retry_response, route):
            return retry_response
        return cls._selection_clarification()

    @classmethod
    async def _enforce_handshake_async(cls, request, response, route, handler):
        projected = cls._selection_tool_response(request, response, route)
        if projected is not None:
            return projected
        if cls._has_valid_route_tool_call(response, route):
            return response
        if cls._has_auto_selection_attempt(request):
            return cls._selection_clarification()
        retry_request = cls._route_only_retry(request)
        retry_response = await handler(retry_request)
        projected = cls._selection_tool_response(retry_request, retry_response, route)
        if projected is not None:
            return projected
        if cls._has_valid_route_tool_call(retry_response, route):
            return retry_response
        return cls._selection_clarification()

    @classmethod
    def _enforce_model_response(cls, request, response, policy: TurnPolicy):
        """MODEL_RESPONSE turns may answer naturally, but never with tools
        # 澄清/自然回复回合：模型可以自由组织语言，但工具调用必须落在受控
        # palette 内（通常是 route_conversation）。出现越权工具调用时用确定性
        # 澄清整体替换——宁可代码回答，也不让“字段澄清”悄悄变成业务工具调用。
        outside the restricted palette. An off-palette provider call is
        replaced by the deterministic clarification so a field clarification
        cannot quietly become a business tool invocation."""
        messages = cls._response_messages(response)
        target = next(
            (message for message in reversed(messages) if _message_type(message) == "ai"),
            None,
        )
        if target is None:
            return response
        calls = getattr(target, "tool_calls", None) or (
            target.get("tool_calls") if isinstance(target, dict) else []
        )
        if not calls:
            return response
        allowed = set(policy.planning_tools)
        for call in calls:
            name = str(call.get("name") or "") if isinstance(call, dict) else ""
            if name not in allowed:
                return cls._selection_clarification()
        return response

    @classmethod
    def _requires_initial_route(cls, request, route) -> bool:
        """判断无路由首轮是否必须完成一次 ``route_conversation`` 协议调用。

        闲聊可以直接回答，但被轻量分类器识别为需要工具的业务请求不能只生成一
        段澄清文案就结束，否则没有结构化 ``FIELD_CLARIFICATION``，下一轮也无法
        恢复待补计划。这里不判断具体领域或动作，只复用已有分类器判断“是否进入
        业务路由”；真正的 capability/action 仍由模型和 Action Catalog 决定。
        """

        if route is not None:
            return False
        # 当前回合没有路由工具时（例如协议防火墙或最小化单测），不能凭分类器
        # 虚构一次重试；只有正常规划 palette 实际提供了该工具才执行此规则。
        if "route_conversation" not in {
            cls._tool_name(tool) for tool in getattr(request, "tools", []) or []
        }:
            return False
        from ..services.conversation_router import classify_message

        return bool(classify_message(cls._current_user_message(request)).needs_tools)

    @classmethod
    def _enforce_initial_route(cls, request, response, handler):
        """首轮业务请求必须提交路由工具；失败时只做一次受限重试。

        重试工具列表只有 ``route_conversation``，因此这条修复不会为模型开放任
        何领域工具或执行器。第二次仍未遵守协议时返回确定性澄清，避免无限重试。
        """

        if cls._has_any_route_tool_call(response):
            return response
        retry_response = handler(cls._route_only_retry(request))
        if cls._has_any_route_tool_call(retry_response):
            return retry_response
        return cls._selection_clarification()

    @classmethod
    async def _enforce_initial_route_async(cls, request, response, handler):
        if cls._has_any_route_tool_call(response):
            return response
        retry_response = await handler(cls._route_only_retry(request))
        if cls._has_any_route_tool_call(retry_response):
            return retry_response
        return cls._selection_clarification()

    @classmethod
    def _has_any_route_tool_call(cls, response) -> bool:
        """确认模型已进入路由协议；具体参数校验仍由 Tool Schema 负责。"""

        messages = cls._response_messages(response)
        target = next(
            (message for message in reversed(messages) if _message_type(message) == "ai"),
            None,
        )
        calls = getattr(target, "tool_calls", None) or (
            target.get("tool_calls") if isinstance(target, dict) else []
        )
        return bool(calls) and all(
            isinstance(call, dict)
            and str(call.get("name") or "") == "route_conversation"
            for call in calls
        )

    @classmethod
    def _executor_name(cls, route) -> str:
        return str(
            route.get("executionTool")
            or ((route.get("routeDecision") or {}).get("executionTool") or "")
        ).strip()

    @classmethod
    def _tool_call_id(cls, message) -> str:
        value = getattr(message, "tool_call_id", None)
        if isinstance(message, dict):
            value = message.get("tool_call_id")
        return str(value or "").strip()

    @classmethod
    def _delegate_call_ids(cls, request, delegate_agent: str) -> set[str]:
        """Return every ``task`` call id that targeted the delegate agent.

        # DeepAgents 生成的 task ToolMessage 没有 name，无法像普通执行器那样
        # 按工具名识别。改用 tool_call_id 反向找到父级 AI 消息里的 task 调用，
        # 只要 args.subagent_type 命中领域子 Agent 名即可确认“委托已执行”。
        """
        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        ids: set[str] = set()
        for message in messages:
            if _message_type(message) != "ai":
                continue
            calls = getattr(message, "tool_calls", None)
            if isinstance(message, dict):
                calls = calls or message.get("tool_calls")
            for call in calls or []:
                if not isinstance(call, dict) or str(call.get("name") or "") != "task":
                    continue
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                if str(args.get("subagent_type") or "") == delegate_agent:
                    ids.add(str(call.get("id") or ""))
        return ids

    @classmethod
    def _delegate_was_called(cls, request, route, delegate_agent: str) -> bool:
        """仅在子 Agent 返回“真实 executor 成功”回执时认定委托完成。

        ``task`` ToolMessage 只表示子 Agent 已返回，不能证明它没有停在 helper
        查询、参数错误或授权拒绝处。执行完成必须由 child middleware 从 executor
        的成功 ToolMessage 生成回执，主图绝不从模型叙述或任意 task 返回推断。
        """
        call_ids = cls._delegate_call_ids(request, delegate_agent)
        if not call_ids:
            return False
        executor = cls._executor_name(route)
        expected_plan_id = str(route.get("planId") or route.get("plan_id") or "").strip()
        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        for message in messages:
            if (
                _message_type(message) != "tool"
                or cls._tool_call_id(message) not in call_ids
            ):
                continue
            content = _content(message)
            receipt = parse_execution_receipt(content)
            if (
                receipt is not None
                and receipt.executor_tool == executor
                and receipt.plan_id == expected_plan_id
            ):
                return True
            # 会议保留已有的专用草稿凭据，它同样只能由确定性工作流成功结果
            # 创建。待后续统一确认链路时再收敛其展示字段，不破坏现有审批卡。
            meeting_receipt = parse_meeting_draft_receipt(content)
            if (
                meeting_receipt is not None
                and executor == "run_meeting_booking_workflow"
            ):
                return True
            # 写工作流生成草稿后会用领域专用回执替代通用执行回执。它不含
            # planId（草稿卡不应暴露编译内部字段），因此必须同时受“当前 task
            # 绑定的子 Agent + 本次编译 executor”限制，不能按 domain 猜测。
            if executor == "run_personal_schedule_workflow" and parse_personal_schedule_draft_receipt(content):
                return True
            if executor == "run_party_file_write_workflow" and parse_party_file_draft_receipt(content):
                return True
            if executor == "run_approval_write_workflow" and parse_approval_draft_receipt(content):
                return True
        return False

    @classmethod
    def _delegate_description(cls, request, route, delegate_agent: str) -> str:
        """Build the code-owned command transported through ``task``.

        A DeepAgents child receives only a task description, so that string is
        a transport envelope rather than a prompt.  The model never authors
        it; invalid/missing compiled state refuses to create a task instead of
        falling back to prose instructions.
        """
        work_order = work_order_from_route(
            route,
            user_context=cls._current_user_message(request),
        )
        if work_order is None:
            return ""
        return serialize_work_order(work_order)

    @classmethod
    def _executor_was_called(cls, request, route, delegate_agent: str | None = None) -> bool:
        executor = cls._executor_name(route)
        if delegate_agent and cls._delegate_was_called(request, route, delegate_agent):
            return True
        if not executor:
            return False
        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        # A checkpoint created before the WorkOrder migration may contain a
        # direct executor ToolMessage.  It is an already-performed effect, so
        # recognize it during resume instead of dispatching the same plan to a
        # child a second time.
        return any(
            _message_type(message) == "tool" and _tool_name(message) == executor
            for message in messages
        )

    @classmethod
    def _has_auto_executor_attempt(cls, request) -> bool:
        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        return any(
            _message_type(message) == "ai"
            and (getattr(message, "response_metadata", {}) or {}).get(
                cls._AUTO_EXECUTION_MARKER
            ) is True
            for message in messages
        )

    @classmethod
    def _has_valid_executor_call(cls, response, route, delegate_agent: str | None = None) -> bool:
        executor = cls._executor_name(route)
        if not executor and not delegate_agent:
            return False
        messages = cls._response_messages(response)
        target = next(
            (message for message in reversed(messages) if _message_type(message) == "ai"),
            None,
        )
        calls = getattr(target, "tool_calls", None) or (
            target.get("tool_calls") if isinstance(target, dict) else []
        )
        if not calls:
            return False
        if delegate_agent:
            # 委托模式：合法的执行调用是发给领域子 Agent 的 task 调用，且
            # subagent_type 必须命中策略里选定的子 Agent 名。
            return all(
                isinstance(call, dict)
                and str(call.get("name") or "") == "task"
                and str((call.get("args") or {}).get("subagent_type") or "") == delegate_agent
                for call in calls
            )
        return all(
            isinstance(call, dict) and str(call.get("name") or "") == executor
            for call in calls
        )

    @classmethod
    def _compiled_executor_call(cls, request, route, delegate_agent: str | None = None):
        executor = cls._executor_name(route)
        if not isinstance(route.get("executionPlan"), dict):
            return None
        if delegate_agent:
            if not executor or work_order_from_route(route) is None:
                return None
            call = {
                "name": "task",
                "args": {},
                "id": f"compiled-delegate-{delegate_agent}",
                "type": "tool_call",
            }
            return cls._bind_compiled_call(request, call)
        if not executor:
            return None
        call = {
            "name": executor,
            "args": {},
            "id": f"compiled-executor-{executor}",
            "type": "tool_call",
        }
        # ``ModelRequest`` deliberately has no ``tool_call`` field. Bind the
        # route-owned arguments directly while constructing the AI message;
        # ``_inject_compiled_plan`` remains reserved for ToolCallRequest.
        return cls._bind_compiled_call(request, call)

    @staticmethod
    def _execution_clarification():
        return AIMessage(
            name="oa-main-agent",
            content="当前业务计划未能完成，请稍后重试。",
            response_metadata={
                "deterministicTerminal": True,
                "routeFailure": "resolved_executor_boundary",
            },
        )

    @classmethod
    def _code_owned_execution_call(cls, request, route, delegate_agent: str | None = None):
        """Emit the compiled executor call without invoking the parent model.

        Once ``RESOLVED`` exists, deciding whether to call an executor is not
        language generation.  Calling a model just to obtain the same ``task``
        produces the protocol-leak and wrong-tool failure modes this boundary
        was introduced to remove.
        """
        if cls._executor_was_called(request, route, delegate_agent):
            return None
        if cls._has_auto_executor_attempt(request):
            return cls._execution_clarification()
        call = cls._compiled_executor_call(request, route, delegate_agent)
        if call is None:
            return cls._execution_clarification()
        return AIMessage(
            name="oa-main-agent",
            content="",
            tool_calls=[call],
            response_metadata={cls._AUTO_EXECUTION_MARKER: True},
        )

    @classmethod
    def _protocol_firewall(cls, response, route: dict[str, Any] | None = None):
        """Prevent provider protocol prose from becoming user-visible text.

        The model can leak an unparsed tool protocol, but it can also quote a
        route state, WorkOrder or executor name in ordinary text.  Those are
        equally internal.  The firewall therefore shares the same validator
        as ``report_progress`` rather than relying on syntax markers alone.
        """
        messages = cls._response_messages(response)
        target_index = next(
            (index for index in range(len(messages) - 1, -1, -1)
            if _message_type(messages[index]) == "ai"),
            None,
        )
        if target_index is None:
            return response
        target = messages[target_index]
        content = _content(target)
        if not isinstance(content, str):
            return response
        calls = getattr(target, "tool_calls", None) or (
            target.get("tool_calls") if isinstance(target, dict) else []
        )
        syntax_leak = any(marker in content.lower() for marker in cls._PROTOCOL_MARKERS)
        # A valid tool invocation commonly has an empty assistant body.  Empty
        # prose is invalid for a user narration, but it is not a protocol leak
        # and must not invalidate the invocation itself.
        narration_issues = (
            narration_validation_issues(content)
            if route is not None and content.strip()
            else ()
        )
        if not syntax_leak and not narration_issues:
            return response
        # Parsed calls are still handled by LangGraph.  Only suppress their
        # duplicate raw representation. For a route-state leak without a
        # call, reuse the compiler's user-facing clarification instead of
        # exposing its protocol vocabulary.
        clarification = route.get("clarification") if isinstance(route, dict) else {}
        question = str(clarification.get("question") or "").strip() if isinstance(clarification, dict) else ""
        if calls:
            replacement_content = ""
        elif syntax_leak:
            # Keep the established explicit failure for raw, unparsed tool
            # protocol.  A route clarification is not an accurate substitute
            # for a provider transport/protocol failure.
            replacement_content = (
                "模型执行协议未被正确解析，已阻止原始内容展示。请重试该操作。"
            )
        else:
            replacement_content = question or "当前请求需要补充必要信息后继续。"
        metadata = {
            **(getattr(target, "response_metadata", {}) or {}),
            "protocolFirewall": True,
            "routeFailure": (
                "MODEL_TOOL_PROTOCOL_UNSUPPORTED"
                if syntax_leak and not calls
                else "MODEL_INTERNAL_NARRATION_BLOCKED"
                if narration_issues and not calls
                else None
            ),
            **({"narrationIssues": list(narration_issues)} if narration_issues else {}),
        }
        replacement = target.model_copy(
            deep=True,
            update={"content": replacement_content, "response_metadata": metadata},
        )
        updated = list(messages)
        updated[target_index] = replacement
        return cls._replace_response_messages(response, updated)

    @classmethod
    def _execution_response(cls, request, response, route):
        """Prevent a resolved plan from being replaced by model prose.

        # EXECUTE 回合的核心逻辑（也是“兼容层/规范化”思想的实现）：
        # 路由已 RESOLVED 且执行器已编译后，模型必须调用该执行器。若模型
        # 只回话未调工具、或调用了别的工具，这里用编译好的 executor 调用
        # 直接替换模型输出（并打 _AUTO_EXECUTION_MARKER 标记防重复合成），
        # 而不是报错中断——因为“该执行什么”是代码从路由事实里确定的。
        # 委托模式（policy.delegate_agent）：执行器换成了 DeepAgents 的 task
        # 工具，合法输出是发给领域子 Agent 的 task 调用；合成/绑定逻辑由
        # _compiled_executor_call / _bind_compiled_call 负责，参数里的权威计划
        # 被嵌入 description，子 Agent 侧再确定性绑定到工作流调用上。
        Once the compiler binds an executor, the model may summarize only
        after that executor has returned a ToolMessage.  A provider response
        without the call is converted into the same typed call the model was
        allowed to make; this keeps Java as the source of business facts and
        prevents a false "service unavailable" answer from ending the run.
        """
        if not route or str(route.get("planStatus") or "").upper() != "RESOLVED":
            return response
        if os.getenv("OA_AGENT_INTENT_EVAL_ROUTE_ONLY", "false").lower() in {"1", "true", "yes", "on"}:
            # Golden-set evaluation must measure routing/action selection
            # without creating drafts, approvals or external effects. This
            # switch is test-only and is never enabled by deployment config.
            return response
        delegate_agent = domain_agent_for_route(route)
        if cls._executor_was_called(request, route, delegate_agent):
            return response
        if cls._has_valid_executor_call(response, route, delegate_agent):
            return response
        if cls._has_auto_executor_attempt(request):
            return cls._execution_clarification()
        call = cls._compiled_executor_call(request, route, delegate_agent)
        if call is None:
            return cls._execution_clarification()
        messages = cls._response_messages(response)
        target_index = next(
            (
                index for index in range(len(messages) - 1, -1, -1)
                if _message_type(messages[index]) == "ai"
            ),
            None,
        )
        if target_index is None:
            return cls._execution_clarification()
        target = messages[target_index]
        metadata = {
            **(getattr(target, "response_metadata", {}) or {}),
            cls._AUTO_EXECUTION_MARKER: True,
        }
        replacement = target.model_copy(
            deep=True,
            update={"content": "", "tool_calls": [call], "response_metadata": metadata},
        )
        updated = list(messages)
        updated[target_index] = replacement
        return cls._replace_response_messages(response, updated)

    @staticmethod
    def _terminal_route_response(request):
        """Return a deterministic user response for a structured boundary.

        # 确定性终态（UNSUPPORTED / CONFIRMATION_REQUIRED）：根本不调用模型，
        # 直接由代码返回终态文案。字段澄清（FIELD_CLARIFICATION）不在此列，
        # 那是交互，措辞仍由模型负责。
        # This is now a thin compatibility view over :func:`decide_turn_policy`.
        Only boundaries the model must not interpret (``UNSUPPORTED`` and
        ``CONFIRMATION_REQUIRED``) short-circuit here. Field clarifications are
        interaction and stay with the model, which owns the wording.
        """
        policy = decide_turn_policy(
            _route_result(
                list((getattr(request, "state", {}) or {}).get("messages") or [])
            )
        )
        if policy.mode != TurnMode.DETERMINISTIC_TERMINAL:
            return None
        return AIMessage(
            name="oa-main-agent",
            content=policy.terminal_content,
            response_metadata=policy.terminal_metadata,
        )

    @staticmethod
    def _override(request):
        # 模型调用前的工具列表裁剪入口：先算路由与回合策略，再交给
        # _override_for_policy 生成“只含当前回合合法工具”的请求副本。
        route = _route_result(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        return PlanToolProjectionMiddleware._override_for_policy(request, decide_turn_policy(route), route)

    @classmethod
    def _override_for_policy(cls, request, policy: TurnPolicy, route):
        # palette 屏蔽的具体实现：
        # - 合成为“synthesizing”阶段或执行器刚返回 ToolMessage 时，直接清空
        #   工具（本轮只允许收尾叙述，不能再发起新的业务操作）；
        # - 否则按 policy.planning_tools 白名单过滤 request.tools。
        # 这就是“模型每次调用前可见工具变少、不易出错”的关键机制。
        import logging
        _log = logging.getLogger(__name__)
        state = getattr(request, "state", {}) or {}
        messages = list(state.get("messages") or [])
        turn_messages = _current_turn_messages(messages)
        _log.warning(
            "plan projection: messages=%s turn=%s route=%s latest_tool=%s phase=%s tools=%s",
            len(messages), len(turn_messages),
            {k: route.get(k) for k in ("planStatus", "executionTool", "execution_class")} if route else None,
            next((_tool_name(message) for message in reversed(messages) if _message_type(message) == "tool"), ""),
            classify_main_agent_phase(messages),
            [cls._tool_name(item) for item in request.tools],
        )
        executor = route.get("executionTool") if route else None
        delegate_agent = domain_agent_for_route(route) if route else None
        latest_tool = next((_tool_name(message) for message in reversed(messages) if _message_type(message) == "tool"), "")
        delegate_executed = bool(delegate_agent) and cls._executor_was_called(request, route, delegate_agent)
        if classify_main_agent_phase(messages) == "synthesizing" or (
            executor and latest_tool == executor
        ) or delegate_executed:
            # The synthesis phase must not start a new business operation.
            # A confirmed interrupt resumes its already-persisted ToolCall
            # through LangGraph's ToolNode; it never needs to be made visible
            # to a later model call. Re-exposing a pending confirmation tool
            # here would let ordinary text recreate a durable write path.
            # 委托模式下，领域子 Agent 已返回（task ToolMessage 已落盘），
            # 本轮同样只允许收尾叙述，不能再发起第二次委托。
            return request.override(tools=[])
        # The policy owns the palette for every routed turn. This is the only
        # filter left in the middleware: code never re-combines planStatus,
        # actionId and executionClass to derive behaviour.
        allowed_names = set(policy.planning_tools)
        if not allowed_names:
            return request.override(tools=[])
        allowed = []
        for item in request.tools:
            name = cls._tool_name(item)
            if name in allowed_names:
                allowed.append(item)
        # The ToolNode still owns the stable executable route tool.  This
        # model-facing descriptor is only for the next ``bind_tools`` call:
        # its enum values are rebuilt from the Java-synchronized catalog on
        # every turn, so action names are not prompt constants.
        capability = _route_capability(route)
        selected_action = _route_action_id(route)
        action_required = policy.mode == TurnMode.HANDSHAKE
        allowed = [
            route_conversation_model_schema(
                capability,
                selected_action_id=selected_action or None,
                require_action=action_required,
            )
            if (
                cls._tool_name(item) == "route_conversation"
            )
            else item
            for item in allowed
        ]
        # Returning the untouched request when a generated tool (notably
        # DeepAgents' task) is absent would re-open every original business
        # tool.  An unavailable legal palette is closed, never widened.
        return request.override(tools=allowed)

    def wrap_model_call(self, request, handler):
        # 模型调用入口（同步版）。整个中间件的执行顺序：
        #   1. 用全量消息流算出路由事实（route）与回合策略（policy）；
        #   2. 终态回合（UNSUPPORTED / CONFIRMATION_REQUIRED）不调模型，
        #      直接返回确定性文案；
        #   3. 其余回合先把 palette 裁剪好，再调用真正的模型（handler）；
        #   4. 按回合模式检查模型输出：
        #      - HANDSHAKE       -> _enforce_handshake（强制提交路由调用）
        #      - MODEL_RESPONSE  -> _enforce_model_response（防越权工具）
        #      - EXECUTE         -> _execution_response（防计划被散文替换）
        all_messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        route = _route_result(all_messages)
        policy = decide_turn_policy(route)
        if policy.mode == TurnMode.DETERMINISTIC_TERMINAL:
            return AIMessage(
                name="oa-main-agent",
                content=policy.terminal_content,
                response_metadata=policy.terminal_metadata,
            )
        if policy.mode == TurnMode.EXECUTE:
            code_owned = self._code_owned_execution_call(
                request, route, policy.delegate_agent,
            )
            if code_owned is not None:
                return code_owned
        response = handler(self._override_for_policy(request, policy, route))
        if self._requires_initial_route(request, route):
            return self._protocol_firewall(
                self._enforce_initial_route(request, response, handler), route
            )
        if policy.mode == TurnMode.HANDSHAKE:
            return self._protocol_firewall(self._enforce_handshake(request, response, route, handler), route)
        if policy.mode == TurnMode.MODEL_RESPONSE:
            return self._protocol_firewall(self._enforce_model_response(request, response, policy), route)
        return self._protocol_firewall(self._execution_response(request, response, route), route)

    async def awrap_model_call(self, request, handler):
        all_messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        route = _route_result(all_messages)
        policy = decide_turn_policy(route)
        if policy.mode == TurnMode.DETERMINISTIC_TERMINAL:
            return AIMessage(
                name="oa-main-agent",
                content=policy.terminal_content,
                response_metadata=policy.terminal_metadata,
            )
        if policy.mode == TurnMode.EXECUTE:
            code_owned = self._code_owned_execution_call(
                request, route, policy.delegate_agent,
            )
            if code_owned is not None:
                return code_owned
        response = await handler(self._override_for_policy(request, policy, route))
        if self._requires_initial_route(request, route):
            return self._protocol_firewall(
                await self._enforce_initial_route_async(request, response, handler), route
            )
        if policy.mode == TurnMode.HANDSHAKE:
            return self._protocol_firewall(
                await self._enforce_handshake_async(request, response, route, handler), route
            )
        if policy.mode == TurnMode.MODEL_RESPONSE:
            return self._protocol_firewall(self._enforce_model_response(request, response, policy), route)
        return self._protocol_firewall(self._execution_response(request, response, route), route)

    @classmethod
    def _bind_compiled_call(cls, request, call):
        """Bind the canonical plan to the projected executor call.

        # 兼容层/规范化核心：路由工具已经返回过权威的执行计划（canonical
        # plan）。这里在工具调用边界把计划字段重填进模型生成的调用参数，
        # 防止模型篡改关键字段（例如把相对日期“明天”改掉、把 UPDATE 退化成
        # CREATE、丢失 source_booking_id / source_party_file_id）。模型只负责
        # 决定“调不调”，参数内容以路由编译结果为准。
        # Some providers emit a tool call with an empty/partial argument object
        even though the route tool already returned the canonical execution
        plan.  Letting that call reach the executor makes the executor reject
        it and causes the ReAct loop to retry indefinitely.  The route result
        is the authoritative source, so the middleware fills (and replaces)
        the public ``plan`` argument at the tool boundary.  This keeps the
        model free to choose *whether* to execute while code owns *what* is
        executed.
        """
        call = dict(call or {})
        name = str(call.get("name") or "")
        if name == "route_conversation":
            state = getattr(request, "state", {}) or {}
            # 模型输入中的授权标记一律无效。只有本中间件从 checkpoint 找到有效
            # 候选后，才会在下面重新写入来源字段和内部授权标记。
            raw_args = dict(call.get("args") or {})
            raw_plan = raw_args.get("candidate_plan")
            if isinstance(raw_plan, str):
                try:
                    parsed_plan = json.loads(raw_plan)
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed_plan = None
                if isinstance(parsed_plan, dict):
                    raw_plan = parsed_plan
            if isinstance(raw_plan, dict):
                raw_plan = dict(raw_plan)
                raw_plan.pop("_authorized_source_fields", None)
                raw_plan.pop("_context_candidate_proof", None)
                raw_plan.pop("_context_candidate_kind", None)
                raw_args["candidate_plan"] = raw_plan
            call["args"] = raw_args
            call = merge_resume_route_call(call, state.get("pending_plan"))
            args = dict(call.get("args") or {})
            candidate = context_candidate_for_route_call(
                state, args.get("context_candidate_id"),
            )
            requested_action = str(args.get("action_id") or "").strip()
            requested_capability = str(args.get("capability_id") or "").strip()
            context_intent_supplied = "context_intent" in args
            context_intent = str(args.get("context_intent") or "NEW_REQUEST").strip().upper()
            context_confidence = args.get("context_confidence")
            try:
                confidence_is_sufficient = context_confidence is None or float(context_confidence) >= 0.70
            except (TypeError, ValueError):
                confidence_is_sufficient = False
            messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
            user_message = ""
            for message in reversed(messages):
                if _message_type(message) in {"human", "user"}:
                    content = _content(message)
                    if isinstance(content, str):
                        user_message = content
                    break
            # 兼容已运行中的旧模型/旧 checkpoint：过去没有 context_intent 字段，
            # 但它已经提交了受限的 UPDATE/CANCEL + 候选 ID。仍让它通过同一份
            # 唯一性校验恢复来源字段；新提示词和新模型调用必须显式给出 intent。
            if (
                not context_intent_supplied
                and candidate is not None
                and candidate.kind in {"authorized_resource", "authorized_query"}
                and requested_action in candidate.action_ids
            ):
                context_intent = "REFER_TO_QUERY_CANDIDATE"
                # 旧 checkpoint/模型没有显式字段时也要把兼容判定写回调用参数，
                # 否则 route_conversation 会把它重新当作 NEW_REQUEST。
                args["context_intent"] = context_intent
            if (
                candidate is not None
                and candidate.kind in {"authorized_resource", "authorized_query"}
                and candidate.capability_id == requested_capability
                and requested_action in candidate.action_ids
                and context_intent == "REFER_TO_QUERY_CANDIDATE"
                and confidence_is_sufficient
                and not context_shadow_mode()
                and context_candidate_is_recent_for_direct_lookup(state, candidate)
                and context_candidate_reference_is_unambiguous(
                    state, candidate, user_message=user_message,
                )
            ):
                # 候选只能负责“定位对象”，不能把 source ID 升级成写操作事实。
                # 这里从 checkpoint 取出内部 ID，签发一个仅能调用 Java 详情工具的
                # targetResolution 标记；真正 UPDATE/CANCEL 需在只读回执后由代码
                # 二次编译。模型始终看不到 ID，也不能伪造这个标记。
                plan = args.get("candidate_plan")
                plan = dict(plan) if isinstance(plan, dict) else {}
                source_key = (
                    "source_schedule_id" if candidate.capability_id == "schedule"
                    else "source_booking_id" if candidate.capability_id == "meeting" else ""
                )
                source_id = candidate.trusted_plan.get(source_key) if source_key else None
                if source_id is None:
                    args.pop("context_candidate_id", None)
                    call["args"] = args
                    return call
                args["candidate_plan"] = {
                    **plan,
                    "_context_candidate_proof": context_candidate_proof(candidate.candidate_id),
                    "_context_candidate_kind": candidate.kind,
                    "_target_resolution": {
                        "candidateId": candidate.candidate_id,
                        "verificationTool": (
                            "get_personal_schedule" if candidate.capability_id == "schedule"
                            else "get_my_meeting_booking"
                        ),
                        source_key: source_id,
                        "operation": str(plan.get("operation") or "").upper(),
                    },
                }
                audit_context_decision(
                    state,
                    event="candidate_resolution_requested",
                    candidateId=candidate.candidate_id,
                    kind=candidate.kind,
                    intent=context_intent,
                    confidence=context_confidence,
                )
            elif (
                candidate is not None
                and candidate.kind == "pending_approval"
                and context_intent == "LOCATE_APPROVAL_CARD"
                and not context_shadow_mode()
                and context_candidate_reference_is_unambiguous(
                    state, candidate, user_message=user_message,
                )
            ):
                # 审批候选只可用于定位当前确认卡。这里不暴露给编译器的业务来源
                # 字段，也不让普通文本走确认提交；route_conversation 只会返回澄清卡。
                plan = args.get("candidate_plan")
                plan = dict(plan) if isinstance(plan, dict) else {}
                args["candidate_plan"] = {
                    **plan,
                    "_context_candidate_proof": context_candidate_proof(candidate.candidate_id),
                    "_context_candidate_kind": candidate.kind,
                }
                audit_context_decision(
                    state,
                    event="approval_candidate_located",
                    candidateId=candidate.candidate_id,
                    kind=candidate.kind,
                    intent=context_intent,
                    confidence=context_confidence,
                )
            else:
                # 无效、过期或领域/动作不匹配的候选不应留下可被下游误解的引用。
                args.pop("context_candidate_id", None)
                if candidate is not None:
                    audit_context_decision(
                        state,
                        event="candidate_rejected",
                        candidateId=candidate.candidate_id,
                        kind=candidate.kind,
                        intent=context_intent,
                        confidence=context_confidence,
                        reason=(
                            "shadow_mode" if context_shadow_mode()
                            else "stale_direct_locator" if candidate is not None and not context_candidate_is_recent_for_direct_lookup(state, candidate)
                            else "low_confidence" if not confidence_is_sufficient
                            else "mismatched_or_ambiguous"
                        ),
                    )
            # The user turn is the only trusted source for relative dates and
            # business intent. A provider may alter the free-form ``message``
            # argument while still selecting the correct action, which would
            # let it silently change "明天" to "今天" before the server-side
            # date normalizer runs. Always bind this field to the current user
            # turn; the model owns only the typed routing fields.
            for message in reversed(messages):
                if _message_type(message) not in {"human", "user"}:
                    continue
                content = _content(message)
                if isinstance(content, str) and content.strip():
                    if args.get("message") != content:
                        args["message"] = content
                    break
            call["args"] = args
            return call
        if name == "task":
            # 委托模式下的参数规范化：子 Agent 无状态，所有上下文只能写进
            # description。这里把“发给谁”和“带什么计划”都重新绑定为代码拥有
            # 的值——模型/子 Agent 无法改 subagent_type，也无法在重试时丢掉
            # RESOLVED task calls are entirely code-owned.  A fallback task is
            # intentionally left untouched because it has no compiled plan.
            messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
            route = _route_result(messages)
            delegate_agent = domain_agent_for_route(route) if route else None
            if not delegate_agent:
                return call
            args = dict(call.get("args") or {})
            if str(args.get("subagent_type") or "") != delegate_agent:
                args["subagent_type"] = delegate_agent
            description = cls._delegate_description(request, route, delegate_agent)
            if not description:
                return call
            args["description"] = description
            call["args"] = args
            return call
        if name not in {"execute_party_file_metadata_plan", "run_approval_query_plan", "get_my_calendar", "list_my_meeting_bookings", "get_my_meeting_booking", "get_personal_schedule", "run_meeting_booking_workflow", "run_personal_schedule_workflow", "create_party_file_draft", "update_party_file_draft", "delete_party_file_draft", "create_approval_withdraw_draft", "approval_report", "meeting_report", "schedule_report", "party_file_report"}:
            return call
        messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        route = _route_result(messages)
        if not route or route.get("planStatus") != "RESOLVED":
            return call
        executor = route.get("executionTool") or ((route.get("routeDecision") or {}).get("executionTool"))
        canonical = route.get("executionPlan")
        if executor != name or not isinstance(canonical, dict):
            return call
        if is_target_resolution_route(route):
            # 主图直调旧路径也只能携带由代码签发的定向 ID；子 Agent 路径由
            # WorkflowPlanBinderMiddleware 使用同一 canonical 字段重填。
            args = dict(call.get("args") or {})
            if name == "get_personal_schedule":
                args["schedule_id"] = canonical.get("sourceScheduleId")
            elif name == "get_my_meeting_booking":
                args["booking_id"] = canonical.get("sourceBookingId")
            call["args"] = args
            return call
        if name in {"create_party_file_draft", "update_party_file_draft", "delete_party_file_draft"}:
            args = dict(call.get("args") or {})
            # CREATE uses the generic draft schema; UPDATE/DELETE have
            # operation-specific schemas. The compiler owns the operation so
            # a retry cannot switch an update/delete into a publish.
            if name == "create_party_file_draft":
                args["operation"] = "CREATE"
            else:
                source_id = canonical.get("sourcePartyFileId")
                if source_id is not None:
                    args["source_party_file_id"] = source_id
            # The compiler has already validated these values. Re-apply them
            # on every retry so a provider cannot drop category/content or
            # accidentally turn an UPDATE/DELETE into an empty request.
            for key in ("title", "content", "category_name", "summary", "publish_time",
                        "targets", "distribute_to_self", "storage_type", "status"):
                if key in canonical:
                    args[key] = canonical[key]
            if "attachment_file_ids" in canonical:
                attachment_ids = canonical["attachment_file_ids"]
                args["attachment_file_ids"] = (
                    ",".join(str(item) for item in attachment_ids)
                    if isinstance(attachment_ids, list) else attachment_ids
                )
            call["args"] = args
            return call
        if name == "run_meeting_booking_workflow":
            # Operation and source booking are compiler-owned. Preserve other
            # fields extracted by the model (new time, subject, attendees),
            # but never let a partial retry turn UPDATE into CREATE.
            args = dict(call.get("args") or {})
            operation = canonical.get("operation")
            if operation:
                args["operation"] = operation
            if canonical.get("sourceBookingId") is not None:
                args["source_booking_id"] = canonical["sourceBookingId"]
            field_map = {
                "subject": "subject", "start_time": "start_time", "end_time": "end_time",
                "attendees": "attendee_names", "room_capacity": "room_capacity",
                "equipment": "equipment", "room_preference": "room_preference",
                "remark": "remark", "reason": "cancel_reason",
            }
            for source, target in field_map.items():
                if source in canonical:
                    args[target] = canonical[source]
            call["args"] = args
            return call
        if name == "run_personal_schedule_workflow":
            # The route boundary owns UPDATE/CANCEL operation and, after a
            # calendar query, the only authorized source schedule ID. A model
            # retry must not lose that binding or switch back to CREATE.
            args = dict(call.get("args") or {})
            operation = canonical.get("operation")
            if operation:
                args["operation"] = operation
            if canonical.get("sourceScheduleId") is not None:
                args["source_schedule_id"] = canonical["sourceScheduleId"]
            field_map = {
                "title": "title", "start_time": "start_time", "end_time": "end_time",
                "description": "description", "location": "location",
                "attendees": "attendee_user_ids", "other_participants": "other_participants",
            }
            for source, target in field_map.items():
                if source in canonical:
                    args[target] = canonical[source]
            call["args"] = args
            return call
        if name == "get_my_calendar":
            args = dict(call.get("args") or {})
            if canonical.get("startTime") is not None:
                args["start_time"] = canonical["startTime"]
            if canonical.get("endTime") is not None:
                args["end_time"] = canonical["endTime"]
            call["args"] = args
            return call
        if name == "list_my_meeting_bookings":
            args = dict(call.get("args") or {})
            if canonical.get("startTime") is not None:
                args["start_time"] = canonical["startTime"]
            if canonical.get("endTime") is not None:
                args["end_time"] = canonical["endTime"]
            call["args"] = args
            return call
        if name == "create_approval_withdraw_draft":
            args = dict(call.get("args") or {})
            if canonical.get("processInstanceId") is not None:
                args["process_instance_id"] = canonical["processInstanceId"]
            if canonical.get("reason") is not None:
                args["reason"] = canonical["reason"]
            call["args"] = args
            return call
        if name in {"approval_report", "meeting_report", "schedule_report", "party_file_report"}:
            # Reports accept ordinary named arguments, not the generic
            # ``plan`` envelope used by deterministic query executors.
            args = dict(call.get("args") or {})
            for key, value in canonical.items():
                if key not in {"operation", "rangeRequired"}:
                    args[key] = value
            call["args"] = args
            return call
        call["args"] = {"plan": canonical}
        return call

    @classmethod
    def _inject_compiled_plan(cls, request):
        """Bind canonical arguments at the actual tool-call boundary.

        # 工具真正被执行前（wrap_tool_call 钩子），再次把编译计划绑定到
        # ToolCallRequest.tool_call 上。与模型响应投影（_bind_compiled_call）
        # 的区别：这里是 ToolCallRequest 契约，模型响应那里是 ModelRequest。
        # 两层都做规范化，保证无论模型输出走哪条路径，执行器拿到的参数都
        # 与路由编译结果一致。
        # ``ToolCallRequest`` owns ``tool_call`` and supports ``override``;
        this method is intentionally kept separate from model-response
        projection so the two LangChain request contracts cannot be mixed.
        """
        call = cls._bind_compiled_call(request, getattr(request, "tool_call", None))
        return request.override(tool_call=call)

    def wrap_tool_call(self, request, handler):
        return handler(self._inject_compiled_plan(request))

    async def awrap_tool_call(self, request, handler):
        return await handler(self._inject_compiled_plan(request))


__all__ = ["PlanToolProjectionMiddleware"]
