"""上下文候选的目标核验与二次编译。

文件职责
========
多轮候选只解决“用户大概率在说哪一条记录”，不能提供写操作事实。本模块把这条
原则落成代码拥有的两段式状态机：

``候选定位`` -> ``Java 定向只读核验`` -> ``代码二次编译`` -> ``写工作流 / HITL``

候选中保存的 source ID 仅会被写入第一步的定向读取 WorkOrder；它绝不会直接
进入 UPDATE/CANCEL 的 ``candidate_plan``。Java 在本轮返回对象、可编辑状态和
正式 ID 后，才由 :func:`verified_follow_up_route` 重新调用中央编译器生成写计划。

本模块不调用模型、不调用 Java。它只构建及验证跨模块契约，实际 Java 调用仍由
领域子 Agent 的 helper 工具完成。
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage

from .compiler import compile_plan
from .planning.common import int_or_none, plan_id
from .route_state import message_content, message_type
from .delegated_receipt import parse_execution_receipt


@dataclass(frozen=True)
class TargetResolutionSpec:
    """一种可由近期候选发起的定向 Java 核验。

    参数：
        capability_id：原始写动作所属领域。
        action_ids：允许进入本核验的正式 UPDATE/CANCEL 动作。
        verification_tool：子 Agent 必须调用的只读详情工具。
        source_field：写计划和候选内部使用的 source 字段名。
        canonical_source_key：WorkOrder 中使用的驼峰字段名。
        source_types：Java 明确返回类型时允许的对象类型。
    """

    capability_id: str
    action_ids: tuple[str, ...]
    verification_tool: str
    source_field: str
    canonical_source_key: str
    source_types: tuple[str, ...]


_SPECS = (
    TargetResolutionSpec(
        capability_id="schedule",
        action_ids=("schedule.update", "schedule.cancel"),
        verification_tool="get_personal_schedule",
        source_field="source_schedule_id",
        canonical_source_key="sourceScheduleId",
        source_types=("PERSONAL_SCHEDULE",),
    ),
    TargetResolutionSpec(
        capability_id="meeting",
        action_ids=("meeting.update", "meeting.cancel"),
        verification_tool="get_my_meeting_booking",
        source_field="source_booking_id",
        canonical_source_key="sourceBookingId",
        source_types=("MEETING_BOOKING",),
    ),
)


def target_resolution_spec(capability_id: str | None, action_id: str | None) -> TargetResolutionSpec | None:
    """按已注册的领域和动作找到唯一核验规格，未知写动作不能走此捷径。"""

    capability = str(capability_id or "").strip()
    action = str(action_id or "").strip()
    return next(
        (
            spec for spec in _SPECS
            if spec.capability_id == capability and action in spec.action_ids
        ),
        None,
    )


def is_target_resolution_route(route: dict[str, Any] | None) -> bool:
    """判断路由是否为内部只读核验计划，而不是普通的业务写计划。"""

    plan = route.get("executionPlan") if isinstance(route, dict) else None
    return isinstance(plan, dict) and plan.get("targetResolution") is True


def build_target_resolution_plan(
    *,
    capability_id: str,
    action_id: str,
    candidate_plan: dict[str, Any],
    target_resolution: dict[str, Any],
) -> dict[str, Any] | None:
    """构造仅用于 Java 定向读取的 canonical plan。

    ``target_resolution`` 必须已经由计划投影层基于 checkpoint 候选和 HMAC 证明
    写入；此函数仍会重新校验领域、动作、工具和 ID，避免把普通模型字段升级为
    定向查询权限。
    """

    spec = target_resolution_spec(capability_id, action_id)
    if spec is None:
        return None
    if str(target_resolution.get("verificationTool") or "") != spec.verification_tool:
        return None
    source_id = int_or_none(target_resolution.get(spec.source_field))
    if source_id is None or source_id <= 0:
        return None

    # 只保留用户本轮提交的业务变更字段。source 字段和所有内部标记均不能从
    # 候选透传到第二阶段写计划。
    original_payload = {
        key: value
        for key, value in dict(candidate_plan or {}).items()
        if not key.startswith("_") and key not in {"source_schedule_id", "source_booking_id"}
    }
    original_payload["action_id"] = action_id
    original_payload["operation"] = str(target_resolution.get("operation") or original_payload.get("operation") or "").upper()

    canonical = {
        "targetResolution": True,
        "version": "1",
        "originalActionId": action_id,
        "originalExecutionClass": "workflow",
        "verificationTool": spec.verification_tool,
        "candidateId": str(target_resolution.get("candidateId") or ""),
        spec.canonical_source_key: source_id,
        "pendingCandidatePlan": original_payload,
    }
    return canonical


def target_resolution_compiled_route(
    *,
    capability_id: str,
    action_id: str,
    candidate_plan: dict[str, Any],
    target_resolution: dict[str, Any],
) -> dict[str, Any] | None:
    """把可信候选定位转换为路由工具可返回的 RESOLVED 只读计划。"""

    canonical = build_target_resolution_plan(
        capability_id=capability_id,
        action_id=action_id,
        candidate_plan=candidate_plan,
        target_resolution=target_resolution,
    )
    if canonical is None:
        return None
    spec = target_resolution_spec(capability_id, action_id)
    if spec is None:
        return None
    return {
        "planId": plan_id(capability_id, "target_resolution", canonical),
        "planStatus": "RESOLVED",
        "capabilityId": capability_id,
        "actionId": action_id,
        "executionClass": "metadata_query",
        "executionTool": spec.verification_tool,
        "executionPlan": canonical,
        "plan": {
            "plan_id": plan_id(capability_id, "target_resolution", canonical),
            "status": "RESOLVED",
            "capability_id": capability_id,
            "execution_class": "metadata_query",
            "execution_tool": spec.verification_tool,
            "canonical": canonical,
        },
    }


def _tool_call_id(message: Any) -> str:
    value = message.get("tool_call_id") if isinstance(message, dict) else getattr(message, "tool_call_id", "")
    return str(value or "").strip()


def _tool_calls(message: Any) -> list[dict[str, Any]]:
    value = message.get("tool_calls") if isinstance(message, dict) else getattr(message, "tool_calls", None)
    return [dict(call) for call in value if isinstance(call, dict)] if isinstance(value, list) else []


def _matching_resolution_receipt(messages: list[Any], route: dict[str, Any]):
    """读取当前回合内、匹配该核验 WorkOrder 的唯一 task 回执。"""

    canonical = route.get("executionPlan") if isinstance(route, dict) else None
    plan_id_value = str(route.get("planId") or "").strip() if isinstance(route, dict) else ""
    if not isinstance(canonical, dict) or not plan_id_value:
        return None
    expected_tool = str(canonical.get("verificationTool") or "")
    for index, message in enumerate(messages):
        if message_type(message) != "tool" or _tool_call_id(message) == "":
            continue
        call_id = _tool_call_id(message)
        parent_call = next(
            (
                call for previous in reversed(messages[:index])
                for call in _tool_calls(previous)
                if str(call.get("id") or "") == call_id and str(call.get("name") or "") == "task"
            ),
            None,
        )
        if parent_call is None:
            continue
        args = parent_call.get("args") if isinstance(parent_call.get("args"), dict) else {}
        # 延迟导入避免 domain_dispatch 与本模块在启动时互相初始化；解析仍由
        # WorkOrder 的唯一实现完成，不能手写 JSON 读取逻辑。
        from .domain_dispatch import parse_work_order

        work_order = parse_work_order(str(args.get("description") or ""))
        if (
            work_order is None
            or work_order.plan_id != plan_id_value
            or work_order.execution_tool != expected_tool
        ):
            continue
        return parse_execution_receipt(message_content(message))
    return None


def _verified_source_id(spec: TargetResolutionSpec, result: Any, requested_id: int) -> int | None:
    """从本轮 Java 详情结果确认对象类型、可编辑性和 ID 没有漂移。"""

    if not isinstance(result, dict) or result.get("editable") is not True:
        return None
    source_type = str(result.get("sourceType") or "").strip().upper()
    if source_type and source_type not in spec.source_types:
        return None
    if spec.capability_id == "schedule":
        actual_id = int_or_none(result.get("sourceId") or result.get("scheduleId") or result.get("id"))
    else:
        actual_id = int_or_none(result.get("bookingId") or result.get("sourceId") or result.get("id"))
    return actual_id if actual_id == requested_id else None


def verified_follow_up_route(messages: list[Any], route: dict[str, Any]) -> dict[str, Any] | None:
    """核验成功后，由代码重编译真正的写 WorkOrder。

    该函数是核心安全边界：只有当前回合中匹配的、结构化成功回执才能产生 source
    字段；模型、候选摘要和历史 ToolMessage 都不能直接进入这一步。
    """

    if not is_target_resolution_route(route):
        return None
    canonical = route.get("executionPlan") or {}
    capability = str(route.get("capabilityId") or "")
    action_id = str(route.get("actionId") or canonical.get("originalActionId") or "")
    spec = target_resolution_spec(capability, action_id)
    if spec is None:
        return None
    requested_id = int_or_none(canonical.get(spec.canonical_source_key))
    receipt = _matching_resolution_receipt(messages, route)
    if (
        requested_id is None
        or receipt is None
        or receipt.status != "SUCCEEDED"
        or receipt.executor_tool != spec.verification_tool
    ):
        return None
    verified_id = _verified_source_id(spec, receipt.result, requested_id)
    if verified_id is None:
        return None
    pending = canonical.get("pendingCandidatePlan")
    payload = dict(pending) if isinstance(pending, dict) else {}
    payload.pop("source_schedule_id", None)
    payload.pop("source_booking_id", None)
    payload.pop("_authorized_source_fields", None)
    payload["action_id"] = action_id
    payload["operation"] = str(payload.get("operation") or "").upper()
    payload[spec.source_field] = verified_id
    payload["_authorized_source_fields"] = [spec.source_field]
    compiled = compile_plan(
        capability_id=capability,
        execution_class="workflow",
        candidate_plan=payload,
    )
    if compiled is None or compiled.status != "RESOLVED" or not compiled.execution_tool:
        return None
    final_route = {
        "planStatus": "RESOLVED",
        "routeState": "RESOLVED",
        "capabilityId": capability,
        "actionId": action_id,
        "executionClass": compiled.execution_class,
        "executionTool": compiled.execution_tool,
        "executionPlan": compiled.canonical,
        "planId": compiled.plan_id,
    }
    return final_route


def target_resolution_error(messages: list[Any], route: dict[str, Any]) -> str | None:
    """把已返回但未通过核验的回执转换为安全的用户可见结果。"""

    if not is_target_resolution_route(route):
        return None
    receipt = _matching_resolution_receipt(messages, route)
    if receipt is None:
        return None
    if receipt.status != "SUCCEEDED":
        return "无法核验要修改的业务对象。它可能已删除、无权访问或暂时不可用，请重新查询后再试。"
    if verified_follow_up_route(messages, route) is None:
        return "该业务对象当前不可修改或信息已变化，请重新查询后再试。"
    return None


class TargetResolutionMiddleware(AgentMiddleware):
    """在只读核验回执后由代码写入二次编译路由。

    中间件放在主图中而非领域子 Agent 中，因为“核验成功后是否能产生写计划”是
    中央编译器的控制面职责。子 Agent 只执行 WorkOrder 中唯一允许的详情读取。
    """

    name = "TargetResolutionMiddleware"

    @staticmethod
    def _route(messages: list[Any]) -> dict[str, Any] | None:
        from .route_state import route_result

        return route_result(messages)

    @staticmethod
    def _synthetic_route_message(route: dict[str, Any], *, source_plan_id: str) -> ToolMessage:
        """构造与 route_conversation 真正成功响应一致的受控 ToolMessage。"""

        return ToolMessage(
            name="route_conversation",
            tool_call_id=f"target-resolution-{source_plan_id}",
            content=json.dumps({"ok": True, "data": route}, ensure_ascii=False),
        )

    def before_model(self, state, runtime):
        messages = list((state or {}).get("messages") or [])
        route = self._route(messages)
        if not is_target_resolution_route(route):
            return None
        follow_up = verified_follow_up_route(messages, route)
        if follow_up is not None:
            return {
                "messages": [self._synthetic_route_message(
                    follow_up, source_plan_id=str(route.get("planId") or "resolution"),
                )]
            }
        error = target_resolution_error(messages, route)
        if error is None:
            return None
        clarification = {
            "planStatus": "CLARIFY",
            "routeState": "FIELD_CLARIFICATION",
            "capabilityId": route.get("capabilityId"),
            "actionId": route.get("actionId"),
            "executionClass": "workflow",
            "clarification": {
                "status": "CLARIFY",
                "question": error,
                "issues": ["TARGET_RESOLUTION_FAILED"],
                "missingFields": [],
            },
        }
        return {
            "messages": [self._synthetic_route_message(
                clarification, source_plan_id=str(route.get("planId") or "resolution"),
            )]
        }

    async def abefore_model(self, state, runtime):
        return self.before_model(state, runtime)


__all__ = [
    "TargetResolutionSpec", "build_target_resolution_plan",
    "is_target_resolution_route", "target_resolution_compiled_route", "target_resolution_error",
    "target_resolution_spec", "verified_follow_up_route", "TargetResolutionMiddleware",
]
