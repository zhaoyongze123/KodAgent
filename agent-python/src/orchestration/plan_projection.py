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
- _enforce_handshake / _selection_tool_response 交握回合的协议强制与受控重试
- _enforce_model_response                     澄清回合的越权工具拦截
- _execution_response / _execution_clarification  已解析回合的执行强制
- _bind_compiled_call / _inject_compiled_plan  工具边界参数规范化（兼容层）
- _control_finalization / _finalize_response  控制事实的无工具最终收尾
"""

from __future__ import annotations

import hashlib
import json
import logging
from copy import copy
from dataclasses import replace
import os
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from .capabilities import action_execution_class, resolve_action
from .attachment_request import artifact_requested, requested_formats
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
    ordered_context_candidates,
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
    parse_project_investigation_receipt,
)
from .coordination_dispatch import (
    load_tasks as _load_coordination_tasks,
    public_summary as _coordination_public_summary,
    record_task_result as _record_coordination_task_result,
    start_tasks as _start_coordination_tasks,
    task_from_description as _coordination_task_from_description,
)
from .route_state import (
    current_turn_messages as _current_turn_messages,
    message_content as _content,
    message_name as _tool_name,
    message_type as _message_type,
    route_action_id as _route_action_id,
    route_capability as _route_capability,
    route_execution_class as _route_execution_class,
    route_result as _route_result,
    route_results as _route_results,
    route_state as _route_state,
)
from ..tools.common.conversation import route_conversation_model_schema
from ..tools.common.events import current_agent_context, narration_validation_issues
from ..services.narration_stream import stream_model_output_scope
from ..presentation.message_contract import (
    PRESENTATION_KEY,
    presentation_final_entry_id,
    presentation_kind,
    with_message_presentation,
)


logger = logging.getLogger(__name__)


class PlanToolProjectionMiddleware(AgentMiddleware):
    """在计划编译完成后投影工具，并强制模型遵守计划边界。

    ``route_conversation`` 返回前保留 DeepAgents 的常规控制面工具；一旦返回
    ``RESOLVED`` 计划，本中间件只向模型暴露该计划绑定的执行器。这样既保留
    原有 ReAct 循环和 checkpoint 语义，又消除跨领域误选工具与绕过编译器的路径。
    """

    name = "PlanToolProjectionMiddleware"

    _AUTO_SELECTION_MARKER = "auto_action_selection_route"
    _AUTO_EXECUTION_MARKER = "auto_compiled_executor_call"
    # 自动执行防重标记必须绑定到已编译的计划。同一轮里可以有
    # “查日程 + 查项目”两个独立计划，不能因为前一个已被代码自动执行，
    # 就把后一个当作重放。
    _AUTO_EXECUTION_PLAN_ID = "auto_compiled_plan_id"
    # 模型偶尔会把一个跨领域请求拆成多个 route_conversation 调用。只有这些
    # 调用都已编译成功后，代码才会合成为一次 steps[] 路由，进而创建协调批次。
    # 此标记仅用于审计和故障排查，不能作为跨领域计划的事实来源。
    _AUTO_COORDINATION_MARKER = "auto_coordination_route"
    # 代码拥有的最终答复可携带一份受控 UI 投影。它不是自然语言中的下载链接，
    # 而是由聊天前端按稳定结构渲染成卡片；模型没有权限构造这个字段。
    _UI_PRESENTATION_KEY = PRESENTATION_KEY
    # 项目列表只是“选择哪个项目”的必要查询。若返回唯一项目且用户原始问题
    # 明确是在问进度/风险等分析，代码会把该已验证的定位结果收敛为一次
    # project.investigate 路由，避免主 Agent 再把同一问题拆成多次串行查询。
    _AUTO_PROJECT_INVESTIGATION_MARKER = "auto_project_investigation_route"
    # 当用户问的是“我手头项目怎么样”但未指定项目时，项目列表是唯一合法的
    # 定位动作。此标记防止 ACTION_SELECTION 尚未落盘时重复签发列表查询。
    _AUTO_PROJECT_LIST_MARKER = "auto_project_list_route"
    # 首轮项目进度问题若同时满足“明确项目语义 + 单领域只读分析”，无需先让
    # 模型在全量能力目录中识别领域。该标记仅避免工具节点尚未写回前重复签发，
    # 不承载项目权限、项目编号或任何业务事实。
    _AUTO_INITIAL_PROJECT_LIST_MARKER = "auto_initial_project_list_route"
    _ARTIFACT_TOOL = "create_document_artifact"
    # 用户明确说“这个项目”且当前 Thread 只有一个可验证项目候选时，项目编号
    # 仅用于重进 Java Provider 的只读调查，不应再让模型先重复一遍“项目 ->
    # project.list -> 项目”的空转路由。
    _AUTO_CONTEXT_PROJECT_INVESTIGATION_MARKER = "auto_context_project_investigation_route"
    _PROTOCOL_MARKERS = (
        "<|dsml|>", "<tool_calls", "</tool_calls>", "<invoke name=",
        "<function_calls>", "</function_calls>",
    )

    @staticmethod
    def _message_id(message: Any) -> str:
        """Read a persisted LangChain message id without trusting message content."""

        value = message.get("id") if isinstance(message, dict) else getattr(message, "id", None)
        return str(value or "").strip()

    @classmethod
    def _current_turn_identity(cls, request) -> str:
        """Return a trusted identity for the user turn that owns a code call.

        ``runId`` is issued by the Agent gateway for every invocation and is
        therefore the normal isolation boundary.  ``messageId``/the persisted
        human-message id provide a compatible fallback for checkpoint replay.
        This deliberately never derives an id from model-produced text or
        tool-call arguments.
        """

        context = current_agent_context()
        run_id = str(context.get("runId") or "").strip()
        if run_id and run_id != "local-run":
            return f"run:{run_id}"
        message_id = str(context.get("messageId") or "").strip()
        if message_id:
            return f"message:{message_id}"
        messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        for message in reversed(messages):
            if _message_type(message) not in {"human", "user"}:
                continue
            persisted_id = cls._message_id(message)
            if persisted_id:
                return f"message:{persisted_id}"
            break
        # This branch exists solely for direct unit tests and pre-context
        # local scripts.  Production calls receive a run id at the gateway.
        return "local"

    @staticmethod
    def _call_label(value: str) -> str:
        """Keep the readable part of a provider tool-call id protocol-safe."""

        normalized = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "")).strip("-")
        return normalized[:48] or "call"

    @classmethod
    def _code_owned_tool_call_id(
        cls,
        request,
        *,
        prefix: str,
        subject: str,
        identity: str,
    ) -> str:
        """Issue a deterministic, Run-isolated id for a code-owned tool call.

        Tool call IDs are part of the persistent LLM protocol, not UI labels.
        A static id such as ``compiled-delegate-projects_agent`` collides when
        a later user turn delegates another project plan in the same thread;
        the next provider request then contains two ToolMessages for one call.
        Include both the trusted execution identity (plan/batch/route) and the
        current trusted Run/message scope.  The hash preserves provider-safe
        length without exposing internal identifiers to the user interface.
        """

        material = "|".join((
            "v1",
            str(prefix or ""),
            str(subject or ""),
            str(identity or ""),
            cls._current_turn_identity(request),
        ))
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:20]
        return f"{cls._call_label(prefix)}-{cls._call_label(subject)}-{digest}"

    @classmethod
    def _compiled_plan_identity(cls, route: dict[str, Any], executor: str) -> str:
        """Use the compiler plan id; retain a legacy deterministic fallback.

        All current compiler results carry ``planId``.  The fallback only
        keeps older checkpoints and focused tests compatible; it is built from
        compiler-owned route facts, never a model-authored executor call.
        """

        plan_id = str(route.get("planId") or route.get("plan_id") or "").strip()
        if plan_id:
            return f"plan:{plan_id}"
        canonical = route.get("executionPlan") if isinstance(route.get("executionPlan"), dict) else {}
        encoded = json.dumps(
            {
                "capability": _route_capability(route),
                "action": _route_action_id(route),
                "executor": executor,
                "plan": canonical,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return "legacy:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _coordination_batch_id(route: dict[str, Any] | None) -> str:
        """从跨领域路由事实读取已持久化批次 ID，模型参数不参与。"""

        if not isinstance(route, dict):
            return ""
        batch = route.get("coordinationBatch") or route.get("coordination_batch") or {}
        return str(batch.get("batchId") or batch.get("batch_id") or "").strip() if isinstance(batch, dict) else ""

    @classmethod
    def _is_coordination_route(cls, route: dict[str, Any] | None) -> bool:
        """只认可路由工具明确签发的协调状态，不能从步骤文本推断。"""

        return (
            isinstance(route, dict)
            and str(route.get("planStatus") or route.get("plan_status") or "").upper() == "COORDINATION_READY"
            and bool(cls._coordination_batch_id(route))
        )

    @classmethod
    def _routes_by_capability(cls, messages: list[Any]) -> dict[str, dict[str, Any]]:
        """读取本回合每个领域最后一次工具签发的路由事实。

        同一领域可能经历“动作选择 -> 已解析”两次路由，因此只保留该领域最后
        一次结果。这里不读取模型 tool call 参数，避免把未经过 route_conversation
        编译的内容误当作可执行步骤。
        """

        routes: dict[str, dict[str, Any]] = {}
        for route in _route_results(messages):
            capability = _route_capability(route)
            if capability and capability not in {"general", "general_agent", "coordination"}:
                routes[capability] = route
        return routes

    @classmethod
    def _active_route(cls, messages: list[Any]) -> dict[str, Any] | None:
        """返回当前需要驱动的路由，跨领域时优先未完成领域。

        这条规则避免“日程已解析、项目仍待选择动作”时先派发日程，造成用户
        明明要求并行却得到半完成结果。待全部领域均 RESOLVED 后，调用方会生成
        受控协调路由，单领域执行器不会再单独可见。
        """

        latest = _route_result(messages)
        if cls._is_coordination_route(latest):
            return latest
        routes = cls._routes_by_capability(messages)
        if len(routes) < 2:
            return latest
        unfinished = [route for route in routes.values() if _route_state(route) != "RESOLVED"]
        return unfinished[-1] if unfinished else latest

    @classmethod
    def _coordination_steps_from_routes(cls, messages: list[Any]) -> list[dict[str, Any]]:
        """从多个已解析单领域路由重建受控 ``steps[]`` 输入。

        返回值只来自每个路由结果的 ``executionPlan``，该计划已经通过现有
        PlanCompiler 与 Action Catalog 校验。中央协调编译器仍会逐项重新编译，
        因此这里的投影不是绕过编译的捷径，也不会采纳模型自由拼写的字段。
        """

        routes = cls._routes_by_capability(messages)
        if not 2 <= len(routes) <= 4 or any(_route_state(route) != "RESOLVED" for route in routes.values()):
            return []
        steps: list[dict[str, Any]] = []
        for capability, route in routes.items():
            action_id = _route_action_id(route)
            execution_class = _route_execution_class(route)
            execution_plan = route.get("executionPlan") or route.get("execution_plan")
            if not action_id or not execution_class or not isinstance(execution_plan, dict):
                return []
            candidate_plan = dict(execution_plan)
            candidate_plan["action_id"] = action_id
            steps.append({
                "step_id": capability,
                "capability_id": capability,
                "action_id": action_id,
                "execution_class": execution_class,
                "candidate_plan": candidate_plan,
            })
        return steps

    @classmethod
    def _code_owned_coordination_route_call(cls, request, messages: list[Any]):
        """将已完成的多领域路由收敛为一次由代码签发的协调路由调用。

        它不直接创建 ``CoordinationBatch``，而是仍经过稳定的 route_conversation
        工具和其持久化/审计边界。模型不能构造这个调用，也不能把一个领域的
        WorkOrder 或自由文本塞给另一个领域。
        """

        steps = cls._coordination_steps_from_routes(messages)
        if not steps:
            return None
        call = {
            "name": "route_conversation",
            "args": {
                "message": cls._current_user_message(request),
                "capability_id": "general_agent",
                "steps": steps,
            },
            "id": cls._code_owned_tool_call_id(
                request,
                prefix="compiled-coordination",
                subject="route",
                identity="steps:" + ",".join(
                    str((step.get("candidate_plan") or {}).get("planId") or step["step_id"])
                    for step in steps
                ),
            ),
            "type": "tool_call",
        }
        return AIMessage(
            name="oa-main-agent",
            content="",
            tool_calls=[call],
            response_metadata={cls._AUTO_COORDINATION_MARKER: True},
            additional_kwargs={cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
        )

    @classmethod
    def _has_auto_project_investigation(cls, request) -> bool:
        """判断本用户回合是否已经签发过唯一项目的自主调查。

        参数：
            request：当前模型调用请求，其中保存完整 LangGraph 消息状态。

        返回：若本回合已有代码签发的项目调查路由则返回 ``True``。该标记仅防止
        工具节点尚未落盘时重复签发，不是业务状态、更不授予项目访问权限。
        """

        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        return any(
            _message_type(message) == "ai"
            and bool((getattr(message, "response_metadata", {}) or {}).get(
                cls._AUTO_PROJECT_INVESTIGATION_MARKER
            ))
            for message in messages
        )

    @classmethod
    def _has_auto_project_list(cls, request) -> bool:
        """判断本用户回合是否已经签发过项目定位列表。"""
        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        return any(
            _message_type(message) == "ai"
            and bool((getattr(message, "response_metadata", {}) or {}).get(
                cls._AUTO_PROJECT_LIST_MARKER
            ))
            for message in messages
        )

    @staticmethod
    def _project_analysis_requested(user_message: str) -> bool:
        """判断用户是否在请求项目调查，而非单纯索要项目列表。

        参数：
            user_message：当前回合的原始用户文本。

        返回：只匹配项目进度、风险、任务、成员、资料或报告等调查语义。这个小范围
        规则只决定“列表之后是否进入已经注册的 project.investigate”，不会创建
        新动作、不会读取项目数据，也不会替代 Java 的项目权限校验。
        """

        text = str(user_message or "").strip().lower()
        if not text:
            return False
        analysis_signals = (
            # 这里是“是否值得直接查项目列表”的性能信号，不是业务动作判定。
            # 除了显式术语，还覆盖规划院人员常见的自然问法，例如“心里没底”、
            # “重点盯什么”“哪几件事要关注”。真正的项目编号、权限和统计事实
            # 仍必须在后续 Java Provider 调用中重新核验。
            "进度", "推进", "风险", "卡点", "卡在", "拖进度", "拖延",
            "任务", "负责人", "成员", "动态", "资料", "制度", "报告",
            "分析", "完成率", "逾期", "停滞", "怎么样", "情况", "盯住",
            "盯紧", "重点", "关注", "心里没底", "没底", "哪几件事",
            "汇报", "怎么汇报", "怎么组织", "汇总", "领导",
            # 项目周报是规划院人员的常见自然表达。它不直接创建导出，而是先
            # 查询当前用户可见的项目；多项目时仍由候选卡片选择，唯一项目才会
            # 继续走中央编译后的调查/报告执行链路。
            "周报", "月报", "阶段总结", "阶段汇报", "导出",
        )
        return any(signal in text for signal in analysis_signals)

    @classmethod
    def _has_auto_context_project_investigation(cls, request) -> bool:
        """判断本轮是否已签发基于候选的项目调查，防止流式重放重复派发。"""

        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        return any(
            _message_type(message) == "ai"
            and bool((getattr(message, "response_metadata", {}) or {}).get(
                cls._AUTO_CONTEXT_PROJECT_INVESTIGATION_MARKER
            ))
            for message in messages
        )

    @classmethod
    def _code_owned_context_project_investigation_route(cls, request, route: dict[str, Any] | None):
        """把唯一的“这个项目”候选收敛为重新编译后的项目调查。

        候选在这里仍只是 Thread 上下文线索：代码只取出它保存的项目定位值，并在
        ``route_conversation`` 边界附上完整性证明。中央编译器和 Java Project
        Provider 会对新 WorkOrder 和当前成员权限重新校验，候选既不是项目事实，
        也不是跳过路由/编译的执行权限。
        """

        state = getattr(request, "state", {}) or {}
        if route is not None:
            audit_context_decision(state, event="project_candidate_route_skipped", reason="route_already_present")
            return None
        if context_shadow_mode():
            audit_context_decision(state, event="project_candidate_route_skipped", reason="shadow_mode")
            return None
        if cls._has_auto_context_project_investigation(request):
            audit_context_decision(state, event="project_candidate_route_skipped", reason="already_issued_in_turn")
            return None
        user_message = cls._current_user_message(request)
        if not cls._project_analysis_requested(user_message):
            return None
        # “这个项目”是最明确的续接形式，但真实用户也会在刚查看项目后直接说
        # “整理成周报”“进展心里没底”。仅当 Thread 中候选唯一且仍在近窗口时，
        # 这些项目分析语义才可复用定位线索；没有项目候选、存在其他候选，或只问
        # 泛化的“报告/情况”时仍进入普通路由，不能把旧项目偷偷当成事实来源。
        explicit_reference = bool(re.search(
            r"(?:这个|这项|该|上述|前面(?:的)?|刚才(?:的)?|上一个|当前|本)(?:项目|工程|课题)",
            user_message,
        ))
        implicit_project_signals = (
            "项目", "工程", "课题", "周报", "月报", "阶段汇报", "阶段总结",
            "项目进度", "推进", "任务", "风险", "卡点", "资料", "制度",
        )
        if not explicit_reference and not any(signal in user_message for signal in implicit_project_signals):
            audit_context_decision(state, event="project_candidate_route_skipped", reason="no_project_follow_up_signal")
            return None
        candidates = [
            candidate
            for candidate in ordered_context_candidates(
                state.get("context_candidates"),
                user_message=user_message,
            )
            if (
                candidate.kind in {"authorized_query", "authorized_resource"}
                and candidate.capability_id == "project"
                and "project.investigate" in candidate.action_ids
                and str(candidate.trusted_plan.get("project_id") or "").strip()
                and context_candidate_is_recent_for_direct_lookup(state, candidate)
            )
        ]
        if len(candidates) != 1:
            audit_context_decision(
                state,
                event="project_candidate_route_skipped",
                reason="eligible_candidate_count",
                candidateCount=len(candidates),
            )
            return None
        candidate = candidates[0]
        if not context_candidate_reference_is_unambiguous(
            state, candidate, user_message=user_message,
        ):
            audit_context_decision(
                state,
                event="project_candidate_route_skipped",
                reason="candidate_reference_ambiguous",
                candidateCount=len(candidates),
            )
            return None
        project_id = str(candidate.trusted_plan.get("project_id") or "").strip()
        audit_context_decision(
            state,
            event="project_candidate_route_selected",
            candidateId=candidate.candidate_id,
            reference="explicit" if explicit_reference else "implicit",
        )
        return AIMessage(
            name="oa-main-agent",
            content="",
            tool_calls=[{
                "name": "route_conversation",
                "args": {
                    "message": user_message,
                    "capability_id": "project",
                    "action_id": "project.investigate",
                    "execution_class": "fallback_react",
                    "strategy": "delegate",
                    "confidence": 1.0,
                    "task_complexity": "complex",
                    "context_candidate_id": candidate.candidate_id,
                    "context_intent": "REFER_TO_QUERY_CANDIDATE",
                    "context_confidence": 1.0,
                    "candidate_plan": {
                        "project_id": project_id,
                        "_context_candidate_proof": context_candidate_proof(candidate.candidate_id),
                        "_context_candidate_kind": candidate.kind,
                    },
                },
                "id": cls._code_owned_tool_call_id(
                    request,
                    prefix="project-investigation",
                    subject="context",
                    identity=f"candidate:{candidate.candidate_id}",
                ),
                "type": "tool_call",
            }],
            response_metadata={cls._AUTO_CONTEXT_PROJECT_INVESTIGATION_MARKER: True},
            additional_kwargs={cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
        )

    @staticmethod
    def _is_unambiguous_single_project_analysis(user_message: str) -> bool:
        """识别可由代码直接进入项目定位查询的首轮只读问题。

        参数：
            user_message：当前回合用户原始文本。

        返回：用户明确提到“项目”，或自然表达出“整理周报/月报并导出文件”且
        没有携带其他领域信号时返回 ``True``。后者只会触发权限收敛的
        ``project.list``，不会猜测项目编号、直接导出文件或绕过 Action Catalog、
        PlanCompiler 和 Java 权限校验。

        设计原因：首轮模型仅为识别一个已明确的领域而等待几十秒没有业务价值；
        但跨领域和写操作仍交给模型路由，避免关键词规则侵占复杂 ReAct 规划。
        """

        text = str(user_message or "").strip().lower()
        if not PlanToolProjectionMiddleware._project_analysis_requested(text):
            return False
        other_domain_signals = (
            "会议", "会议室", "日程", "审批", "党务", "请假", "出差",
        )
        write_signals = ("新建", "创建", "修改", "删除", "归档", "分配", "调整任务")
        if any(signal in text for signal in (*other_domain_signals, *write_signals)):
            return False
        if "项目" in text:
            return True
        # “最近的情况整理成周报，文件也带上”这类话没有显式说项目，但在
        # 当前产品里安全的下一步仍只是读取本人可见项目。不能据此把通用
        # reporting 报表误当作项目报告，因此要求同时有报告与文件/导出信号。
        report_signals = ("周报", "月报", "阶段总结", "阶段汇报")
        export_signals = ("文件", "附件", "导出", "下载", "word", "excel", "docx", "xlsx")
        return any(signal in text for signal in report_signals) and any(signal in text for signal in export_signals)

    @classmethod
    def _has_auto_initial_project_list(cls, request) -> bool:
        """判断当前回合是否已签发过首轮项目定位查询。"""

        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        return any(
            _message_type(message) == "ai"
            and bool((getattr(message, "response_metadata", {}) or {}).get(
                cls._AUTO_INITIAL_PROJECT_LIST_MARKER
            ))
            for message in messages
        )

    @classmethod
    def _code_owned_initial_project_list_route(cls, request, route: dict[str, Any] | None):
        """为明确的单项目分析首轮签发受控的 ``project.list`` 路由。

        主图仍把此调用交给 ``route_conversation``，因此 Java 动作目录、中央编译、
        WorkOrder 和 KodCloud 当前用户权限复核全部保留。代码只省去了“模型识别
        已经写在用户原文里的项目领域”这一空转回合；项目子 Agent 后续是否继续
        调用任务、动态、资料等工具，仍由其 ReAct 循环自主决定。
        """

        if route is not None or cls._has_auto_initial_project_list(request):
            return None
        # ``request.tools`` 是本次模型调用的可见 palette，而不是主图是否注册
        # route_conversation 的事实来源。中间件链在首轮可能尚未把固定路由工具
        # 投影到该字段；若在这里依赖它，明确的项目分析会退回模型逐个拆分查询，
        # 造成多次无意义的主图 ReAct 循环。route_conversation 是 oa_agent 图的
        # 固定控制面工具，代码签发的调用仍会经过同一编译、审计与权限边界。
        user_message = cls._current_user_message(request)
        if not cls._is_unambiguous_single_project_analysis(user_message):
            return None
        return AIMessage(
            name="oa-main-agent",
            content="",
            tool_calls=[{
                "name": "route_conversation",
                "args": {
                    "message": user_message,
                    "capability_id": "project",
                    "action_id": "project.list",
                    "execution_class": "metadata_query",
                    "strategy": "delegate",
                    "confidence": 1.0,
                    "task_complexity": "simple",
                    "candidate_plan": {"page_no": 1, "page_size": 20},
                },
                "id": cls._code_owned_tool_call_id(
                    request,
                    prefix="project-list",
                    subject="initial",
                    identity="initial-project-analysis",
                ),
                "type": "tool_call",
            }],
            response_metadata={cls._AUTO_INITIAL_PROJECT_LIST_MARKER: True},
            additional_kwargs={cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
        )

    @staticmethod
    def _unique_project_id_from_list_receipt(request, route: dict[str, Any]) -> str:
        """从当前已核验的项目列表回执取唯一项目编号。

        参数：
            request：当前模型调用请求。
            route：当前 ``project.list`` 的已编译路由事实。

        返回：仅当本回合与当前计划编号匹配的项目列表回执恰好包含一个项目时返回
        该项目编号；多项目、空结果、失败回执或不匹配的旧回执一律返回空字符串。
        编号来自子 Agent 的确定性执行回执，后续仍会由 Java Project Provider
        按当前用户重新校验。
        """

        expected_plan_id = str(route.get("planId") or route.get("plan_id") or "").strip()
        if not expected_plan_id:
            return ""
        for message in reversed(_current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )):
            if _message_type(message) != "tool":
                continue
            receipt = parse_execution_receipt(_content(message))
            if (
                receipt is None
                or receipt.plan_id != expected_plan_id
                or receipt.executor_tool != "list_accessible_projects"
                or receipt.status != "SUCCEEDED"
                or not isinstance(receipt.result, dict)
            ):
                continue
            rows = receipt.result.get("items")
            total = receipt.result.get("total")
            if not isinstance(rows, list) or len(rows) != 1:
                return ""
            if total is not None:
                try:
                    if int(total) != 1:
                        return ""
                except (TypeError, ValueError):
                    return ""
            row = rows[0] if isinstance(rows[0], dict) else {}
            project_id = row.get("projectID") or row.get("projectId") or row.get("project_id")
            if project_id is None or isinstance(project_id, bool):
                return ""
            return str(project_id).strip()
        return ""

    @classmethod
    def _code_owned_project_list_route(cls, request, route: dict[str, Any]):
        """把“未指定项目的调查请求”收敛为唯一的项目定位查询。

        参数：
            request：主图当前模型请求，包含本轮用户原文和路由状态。
            route：第一阶段路由工具返回的 ``project`` ACTION_SELECTION 事实。

        返回：只在当前领域是项目、尚未选中具体 Action，且用户确实在问项目
        分析问题时签发 ``project.list``；其他情况返回 ``None`` 让模型继续正常
        选择动作。

        这是性能收口而非语义猜测：没有项目 ID 时，查询“当前用户可参与项目”是
        唯一不扩大权限的下一步。它仍通过 Action Catalog、PlanCompiler、WorkOrder
        和 Java Project Provider，列表结果也只作为随后项目定位的线索。
        """
        if (
            not isinstance(route, dict)
            or _route_capability(route) != "project"
            or _route_action_id(route)
            or _route_state(route) != "ACTION_SELECTION"
            or cls._has_auto_project_list(request)
        ):
            return None
        user_message = cls._current_user_message(request)
        if not cls._project_analysis_requested(user_message):
            return None
        return AIMessage(
            name="oa-main-agent",
            content="",
            tool_calls=[{
                "name": "route_conversation",
                "args": {
                    "message": user_message,
                    "capability_id": "project",
                    "action_id": "project.list",
                    "execution_class": "metadata_query",
                    "strategy": "delegate",
                    "confidence": 1.0,
                    "task_complexity": "simple",
                    "candidate_plan": {"page_no": 1, "page_size": 20},
                },
                "id": cls._code_owned_tool_call_id(
                    request,
                    prefix="project-list",
                    subject="selection",
                    identity=(
                        str(route.get("planId") or route.get("plan_id") or "")
                        or "action-selection"
                    ),
                ),
                "type": "tool_call",
            }],
            response_metadata={cls._AUTO_PROJECT_LIST_MARKER: True},
            additional_kwargs={cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
        )

    @classmethod
    def _code_owned_project_investigation_route(cls, request, route: dict[str, Any]):
        """把“唯一项目列表 + 分析问题”转换为一次受控的自主调查路由。

        该方法只产生 ``route_conversation`` 工具调用，仍会经过现有 Action Catalog、
        ProjectPlanCompiler、WorkOrder 与 Java 权限校验。它没有跳过中央编译，也不把
        列表结果当作项目事实；项目子 Agent 在取得 WorkOrder 后才按真实工具结果
        自主决定是否继续查询任务、动态、资料或制度依据。
        """

        if (
            not isinstance(route, dict)
            or _route_capability(route) != "project"
            or _route_action_id(route) != "project.list"
            or str(route.get("planStatus") or "").upper() != "RESOLVED"
            or cls._has_auto_project_investigation(request)
        ):
            return None
        user_message = cls._current_user_message(request)
        if not cls._project_analysis_requested(user_message):
            return None
        project_id = cls._unique_project_id_from_list_receipt(request, route)
        if not project_id:
            return None
        return AIMessage(
            name="oa-main-agent",
            content="",
            tool_calls=[{
                "name": "route_conversation",
                "args": {
                    "message": user_message,
                    "capability_id": "project",
                    "action_id": "project.investigate",
                    "execution_class": "fallback_react",
                    "strategy": "delegate",
                    "confidence": 1.0,
                    "task_complexity": "complex",
                    # project_id 是刚刚由 Java 列表结果返回的定位线索。计划编译后
                    # Java Project Provider 会重新验证成员关系与任务隐私。
                    "candidate_plan": {"project_id": project_id},
                },
                "id": cls._code_owned_tool_call_id(
                    request,
                    prefix="project-investigation",
                    subject="list",
                    identity=(
                        str(route.get("planId") or route.get("plan_id") or "")
                        or f"project:{project_id}"
                    ),
                ),
                "type": "tool_call",
            }],
            response_metadata={cls._AUTO_PROJECT_INVESTIGATION_MARKER: True},
            additional_kwargs={cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
        )

    @classmethod
    def _created_artifact_formats(cls, request) -> set[str]:
        """返回本轮 Java 已签发附件的格式，不信任模型自报的文件名或地址。"""

        formats: set[str] = set()

        for message in reversed(_current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )):
            if _message_type(message) != "tool" or _tool_name(message) != cls._ARTIFACT_TOOL:
                continue
            try:
                payload = json.loads(_content(message) or "{}")
            except (TypeError, ValueError):
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(payload, dict) and payload.get("ok") is True and isinstance(data, dict):
                artifact_id = str(data.get("artifactId") or "").strip()
                artifact_format = str(data.get("format") or "").strip().upper()
                if artifact_id and artifact_format in {"DOCX", "XLSX"}:
                    formats.add(artifact_format)
        return formats

    @classmethod
    def _required_artifact_formats(cls, request) -> set[str]:
        """读取当前用户明确要求的附件格式；没有要求时不制造附件义务。"""

        return set(requested_formats(cls._current_user_message(request)))

    @classmethod
    def _artifact_completed(cls, request) -> bool:
        """判断本轮是否已交付用户要求的全部附件格式。"""

        created = cls._created_artifact_formats(request)
        required = cls._required_artifact_formats(request)
        return required.issubset(created) if required else bool(created)

    @classmethod
    def _artifact_delivery_pending(cls, request) -> bool:
        """附件是用户明确要求的交付物时，正文不能先于 Java 回执提交。"""

        return bool(cls._required_artifact_formats(request) - cls._created_artifact_formats(request))

    @classmethod
    def _artifact_delivery_request(cls, request, artifact_tools):
        """创建仅包含附件工具的受控交付回合，正文仍完全由模型基于事实撰写。"""

        pending = sorted(cls._required_artifact_formats(request) - cls._created_artifact_formats(request))
        base = getattr(request, "system_message", None)
        base_text = getattr(base, "content", None) or getattr(base, "text", None) or ""
        formats = "、".join(pending) or "DOCX"
        system_message = SystemMessage(content=(
            f"{base_text}\n\n"
            "本轮用户明确要求可下载附件，附件尚未完成交付。现在必须调用 "
            "create_document_artifact 制作附件，不要输出普通答复。"
            f"必须完成的附件格式：{formats}。"
            "文档标题、正文和结构由你根据已核实的事实及用户要求自行撰写；"
            "不得用“未生成”或“请重试”替代附件交付。"
        ))
        return request.override(
            tools=artifact_tools,
            tool_choice={"type": "function", "function": {"name": cls._ARTIFACT_TOOL}},
            system_message=system_message,
        )

    @classmethod
    def _has_only_artifact_tool_calls(cls, response, *, required_formats: set[str] | None = None) -> bool:
        """附件交付回合只能提交仍待交付格式的通用附件工具。"""

        messages = cls._response_messages(response)
        target = next(
            (message for message in reversed(messages) if _message_type(message) == "ai"),
            None,
        )
        if target is None:
            return False
        calls = getattr(target, "tool_calls", None) or (
            target.get("tool_calls") if isinstance(target, dict) else []
        )
        if not calls or not all(
            isinstance(call, dict) and str(call.get("name") or "") == cls._ARTIFACT_TOOL
            for call in calls
        ):
            return False
        formats = {
            str((call.get("args") or {}).get("format") or "").strip().upper()
            for call in calls
            if isinstance(call, dict) and isinstance(call.get("args"), dict)
        }
        if len(formats) != len(calls) or not formats.issubset({"DOCX", "XLSX"}):
            return False
        return not required_formats or formats.issubset(required_formats)

    @classmethod
    def _artifact_delivery_failure(cls, code: str):
        """返回控制事实，交由既有无工具收尾机制说明失败，不伪造用户答复。"""

        return AIMessage(
            name="oa-main-agent",
            content="",
            response_metadata={"routeFailure": code},
            additional_kwargs={cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
        )

    @classmethod
    def _enforce_artifact_delivery(cls, request, response, handler):
        """模型漏调附件工具时，重试一次受控交付回合而非提交缺附件的正文。"""

        pending_formats = cls._required_artifact_formats(request) - cls._created_artifact_formats(request)
        if not pending_formats or cls._has_only_artifact_tool_calls(
            response, required_formats=pending_formats,
        ):
            return response
        artifact_tools = [item for item in request.tools if cls._tool_name(item) == cls._ARTIFACT_TOOL]
        if not artifact_tools:
            return cls._artifact_delivery_failure("ARTIFACT_TOOL_UNAVAILABLE")
        retry = handler(cls._artifact_delivery_request(request, artifact_tools))
        if cls._has_only_artifact_tool_calls(retry, required_formats=pending_formats):
            return retry
        return cls._artifact_delivery_failure("ARTIFACT_DELIVERY_REQUIRED")

    @classmethod
    async def _enforce_artifact_delivery_async(cls, request, response, handler):
        pending_formats = cls._required_artifact_formats(request) - cls._created_artifact_formats(request)
        if not pending_formats or cls._has_only_artifact_tool_calls(
            response, required_formats=pending_formats,
        ):
            return response
        artifact_tools = [item for item in request.tools if cls._tool_name(item) == cls._ARTIFACT_TOOL]
        if not artifact_tools:
            return cls._artifact_delivery_failure("ARTIFACT_TOOL_UNAVAILABLE")
        retry = await handler(cls._artifact_delivery_request(request, artifact_tools))
        if cls._has_only_artifact_tool_calls(retry, required_formats=pending_formats):
            return retry
        return cls._artifact_delivery_failure("ARTIFACT_DELIVERY_REQUIRED")

    @classmethod
    def _artifact_presentation(cls, request) -> dict[str, Any] | None:
        """从附件工具回执提取受控元数据，不信任模型构造的下载地址。"""

        attachments: list[dict[str, Any]] = []
        for message in _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        ):
            if _message_type(message) != "tool" or _tool_name(message) != cls._ARTIFACT_TOOL:
                continue
            try:
                payload = json.loads(_content(message) or "{}")
            except (TypeError, ValueError):
                continue
            data = payload.get("data") if isinstance(payload, dict) else None
            if not (isinstance(payload, dict) and payload.get("ok") is True and isinstance(data, dict)):
                continue
            artifact_id = str(data.get("artifactId") or "").strip()
            fmt = str(data.get("format") or "").strip().upper()
            if not re.fullmatch(r"[0-9a-f-]{16,80}", artifact_id, re.IGNORECASE) or fmt not in {"DOCX", "XLSX"}:
                continue
            item: dict[str, Any] = {
                "artifactId": artifact_id,
                "title": str(data.get("title") or "附件").strip()[:200],
                "format": fmt,
                "filename": str(data.get("filename") or f"附件.{fmt.lower()}").strip()[:240],
                "mimeType": str(data.get("mimeType") or "").strip(),
            }
            if isinstance(data.get("size"), int):
                item["size"] = data["size"]
            attachments.append(item)
        if not attachments:
            return None
        return {
            "schemaVersion": 2,
            "kind": "final",
            "attachments": attachments,
        }

    @classmethod
    def _attach_artifact_presentation(cls, response, request):
        """把已创建附件挂到最终回答元数据；不创建第二个回答卡片。"""

        presentation = cls._artifact_presentation(request)
        if presentation is None:
            return response
        messages = cls._response_messages(response)
        target_index = next(
            (index for index in range(len(messages) - 1, -1, -1)
             if _message_type(messages[index]) == "ai"),
            None,
        )
        if target_index is None:
            return response
        target = messages[target_index]
        if not hasattr(target, "model_copy") or _content(target) is None:
            return response
        current_kwargs = dict(getattr(target, "additional_kwargs", None) or {})
        existing = dict(current_kwargs.get(cls._UI_PRESENTATION_KEY) or {})
        existing.update(presentation)
        current_kwargs[cls._UI_PRESENTATION_KEY] = existing
        updated = list(messages)
        updated[target_index] = target.model_copy(deep=True, update={"additional_kwargs": current_kwargs})
        return cls._replace_response_messages(response, updated)

    @classmethod
    def _with_response_presentation(cls, response, *, kind: str,
                                    final_entry_id: str | None = None):
        """标记本轮最后一条 AI 消息的展示角色，不改写正文。"""

        messages = cls._response_messages(response)
        target_index = next(
            (index for index in range(len(messages) - 1, -1, -1)
             if _message_type(messages[index]) == "ai"),
            None,
        )
        if target_index is None:
            return response
        target = messages[target_index]
        if not hasattr(target, "model_copy"):
            return response
        updated = list(messages)
        updated[target_index] = with_message_presentation(
            target,
            kind=kind,  # type: ignore[arg-type]
            final_entry_id=final_entry_id,
        )
        return cls._replace_response_messages(response, updated)

    @classmethod
    def _complete_presentation(cls, response, *, final_entry_id: str | None = None):
        """在所有协议校验完成后决定消息是否能成为聊天正文。"""

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
        content = _content(target)
        if calls or not isinstance(content, str) or not content.strip():
            return cls._with_response_presentation(response, kind="internal")
        # 控制收尾已经在自己的无工具调用里写入 stable finalEntryId；此处不能
        # 再用 None 覆盖它，否则最终 checkpoint 无法接管临时最终流。
        if presentation_kind(target) == "final" and presentation_final_entry_id(target):
            return response
        if not str(final_entry_id or "").strip():
            # 可见正文只能来自显式的收尾调用。没有流式关联的普通 AIMessage
            # 可能是路由或中间模型回合，必须 fail-closed。
            return cls._with_response_presentation(response, kind="internal")
        return cls._with_response_presentation(
            response,
            kind="final",
            final_entry_id=final_entry_id,
        )

    @staticmethod
    def _task_calls(messages: list[Any]) -> dict[str, str]:
        """建立父级 task 调用 ID 到代码描述的映射，兼容 checkpoint 对象/字典。"""

        calls: dict[str, str] = {}
        for message in messages:
            if _message_type(message) != "ai":
                continue
            raw_calls = getattr(message, "tool_calls", None)
            if isinstance(message, dict):
                raw_calls = raw_calls or message.get("tool_calls")
            for call in raw_calls or []:
                if not isinstance(call, dict) or str(call.get("name") or "") != "task":
                    continue
                args = call.get("args") if isinstance(call.get("args"), dict) else {}
                description = args.get("description")
                call_id = str(call.get("id") or "").strip()
                if call_id and isinstance(description, str):
                    calls[call_id] = description
        return calls

    @classmethod
    def _record_coordination_results(cls, request, route: dict[str, Any]) -> None:
        """将已经返回的子 Agent 回执落回批次，重复扫描不改变终态。"""

        batch_id = cls._coordination_batch_id(route)
        if not batch_id:
            return
        messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        descriptions = cls._task_calls(messages)
        for message in messages:
            if _message_type(message) != "tool":
                continue
            description = descriptions.get(cls._tool_call_id(message))
            if not description:
                continue
            parsed = _coordination_task_from_description(description)
            if parsed is None or parsed[0] != batch_id:
                continue
            _record_coordination_task_result(description, _content(message))

    @classmethod
    def _coordination_dispatch_response(cls, request, route: dict[str, Any]):
        """返回一条含多个代码签发 task 的消息，DeepAgents 会并行执行它们。"""

        batch_id = cls._coordination_batch_id(route)
        if not batch_id:
            return cls._execution_clarification()
        try:
            tasks = _load_coordination_tasks(batch_id)
            if not tasks:
                return None
            _start_coordination_tasks(batch_id, tasks)
        except Exception:
            # 批次状态无法读取/变更时不能退化为模型自由 task；保留既有确定性
            # 边界并让用户稍后重试。
            return cls._execution_clarification()
        return AIMessage(
            name="oa-main-agent",
            content="",
            tool_calls=[
                {
                    "name": "task",
                    "args": {
                        "subagent_type": task.subagent_type,
                        "description": task.description,
                    },
                    "id": cls._code_owned_tool_call_id(
                        request,
                        prefix="coordination",
                        subject=task.subagent_type,
                        identity=f"batch:{task.batch_id}:step:{task.step_id}",
                    ),
                    "type": "tool_call",
                }
                for task in tasks
            ],
            response_metadata={cls._AUTO_EXECUTION_MARKER: True, "coordinationBatchId": batch_id},
            additional_kwargs={cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
        )

    @classmethod
    def _coordination_summary_text(cls, route: dict[str, Any]) -> str | None:
        """从持久化步骤事实生成给用户的汇总底稿，不使用子 Agent 自由文本。"""

        batch_id = cls._coordination_batch_id(route)
        if not batch_id:
            return None
        try:
            summary = _coordination_public_summary(batch_id)
        except Exception:
            return None
        status = str(summary.get("status") or "")
        if status == "RUNNING":
            return None
        labels = {
            "SUCCEEDED": "已完成",
            "WAITING_APPROVAL": "已生成待确认草稿",
            "FAILED": "执行失败",
            "SKIPPED": "因依赖未执行",
            "CANCELLED": "已取消",
        }
        lines = ["跨领域任务处理情况："]
        for step in summary.get("steps") or []:
            if not isinstance(step, dict):
                continue
            domain = str(step.get("domain") or "业务")
            result = labels.get(str(step.get("status") or ""), "处理中")
            text = f"- {domain}：{result}"
            if step.get("errorMessage"):
                text += f"（{str(step['errorMessage'])[:160]}）"
            lines.append(text)
        if status == "WAITING_APPROVAL":
            lines.append("请通过系统展示的确认卡完成待确认操作；未确认前不会提交写入。")
        return "\n".join(lines)

    @classmethod
    def _coordination_summary_response(cls, response, route: dict[str, Any]):
        """协调事实已在 task 回执中，主 Agent 负责组织最终说明。

        旧实现会把所有跨领域问题改写成同一段确定性模板，既覆盖模型回答，也
        破坏流式提交边界。此处保留函数作为兼容调用点，但不再改写正文。
        """

        return response

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
        """读取当前回合的可信用户原文，只供路由和计划编译使用。

        ``CurrentUserMessageMiddleware`` 已在 Agent 边界把本轮 HumanMessage 写成
        ``current_user_message``。真实运行中的消息内容可能是 OpenAI 富文本块，若
        仅接受 ``str`` 会把首轮原文误读为空，进而让明确的项目请求退回模型自由
        拆分多个 Action。优先使用这个受信任标记；扫描消息流只是兼容旧 checkpoint
        和单元测试的回退路径，绝不把历史 AI 或 ToolMessage 当成当前用户指令。
        """

        state = getattr(request, "state", {}) or {}
        marker = state.get("current_user_message") if isinstance(state, dict) else None
        if (
            isinstance(marker, dict)
            and marker.get("source") == "current_human_message"
            and marker.get("trusted") is True
        ):
            trusted_text = marker.get("text")
            if isinstance(trusted_text, str) and trusted_text.strip():
                return trusted_text.strip()

        messages = list(state.get("messages") or []) if isinstance(state, dict) else []
        for message in reversed(messages):
            if _message_type(message) not in {"human", "user"}:
                continue
            content = _content(message)
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                # OpenAI 消息兼容格式：只拼接可见 text 块，跳过图片、工具参数等
                # 非文字内容。这里不解析或信任其中的任何业务字段。
                text = "".join(
                    str(item.get("text") or "")
                    for item in content
                    if isinstance(item, dict) and str(item.get("type") or "text") == "text"
                ).strip()
                if text:
                    return text
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
            "id": cls._code_owned_tool_call_id(
                request,
                prefix="action-selection",
                subject=action.action_id,
                identity=(
                    str(route.get("planId") or route.get("plan_id") or "")
                    or f"response:{target_index}"
                ),
            ),
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

    @classmethod
    def _control_finalization_request(cls, request, *, code: str, facts: str):
        """构造无工具的收尾调用；代码传递事实，模型负责面向用户说明。"""

        base = getattr(request, "system_message", None)
        base_text = getattr(base, "content", None) or getattr(base, "text", None) or ""
        prompt = (
            f"{base_text}\n\n"
            "当前回合已由系统控制层停止，不能调用任何工具或继续执行业务操作。"
            "仅根据以下结构化事实，用简短中文说明现状、未执行的边界和用户下一步可做什么；"
            "不要透露内部协议、工具名、路由状态或错误代码。\n"
            f"控制事实：{facts}\n控制编号：{code}"
        )
        return request.override(tools=[], system_message=SystemMessage(content=prompt))

    @classmethod
    def _control_finalization(cls, request, handler, *, code: str, facts: str,
                              final_entry_id: str | None = None):
        """将控制失败转换为无工具模型答复，而不是固定 AIMessage。"""

        with stream_model_output_scope(entry_id=final_entry_id) as entry_id:
            response = handler(cls._control_finalization_request(request, code=code, facts=facts))
        if cls._response_has_tool_calls(response):
            # 对不遵守无工具收尾约束的供应商再给一次同一事实的机会；仍失败时
            # 只保留内部状态，前端会显示结构化运行错误而不会收到伪造聊天文本。
            with stream_model_output_scope(entry_id=entry_id):
                response = handler(cls._control_finalization_request(request, code=code, facts=facts))
        if cls._response_has_tool_calls(response):
            return cls._with_response_presentation(response, kind="internal")
        return cls._complete_presentation(response, final_entry_id=entry_id)

    @classmethod
    async def _control_finalization_async(cls, request, handler, *, code: str, facts: str,
                                          final_entry_id: str | None = None):
        with stream_model_output_scope(entry_id=final_entry_id) as entry_id:
            response = await handler(cls._control_finalization_request(request, code=code, facts=facts))
        if cls._response_has_tool_calls(response):
            with stream_model_output_scope(entry_id=entry_id):
                response = await handler(cls._control_finalization_request(request, code=code, facts=facts))
        if cls._response_has_tool_calls(response):
            return cls._with_response_presentation(response, kind="internal")
        return cls._complete_presentation(response, final_entry_id=entry_id)

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
            return cls._control_finalization(
                request, handler, code="ACTION_SELECTION_BOUNDARY",
                facts="系统未能形成可执行的业务路由。",
            )
        retry_request = cls._route_only_retry(request)
        retry_response = handler(retry_request)
        projected = cls._selection_tool_response(retry_request, retry_response, route)
        if projected is not None:
            return projected
        if cls._has_valid_route_tool_call(retry_response, route):
            return retry_response
        return cls._control_finalization(
            request, handler, code="ACTION_SELECTION_BOUNDARY",
            facts="系统未能形成可执行的业务路由。",
        )

    @classmethod
    async def _enforce_handshake_async(cls, request, response, route, handler):
        projected = cls._selection_tool_response(request, response, route)
        if projected is not None:
            return projected
        if cls._has_valid_route_tool_call(response, route):
            return response
        if cls._has_auto_selection_attempt(request):
            return await cls._control_finalization_async(
                request, handler, code="ACTION_SELECTION_BOUNDARY",
                facts="系统未能形成可执行的业务路由。",
            )
        retry_request = cls._route_only_retry(request)
        retry_response = await handler(retry_request)
        projected = cls._selection_tool_response(retry_request, retry_response, route)
        if projected is not None:
            return projected
        if cls._has_valid_route_tool_call(retry_response, route):
            return retry_response
        return await cls._control_finalization_async(
            request, handler, code="ACTION_SELECTION_BOUNDARY",
            facts="系统未能形成可执行的业务路由。",
        )

    @classmethod
    def _enforce_model_response(cls, request, response, policy: TurnPolicy, handler=None):
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
        if cls._artifact_delivery_pending(request):
            allowed.add(cls._ARTIFACT_TOOL)
        for call in calls:
            name = str(call.get("name") or "") if isinstance(call, dict) else ""
            if name not in allowed:
                if handler is None:
                    return cls._with_response_presentation(response, kind="internal")
                return cls._control_finalization(
                    request, handler, code="MODEL_TOOL_OUT_OF_PALETTE",
                    facts="模型请求了当前回合不允许的操作，系统没有执行该操作。",
                )
        return response

    @classmethod
    async def _enforce_model_response_async(cls, request, response, policy: TurnPolicy, handler):
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
        if cls._artifact_delivery_pending(request):
            allowed.add(cls._ARTIFACT_TOOL)
        if all(
            str(call.get("name") or "") in allowed
            for call in calls if isinstance(call, dict)
        ) and all(isinstance(call, dict) for call in calls):
            return response
        return await cls._control_finalization_async(
            request, handler, code="MODEL_TOOL_OUT_OF_PALETTE",
            facts="模型请求了当前回合不允许的操作，系统没有执行该操作。",
        )

    @classmethod
    def _response_has_tool_calls(cls, response) -> bool:
        """判断模型本次回复是否仍请求调用工具。"""

        messages = cls._response_messages(response)
        target = next(
            (message for message in reversed(messages) if _message_type(message) == "ai"),
            None,
        )
        if target is None:
            return False
        calls = getattr(target, "tool_calls", None) or (
            target.get("tool_calls") if isinstance(target, dict) else []
        )
        return bool(calls)

    @classmethod
    def _enforce_completed_execution_synthesis(cls, request, response, handler,
                                               *, final_entry_id: str | None = None):
        """已取得执行回执后，主 Agent 只能输出正文，不能再生成工具调用。

        ``_override_for_policy`` 已经在收尾阶段清空工具 schema，但部分兼容模型仍会
        幻觉输出 ``ls``、``glob`` 等旧工具名。不能让这类调用进入 ToolNode 后再由
        执行守卫拒绝，否则前端会留下不存在业务价值的失败标签。这里直接用同一事实
        上下文进行一次无工具重试；正常情况下仍由模型动态组织最终答案。
        """

        if not cls._response_has_tool_calls(response):
            return response
        calls = cls._response_messages(response)
        target = next((message for message in reversed(calls) if _message_type(message) == "ai"), None)
        tool_calls = getattr(target, "tool_calls", None) or (target.get("tool_calls") if isinstance(target, dict) else [])
        if (
            artifact_requested(cls._current_user_message(request))
            and tool_calls
            and all(str(call.get("name") or "") == cls._ARTIFACT_TOOL for call in tool_calls if isinstance(call, dict))
        ):
            return response
        # 兼容模型即便看不到工具 schema 仍可能先幻觉一个调用。重试同样是唯一
        # 可以直播最终回答的主 Agent 无工具收尾范围；若仍有工具调用，chunk
        # tracker 会因 saw_tool_call 不发布任何临时最终文本。
        with stream_model_output_scope(entry_id=final_entry_id):
            retry = handler(request.override(tools=[]))
        if not cls._response_has_tool_calls(retry):
            return retry
        # 连续两次在无工具面板下仍构造调用，说明上游未遵守函数调用协议。此时不能
        # 为了拿到文字把幻觉工具执行出去；保留结构化失败状态，不能由代码伪造回复。
        return AIMessage(
            name="oa-main-agent",
            content="",
            response_metadata={
                "routeFailure": "SYNTHESIS_TOOL_CALL_BLOCKED",
            },
            additional_kwargs={
                cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"},
            },
        )

    @classmethod
    def _requires_initial_route(cls, request, route) -> bool:
        """判断无路由首轮是否必须完成一次 ``route_conversation`` 协议调用。

        闲聊和上下文性追问可以直接回答。只有分类器已识别为必须建立结构化业务
        契约的请求，才在模型漏调路由工具时重试；否则不得用协议兜底覆盖已经正确
        生成的自然语言答案。这样 ``needs_tools`` 仍可为模型保留工具面板，但不会
        被误解释为“必须路由”。
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

        return bool(
            classify_message(
                cls._current_user_message(request)
            ).requires_structured_route
        )

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
        return cls._control_finalization(
            request, handler, code="INITIAL_ROUTE_REQUIRED",
            facts="该请求需要先形成业务路由，但模型未能提交有效路由。",
        )

    @classmethod
    async def _enforce_initial_route_async(cls, request, response, handler):
        if cls._has_any_route_tool_call(response):
            return response
        retry_response = await handler(cls._route_only_retry(request))
        if cls._has_any_route_tool_call(retry_response):
            return retry_response
        return await cls._control_finalization_async(
            request, handler, code="INITIAL_ROUTE_REQUIRED",
            facts="该请求需要先形成业务路由，但模型未能提交有效路由。",
        )

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
            project_receipt = parse_project_investigation_receipt(content)
            if (
                project_receipt is not None
                and _route_capability(route) == "project"
                and _route_action_id(route) == "project.investigate"
                and project_receipt.plan_id == expected_plan_id
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
    def _has_auto_executor_attempt(cls, request, route: dict[str, Any]) -> bool:
        """判断当前计划是否已由代码尝试调度。

        旧实现只要本轮出现过任意自动执行标记就直接拒绝。在跨领域请求中，这会使
        日程分支阻塞项目分支。现在只认同一 ``planId`` 的重复调度；失去 planId 的历史
        checkpoint 不再激进拦截，由工具幂的幂等与 WorkOrder 校验继续保护。
        """
        expected_plan_id = str(route.get("planId") or route.get("plan_id") or "").strip()
        if not expected_plan_id:
            return False
        messages = _current_turn_messages(
            list((getattr(request, "state", {}) or {}).get("messages") or [])
        )
        return any(
            _message_type(message) == "ai"
            and (getattr(message, "response_metadata", {}) or {}).get(
                cls._AUTO_EXECUTION_MARKER
            ) is True
            and str((getattr(message, "response_metadata", {}) or {}).get(
                cls._AUTO_EXECUTION_PLAN_ID
            ) or "").strip() == expected_plan_id
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
                "id": cls._code_owned_tool_call_id(
                    request,
                    prefix="compiled-delegate",
                    subject=delegate_agent,
                    identity=cls._compiled_plan_identity(route, executor),
                ),
                "type": "tool_call",
            }
            return cls._bind_compiled_call(request, call)
        if not executor:
            return None
        call = {
            "name": executor,
            "args": {},
            "id": cls._code_owned_tool_call_id(
                request,
                prefix="compiled-executor",
                subject=executor,
                identity=cls._compiled_plan_identity(route, executor),
            ),
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
            content="",
            response_metadata={
                "routeFailure": "resolved_executor_boundary",
            },
            additional_kwargs={
                PlanToolProjectionMiddleware._UI_PRESENTATION_KEY: {
                    "schemaVersion": 2,
                    "kind": "internal",
                },
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
        if cls._has_auto_executor_attempt(request, route):
            return cls._execution_clarification()
        call = cls._compiled_executor_call(request, route, delegate_agent)
        if call is None:
            return cls._execution_clarification()
        return AIMessage(
            name="oa-main-agent",
            content="",
            tool_calls=[call],
            response_metadata={
                cls._AUTO_EXECUTION_MARKER: True,
                cls._AUTO_EXECUTION_PLAN_ID: str(route.get("planId") or route.get("plan_id") or ""),
            },
            additional_kwargs={cls._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
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
            # 协议错误是结构化运行状态，不是代码代写的聊天回答。前端可根据
            # routeFailure 呈现系统错误卡；后续用户重试会重新进入完整路由链。
            replacement_content = ""
        else:
            replacement_content = ""
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
    def _control_failure_code(cls, response) -> str | None:
        """Read a code-owned terminal failure without inspecting model text."""

        target = next(
            (message for message in reversed(cls._response_messages(response))
             if _message_type(message) == "ai"),
            None,
        )
        metadata = getattr(target, "response_metadata", None) if target is not None else None
        code = metadata.get("routeFailure") if isinstance(metadata, dict) else None
        return str(code).strip() or None if code is not None else None

    @classmethod
    def _finalize_response(cls, request, handler, response, route: dict[str, Any] | None,
                           *, final_entry_id: str | None = None,
                           attach_artifacts: bool = True):
        """Submit one safe final response after every control/protocol boundary.

        The firewall owns rejection, while the model owns user-facing wording.
        This keeps a rejected protocol payload out of the transcript without
        replacing it with a fixed sentence generated by Python.
        """

        protected = cls._protocol_firewall(response, route)
        failure = cls._control_failure_code(protected)
        if failure:
            protected = cls._control_finalization(
                request,
                handler,
                code=failure,
                facts="系统未采纳本次不符合展示或执行边界的内容，未执行额外操作。",
                final_entry_id=final_entry_id,
            )
            # A repair response is still untrusted model output. Do not loop a
            # second repair; if it violates the contract too, fail closed to a
            # structured runtime failure rather than showing unsafe prose.
            protected = cls._protocol_firewall(protected, route)
        if attach_artifacts:
            protected = cls._attach_artifact_presentation(protected, request)
        return cls._complete_presentation(protected, final_entry_id=final_entry_id)

    @classmethod
    async def _finalize_response_async(cls, request, handler, response, route: dict[str, Any] | None,
                                       *, final_entry_id: str | None = None,
                                       attach_artifacts: bool = True):
        protected = cls._protocol_firewall(response, route)
        failure = cls._control_failure_code(protected)
        if failure:
            protected = await cls._control_finalization_async(
                request,
                handler,
                code=failure,
                facts="系统未采纳本次不符合展示或执行边界的内容，未执行额外操作。",
                final_entry_id=final_entry_id,
            )
            protected = cls._protocol_firewall(protected, route)
        if attach_artifacts:
            protected = cls._attach_artifact_presentation(protected, request)
        return cls._complete_presentation(protected, final_entry_id=final_entry_id)

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
        if cls._has_auto_executor_attempt(request, route):
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
            cls._AUTO_EXECUTION_PLAN_ID: str(route.get("planId") or route.get("plan_id") or ""),
        }
        replacement = target.model_copy(
            deep=True,
            update={"content": "", "tool_calls": [call], "response_metadata": metadata},
        )
        updated = list(messages)
        updated[target_index] = replacement
        return cls._replace_response_messages(response, updated)

    @staticmethod
    def _override(request):
        # 模型调用前的工具列表裁剪入口：先算路由与回合策略，再交给
        # _override_for_policy 生成“只含当前回合合法工具”的请求副本。
        route = PlanToolProjectionMiddleware._active_route(
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
        # Artifact ToolMessage 已经携带 Java 签发的附件事实；下一回合只能写最终
        # 正文，不能重新打开规划工具或创建第二份附件。
        if cls._artifact_completed(request):
            return request.override(tools=[])
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
            if artifact_requested(cls._current_user_message(request)) and not cls._artifact_completed(request):
                artifact_tools = [item for item in request.tools if cls._tool_name(item) == cls._ARTIFACT_TOOL]
                if artifact_tools:
                    return cls._artifact_delivery_request(request, artifact_tools)
            return request.override(tools=[])
        # The policy owns the palette for every routed turn. This is the only
        # filter left in the middleware: code never re-combines planStatus,
        # actionId and executionClass to derive behaviour.
        allowed_names = set(policy.planning_tools)
        # 纯聊天或已完成事实调查的收尾回合，只有在用户明确要求持久文件时才
        # 开放通用附件工具。业务路由未完成时不让模型绕过编译层直接生成文件。
        if (
            artifact_requested(cls._current_user_message(request))
            and not cls._artifact_completed(request)
            and cls._tool_name(next((item for item in request.tools if cls._tool_name(item) == cls._ARTIFACT_TOOL), None))
            and policy.mode == TurnMode.MODEL_RESPONSE
            and (route is None or _route_state(route) in {"UNROUTED", "FALLBACK"})
            and not cls._requires_initial_route(request, route)
        ):
            allowed_names.add(cls._ARTIFACT_TOOL)
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
        #   2. 先把 palette 裁剪好，再调用真正的模型（handler）；
        #   3. 按回合模式检查模型输出：
        #      - HANDSHAKE       -> _enforce_handshake（强制提交路由调用）
        #      - MODEL_RESPONSE  -> _enforce_model_response（防越权工具）
        #      - EXECUTE         -> _execution_response（防计划被散文替换）
        all_messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        route = self._active_route(all_messages)
        if self._is_coordination_route(route):
            # 路由工具已原子写入 Batch；从这一刻起不再调用模型决定“派给谁”。
            # 先吸收本轮已经返回的 task 回执，再读取仍可运行的持久化步骤。
            self._record_coordination_results(request, route)
            dispatch = self._coordination_dispatch_response(request, route)
            if dispatch is not None:
                return dispatch
            policy = decide_turn_policy(route)
            artifact_delivery_pending = self._artifact_delivery_pending(request)
            if artifact_delivery_pending:
                final_entry_id = None
                response = handler(self._override_for_policy(request, policy, route))
            else:
                with stream_model_output_scope() as final_entry_id:
                    response = handler(self._override_for_policy(request, policy, route))
            response = self._enforce_model_response(
                request, response, policy, handler,
            )
            response = self._enforce_artifact_delivery(request, response, handler)
            return self._finalize_response(
                request,
                handler,
                self._coordination_summary_response(response, route),
                route,
                final_entry_id=final_entry_id,
            )
        # 已有唯一、近期的项目查询候选时，“这个项目”只需要将定位线索重新带入
        # project.investigate。必须先于首轮 project.list 快捷路径，否则每个追问
        # 都会无意义地重复查询项目列表，既增加时延，也掩盖候选没有被复用的问题。
        context_project_investigation = self._code_owned_context_project_investigation_route(request, route)
        if context_project_investigation is not None:
            return context_project_investigation
        initial_project_list = self._code_owned_initial_project_list_route(request, route)
        if initial_project_list is not None:
            return initial_project_list
        project_list = self._code_owned_project_list_route(request, route)
        if project_list is not None:
            return project_list
        project_investigation = self._code_owned_project_investigation_route(request, route)
        if project_investigation is not None:
            return project_investigation
        # 项目调查回执只提供给主 Agent 做最终组织；不能在这里直接返回固定
        # 摘要，否则不同问题会得到同一份模板，且最终回答不会经过模型流式输出。
        coordination_call = self._code_owned_coordination_route_call(request, all_messages)
        if coordination_call is not None:
            return coordination_call
        policy = decide_turn_policy(route)
        if policy.mode == TurnMode.EXECUTE:
            code_owned = self._code_owned_execution_call(
                request, route, policy.delegate_agent,
            )
            if code_owned is not None:
                return code_owned
        final_synthesis = (
            policy.mode == TurnMode.EXECUTE
            and self._executor_was_called(request, route, policy.delegate_agent)
        )
        direct_final = (
            policy.mode == TurnMode.MODEL_RESPONSE
            and not self._requires_initial_route(request, route)
        )
        final_entry_id = None
        artifact_delivery_pending = self._artifact_delivery_pending(request)
        if (final_synthesis or direct_final) and not artifact_delivery_pending:
            # 只有无工具收尾候选才直播。若模型仍产生工具调用，tracker 会抑制
            # 临时文本，随后由 _complete_presentation 标为 internal。
            with stream_model_output_scope() as final_entry_id:
                response = handler(self._override_for_policy(request, policy, route))
        else:
            response = handler(self._override_for_policy(request, policy, route))
        if (
            policy.mode == TurnMode.EXECUTE
            and self._executor_was_called(request, route, policy.delegate_agent)
        ):
            response = self._enforce_completed_execution_synthesis(
                request, response, handler, final_entry_id=final_entry_id,
            )
        if final_synthesis or direct_final:
            response = self._enforce_artifact_delivery(request, response, handler)
        if self._requires_initial_route(request, route):
            return self._finalize_response(
                request,
                handler,
                self._enforce_initial_route(request, response, handler),
                route,
                final_entry_id=final_entry_id,
            )
        if policy.mode == TurnMode.HANDSHAKE:
            return self._finalize_response(
                request,
                handler,
                self._enforce_handshake(request, response, route, handler),
                route,
                final_entry_id=final_entry_id,
            )
        if policy.mode == TurnMode.MODEL_RESPONSE:
            return self._finalize_response(
                request,
                handler,
                self._enforce_model_response(request, response, policy, handler),
                route,
                final_entry_id=final_entry_id,
            )
        return self._finalize_response(
            request,
            handler,
            self._execution_response(request, response, route),
            route,
            final_entry_id=final_entry_id,
        )

    async def awrap_model_call(self, request, handler):
        all_messages = list((getattr(request, "state", {}) or {}).get("messages") or [])
        route = self._active_route(all_messages)
        if self._is_coordination_route(route):
            self._record_coordination_results(request, route)
            dispatch = self._coordination_dispatch_response(request, route)
            if dispatch is not None:
                return dispatch
            policy = decide_turn_policy(route)
            artifact_delivery_pending = self._artifact_delivery_pending(request)
            if artifact_delivery_pending:
                final_entry_id = None
                response = await handler(self._override_for_policy(request, policy, route))
            else:
                with stream_model_output_scope() as final_entry_id:
                    response = await handler(self._override_for_policy(request, policy, route))
            response = await self._enforce_model_response_async(
                request, response, policy, handler,
            )
            response = await self._enforce_artifact_delivery_async(request, response, handler)
            return await self._finalize_response_async(
                request,
                handler,
                self._coordination_summary_response(response, route),
                route,
                final_entry_id=final_entry_id,
            )
        # 与同步入口保持相同顺序：候选只用于重新定位，不能被首轮列表快捷路径
        # 覆盖成一次新的 project.list 查询。
        context_project_investigation = self._code_owned_context_project_investigation_route(request, route)
        if context_project_investigation is not None:
            return context_project_investigation
        initial_project_list = self._code_owned_initial_project_list_route(request, route)
        if initial_project_list is not None:
            return initial_project_list
        project_list = self._code_owned_project_list_route(request, route)
        if project_list is not None:
            return project_list
        project_investigation = self._code_owned_project_investigation_route(request, route)
        if project_investigation is not None:
            return project_investigation
        # 项目调查回执只提供给主 Agent 做最终组织；不能在这里直接返回固定
        # 摘要，否则不同问题会得到同一份模板，且最终回答不会经过模型流式输出。
        coordination_call = self._code_owned_coordination_route_call(request, all_messages)
        if coordination_call is not None:
            return coordination_call
        policy = decide_turn_policy(route)
        if policy.mode == TurnMode.EXECUTE:
            code_owned = self._code_owned_execution_call(
                request, route, policy.delegate_agent,
            )
            if code_owned is not None:
                return code_owned
        final_synthesis = (
            policy.mode == TurnMode.EXECUTE
            and self._executor_was_called(request, route, policy.delegate_agent)
        )
        direct_final = (
            policy.mode == TurnMode.MODEL_RESPONSE
            and not self._requires_initial_route(request, route)
        )
        final_entry_id = None
        artifact_delivery_pending = self._artifact_delivery_pending(request)
        if (final_synthesis or direct_final) and not artifact_delivery_pending:
            with stream_model_output_scope() as final_entry_id:
                response = await handler(self._override_for_policy(request, policy, route)
            )
        else:
            response = await handler(self._override_for_policy(request, policy, route))
        if (
            policy.mode == TurnMode.EXECUTE
            and self._executor_was_called(request, route, policy.delegate_agent)
        ):
            if self._response_has_tool_calls(response):
                with stream_model_output_scope(entry_id=final_entry_id):
                    retry = await handler(request.override(tools=[]))
                if self._response_has_tool_calls(retry):
                    response = AIMessage(
                        name="oa-main-agent",
                        content="",
                        response_metadata={"routeFailure": "SYNTHESIS_TOOL_CALL_BLOCKED"},
                        additional_kwargs={self._UI_PRESENTATION_KEY: {"schemaVersion": 2, "kind": "internal"}},
                    )
                else:
                    response = retry
        if final_synthesis or direct_final:
            response = await self._enforce_artifact_delivery_async(request, response, handler)
        if self._requires_initial_route(request, route):
            return await self._finalize_response_async(
                request,
                handler,
                await self._enforce_initial_route_async(request, response, handler),
                route,
                final_entry_id=final_entry_id,
            )
        if policy.mode == TurnMode.HANDSHAKE:
            return await self._finalize_response_async(
                request,
                handler,
                await self._enforce_handshake_async(request, response, route, handler),
                route,
                final_entry_id=final_entry_id,
            )
        if policy.mode == TurnMode.MODEL_RESPONSE:
            return await self._finalize_response_async(
                request,
                handler,
                await self._enforce_model_response_async(request, response, policy, handler),
                route,
                final_entry_id=final_entry_id,
            )
        return await self._finalize_response_async(
            request,
            handler,
            self._execution_response(request, response, route),
            route,
            final_entry_id=final_entry_id,
        )

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
                # ``source_*_id`` 是 Java 业务对象的内部来源字段。模型可能从刚刚
                # 收到的工具结果或 UI 展示标识中误抄它；主图只允许随后基于有效
                # candidateId 从 checkpoint 重新签发定向核验，不能把模型参数当事实。
                # 用户明确写出的编号仍会由 route_conversation 从原始用户消息按既有
                # 规则恢复并经过编译器/Java 校验，因此这里不会把 UI 误引用放进行计划。
                for source_field in ("source_schedule_id", "source_booking_id", "source_party_file_id"):
                    raw_plan.pop(source_field, None)
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
                if candidate.capability_id == "project":
                    # 项目列表候选只定位用户所指的项目。project_id 会随着新的
                    # WorkOrder 重新进入 Java Project Provider，Provider 仍按
                    # 当前成员关系、任务隐私和文件权限验证，候选绝不是事实源。
                    project_id = str(candidate.trusted_plan.get("project_id") or "").strip()
                    if not project_id:
                        args.pop("context_candidate_id", None)
                        call["args"] = args
                        return call
                    args["candidate_plan"] = {
                        **plan,
                        "project_id": project_id,
                        "_context_candidate_proof": context_candidate_proof(candidate.candidate_id),
                        "_context_candidate_kind": candidate.kind,
                    }
                    audit_context_decision(
                        state,
                        event="project_candidate_bound",
                        candidateId=candidate.candidate_id,
                        kind=candidate.kind,
                        intent=context_intent,
                        confidence=context_confidence,
                    )
                else:
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

    @classmethod
    def _code_owned_task_call(cls, request, call: dict[str, Any]) -> bool:
        """验证根图 ``task`` 调用确实由代码从当前路由事实签发。

        已解析的 WorkOrder 不能因为模型随后自由输出 ``task`` 就被重绑为当前
        计划。否则同一份 ``project.list`` 回执会被模型伪装成多个项目明细委派，
        最终都执行成相同的列表查询。这里要求调用 ID 同时存在于带代码标记的
        AIMessage 中；模型文字即便猜中了子 Agent 名称、计划 ID 或描述格式，也
        无法自行写入该消息元数据。
        """

        state = getattr(request, "state", {}) or {}
        messages = list(state.get("messages") or [])
        route = cls._active_route(messages)
        if not isinstance(route, dict):
            return False
        call_id = str(call.get("id") or "").strip()
        if not call_id:
            return False

        if cls._is_coordination_route(route):
            batch_id = cls._coordination_batch_id(route)
            for message in _current_turn_messages(messages):
                if _message_type(message) != "ai":
                    continue
                metadata = getattr(message, "response_metadata", {}) or {}
                if str(metadata.get("coordinationBatchId") or "") != batch_id:
                    continue
                for issued in getattr(message, "tool_calls", None) or []:
                    if (
                        isinstance(issued, dict)
                        and str(issued.get("name") or "") == "task"
                        and str(issued.get("id") or "") == call_id
                    ):
                        return True
            return False

        if _route_state(route) == "FALLBACK":
            # 未编译 fallback 没有可校验 WorkOrder，保留其既有受限委派能力；
            # 其他路由状态下的 task 一律不能由模型自由构造。
            return True
        if _route_state(route) != "RESOLVED":
            return False
        expected_plan_id = str(route.get("planId") or route.get("plan_id") or "").strip()
        if not expected_plan_id:
            return False
        for message in _current_turn_messages(messages):
            if _message_type(message) != "ai":
                continue
            metadata = getattr(message, "response_metadata", {}) or {}
            if not (
                metadata.get(cls._AUTO_EXECUTION_MARKER) is True
                and str(metadata.get(cls._AUTO_EXECUTION_PLAN_ID) or "").strip() == expected_plan_id
            ):
                continue
            for issued in getattr(message, "tool_calls", None) or []:
                if (
                    isinstance(issued, dict)
                    and str(issued.get("name") or "") == "task"
                    and str(issued.get("id") or "") == call_id
                ):
                    return True
        return False

    @staticmethod
    def _uncompiled_task_rejection(call: dict[str, Any]) -> ToolMessage:
        """返回结构化拒绝，避免未签发的 task 触达任一领域子 Agent。"""

        call_id = str(call.get("id") or "").strip()
        return ToolMessage(
            name="task",
            tool_call_id=call_id,
            status="error",
            content=json.dumps({
                "ok": False,
                "code": "UNCOMPILED_TASK_REJECTED",
                "message": "领域委派必须由当前已编译工作单签发，已拒绝未绑定的 task 调用。",
            }, ensure_ascii=False, separators=(",", ":")),
        )

    def wrap_tool_call(self, request, handler):
        call = getattr(request, "tool_call", None)
        if isinstance(call, dict) and str(call.get("name") or "") == "task" and not self._code_owned_task_call(request, call):
            return self._uncompiled_task_rejection(call)
        return handler(self._inject_compiled_plan(request))

    async def awrap_tool_call(self, request, handler):
        call = getattr(request, "tool_call", None)
        if isinstance(call, dict) and str(call.get("name") or "") == "task" and not self._code_owned_task_call(request, call):
            return self._uncompiled_task_rejection(call)
        return await handler(self._inject_compiled_plan(request))


__all__ = ["PlanToolProjectionMiddleware"]
