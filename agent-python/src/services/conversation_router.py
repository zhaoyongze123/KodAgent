"""Fast, deterministic first-pass routing for natural conversations.

The model can still make the final routing decision. This classifier prevents
obvious greetings and follow-ups from entering an expensive domain workflow.
"""

from __future__ import annotations

import re
from contextvars import ContextVar
from dataclasses import dataclass
from threading import Lock

from langgraph.config import get_config

from ..domain.conversation import ConversationRoute, ReasoningEffort, TaskComplexity


_FOLLOW_UP = re.compile(r"刚才|上一轮|上面|前面|刚刚|继续|还是|那个|它|他|为什么|哪个|哪些|改成|换成|改一下|取消|现在还能|当前.*(?:是否|有没有|能不能)")
_IMAGE = re.compile(r"画一张|生成图片|生成一张图|海报|插画|图片")
_WORKFLOW = re.compile(r"工作流|流程图|架构图|时序图|审批流程|流程设计|mermaid")
_ACTION = re.compile(
    r"预约|预定|提交|创建|修改|取消|确认|通过|同意|驳回|"
    r"订(?:会议室|[一二三四五六七八九十\\d]+(?:间|个)?会议室)|"
    r"起草|拟定|生成(?:一份|一个)?(?:待确认)?草稿|"
    r"安排(?:会议|日程|.*(?:参加|出席))|申请(?:请假|出差)|发起(?:审批|申请)"
)
_FOLLOW_UP_WRITE = re.compile(r"取消|确认|提交|通过|同意|驳回|修改|改成|换成")
_SMALL_TALK = re.compile(r"^(?:你好|您好|嗨|在吗|谢谢|感谢|再见|早上好|下午好|晚上好)[！!。？?\s]*$")
_MULTI_STEP = re.compile(
    r"(?:查询|查看|搜索|查一下|帮我).*?(?:并(?:且)?|然后|之后|再|同时|以及|和).*?(?:查询|查看|搜索|总结|生成|预约|提交|审批|日程|文件|会议室)"
    r"|(?:并(?:且)?|然后|之后|再|同时|以及|和).*?(?:查询|查看|搜索|总结|生成|预约|提交|审批|日程|文件|会议室)"
)
_RICH_OUTPUT = re.compile(r"总结|汇总|分析|对比|生成(?:报告|内容|文档)|写一份|起草")
_ENTITY_DISAMBIGUATION = re.compile(
    r"我(?:的)?(?:领导|上级)|部门(?:负责人|领导)|[\u4e00-\u9fff]{1,3}(?:主任|院长|经理)(?:参加|出席|来)?"
    r"|[侯王李张陈刘赵孙周吴]总(?=$|[，,、和与参加出席来])"
    r"|(?:研发|财务|行政|办公室)?(?:部)?(?:小[王李张陈刘赵]|[张李王陈刘赵](?:姐|哥))"
)


@dataclass(frozen=True)
class RouteReasoningPolicy:
    """The route-derived model policy for one Run.

    The ContextVar handles normal async propagation. The Run map is a fallback
    for Tool/sub-agent executors that cross a thread or task boundary.
    """

    task_complexity: TaskComplexity
    reasoning_effort: ReasoningEffort


_ROUTE_REASONING_POLICY: ContextVar[RouteReasoningPolicy | None] = ContextVar(
    "kodagent_route_reasoning_policy", default=None
)
_RUN_REASONING_POLICIES: dict[str, RouteReasoningPolicy] = {}
_RUN_REASONING_POLICIES_LOCK = Lock()


def _runtime_run_id() -> str | None:
    try:
        config = get_config()
    except RuntimeError:
        return None
    metadata = config.get("metadata") or {}
    value = config.get("run_id") or metadata.get("runId") or metadata.get("run_id")
    return str(value) if value is not None and str(value).strip() else None


def _requires_reasoning_safety_floor(route: ConversationRoute, message: str) -> bool:
    """Keep state-changing, confirmation, and disambiguation work off `off`."""
    return bool(
        route.mode == "business_action"
        or route.needs_confirmation
        or _ACTION.search(message)
        or _ENTITY_DISAMBIGUATION.search(message)
        or _MULTI_STEP.search(message)
    )


def set_route_reasoning_policy(route: ConversationRoute, message: str) -> RouteReasoningPolicy:
    """Persist the route policy for the rest of the current Agent Run.

    This is the backend guardrail for a model-produced route result. Even if a
    future classifier incorrectly returns ``off``, writes, confirmations,
    reservations, approvals, entity disambiguation, and multi-step work keep
    their required reasoning budget.
    """
    effort: ReasoningEffort = route.reasoning_effort
    if _requires_reasoning_safety_floor(route, message):
        effort = "low"
        route.task_complexity = "complex"
    route.reasoning_effort = effort
    policy = RouteReasoningPolicy(route.task_complexity, effort)
    _ROUTE_REASONING_POLICY.set(policy)
    if run_id := _runtime_run_id():
        with _RUN_REASONING_POLICIES_LOCK:
            _RUN_REASONING_POLICIES[run_id] = policy
    return policy


def get_route_reasoning_policy() -> RouteReasoningPolicy | None:
    policy = _ROUTE_REASONING_POLICY.get()
    if policy is not None:
        return policy
    run_id = _runtime_run_id()
    if not run_id:
        return None
    with _RUN_REASONING_POLICIES_LOCK:
        return _RUN_REASONING_POLICIES.get(run_id)


def clear_route_reasoning_policy() -> None:
    """Clear the policy when a root Run starts or finishes to prevent leaks."""
    _ROUTE_REASONING_POLICY.set(None)
    if run_id := _runtime_run_id():
        with _RUN_REASONING_POLICIES_LOCK:
            _RUN_REASONING_POLICIES.pop(run_id, None)


def _route(
    mode: str,
    *,
    complexity: TaskComplexity,
    reasoning_effort: ReasoningEffort,
    **kwargs,
) -> ConversationRoute:
    return ConversationRoute(
        mode=mode,
        task_complexity=complexity,
        reasoning_effort=reasoning_effort,
        **kwargs,
    )


def classify_message(message: str, *, task_complexity: TaskComplexity = "simple") -> ConversationRoute:
    text = (message or "").strip()
    if not text:
        return _route("chat", complexity="simple", reasoning_effort="off", reason="empty message")
    if _IMAGE.search(text):
        return _route("image_generation", complexity="complex", reasoning_effort="low", requires_structured_route=True, needs_tools=True, show_progress=True, reason="image request")
    if _WORKFLOW.search(text):
        return _route("workflow", complexity="complex", reasoning_effort="low", requires_structured_route=True, needs_tools=True, show_progress=True, reason="workflow or diagram request")
    if _FOLLOW_UP.search(text):
        if _FOLLOW_UP_WRITE.search(text):
            return _route(
                "business_action",
                complexity="complex",
                reasoning_effort="low",
                requires_structured_route=True,
                needs_tools=True,
                needs_confirmation=True,
                show_progress=True,
                reason="follow-up business action",
            )
        needs_tools = bool(re.search(r"重新|现在|冲突|空闲|提交|确认", text))
        requires_complex_reasoning = bool(_MULTI_STEP.search(text) or _ENTITY_DISAMBIGUATION.search(text))
        return ConversationRoute(
            mode="follow_up",
            task_complexity="complex" if needs_tools or requires_complex_reasoning else "simple",
            reasoning_effort="low" if needs_tools or requires_complex_reasoning else "off",
            needs_tools=needs_tools,
            needs_confirmation=bool(re.search(r"确认|提交", text)),
            show_progress=needs_tools,
            reason="follow-up can reuse current task memory",
        )
    if _ACTION.search(text):
        return _route(
            "business_action",
            complexity="complex",
            reasoning_effort="low",
            requires_structured_route=True,
            needs_tools=True,
            needs_confirmation=bool(re.search(r"预约|预定|提交|创建|修改|取消|确认|通过|同意|驳回", text)),
            show_progress=True,
            reason="business action",
        )
    if _MULTI_STEP.search(text):
        return _route("fresh_query", complexity="complex", reasoning_effort="low", requires_structured_route=True, needs_tools=True, show_progress=True, reason="multi-step request")
    if _ENTITY_DISAMBIGUATION.search(text):
        return _route("fresh_query", complexity="complex", reasoning_effort="low", requires_structured_route=True, needs_tools=True, show_progress=True, reason="business entity disambiguation")
    if _RICH_OUTPUT.search(text):
        return _route("fresh_query", complexity="complex", reasoning_effort="low", requires_structured_route=True, needs_tools=True, show_progress=True, reason="request with synthesis")
    if _SMALL_TALK.search(text):
        return _route("chat", complexity="simple", reasoning_effort="off", needs_tools=False, show_progress=False, reason="simple conversation")
    # Domain selection is intentionally deferred to the model's capability
    # contracts and tool schemas. Unknown wording still receives the planning
    # palette, but it is not forced into a structured route after the model
    # has already answered naturally. This preserves context-only requests
    # such as "详细说下" while the model remains free to call the router for a
    # genuine business request expressed in unfamiliar wording.
    return _route("fresh_query", complexity=task_complexity,
                  reasoning_effort="low" if task_complexity == "complex" else "off",
                  needs_tools=True, show_progress=task_complexity == "complex",
                  reason="semantic capability routing deferred to agent")
