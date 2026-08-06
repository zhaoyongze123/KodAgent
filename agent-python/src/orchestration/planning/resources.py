"""Pure compilers for meeting-room and personal-schedule plans."""

from __future__ import annotations

from typing import Any

from ...domain.plan import CompiledTaskPlan
from ...workflows.registry import workflow_registry
from ..capabilities import ACTION_SPECS, action_field_specs, resolve_action
from .common import int_or_none, plan_id, present
from .contracts import CompileContext


_WORKFLOW_TYPES = {"meeting": "meeting_booking", "schedule": "personal_schedule"}
_WORKFLOW_OPERATIONS: dict[str, dict[str, tuple[str, frozenset[str]]]] = {}
for _action in ACTION_SPECS:
    workflow_type = _WORKFLOW_TYPES.get(_action.capability_id)
    if workflow_type is None or _action.execution_class != "workflow":
        continue
    _WORKFLOW_OPERATIONS.setdefault(_action.capability_id, {})[_action.operation] = (
        workflow_type,
        frozenset({_action.operation, *(_alias.upper().replace("-", "_") for _alias in _action.aliases)}),
    )


def _normalize_operation(value: Any, capability_id: str) -> str:
    operation = str(value or "").strip().upper()
    aliases = {
        "CREATE_SCHEDULE": "CREATE", "CREATE_PERSONAL_SCHEDULE": "CREATE",
        "CREATE_DRAFT": "CREATE", "CREATE_SCHEDULE_DRAFT": "CREATE", "NEW_SCHEDULE": "CREATE",
        "UPDATE_SCHEDULE": "UPDATE", "EDIT_SCHEDULE": "UPDATE",
        "CANCEL_SCHEDULE": "CANCEL", "DELETE_SCHEDULE": "CANCEL",
    }
    operation = aliases.get(operation, operation)
    if capability_id == "schedule" and not operation:
        operation = "CREATE"
    return operation


def _workflow_plan(context: CompileContext) -> CompiledTaskPlan:
    payload = dict(context.payload)
    requested = _normalize_operation(
        payload.get("operation") or payload.get("action")
        or ("CREATE" if context.capability_id == "schedule" and payload.get("type") == "personal_schedule" else ""),
        context.capability_id,
    )
    routes = _WORKFLOW_OPERATIONS.get(context.capability_id, {})
    match = next(
        ((operation, workflow_type) for operation, (workflow_type, aliases) in routes.items() if requested in aliases),
        None,
    )
    if match is None:
        return CompiledTaskPlan(
            plan_id=plan_id(context.capability_id, "workflow", {"operation": requested}),
            status="FALLBACK", capability_id=context.capability_id or "general_agent",
            execution_class="workflow", issues=["当前工作流未覆盖该业务操作，保留领域 Agent 继续处理"],
        )
    operation, workflow_type = match
    contract = workflow_registry.get(workflow_type)
    if contract is None or not contract.is_enabled():
        return CompiledTaskPlan(
            plan_id=plan_id(context.capability_id, "workflow", {"workflowType": workflow_type, "operation": operation}),
            status="FALLBACK", capability_id=context.capability_id, execution_class="workflow",
            issues=["对应确定性工作流未启用，保留领域 Agent ReAct 回退"],
        )
    canonical: dict[str, Any] = {"workflowType": workflow_type, "operation": operation, "version": contract.version}
    action = resolve_action(context.capability_id, context.action_id or str(payload.get("action_id") or payload.get("actionId") or ""), operation)
    if action is not None:
        for field in action_field_specs(action):
            if present(payload.get(field.name)):
                canonical[field.name] = payload[field.name]
    if workflow_type == "meeting_booking":
        source_key, canonical_key = "source_booking_id", "sourceBookingId"
    else:
        source_key, canonical_key = "source_schedule_id", "sourceScheduleId"
    source = payload.get(source_key) or payload.get(canonical_key)
    if source is not None:
        source_id = int_or_none(source)
        if source_id is None:
            return CompiledTaskPlan(
                plan_id=plan_id(context.capability_id, "workflow", canonical), status="CLARIFY",
                capability_id=context.capability_id, execution_class="workflow", canonical=canonical,
                issues=["来源业务编号无效"], missing_fields=[source_key],
                clarification_question="请指定要修改或取消的来源记录编号。",
            )
        canonical[canonical_key] = source_id
    return CompiledTaskPlan(
        plan_id=plan_id(context.capability_id, "workflow", canonical), status="RESOLVED",
        capability_id=context.capability_id, execution_class="workflow", execution_tool=contract.tool_name,
        canonical=canonical,
    )


def _metadata_plan(context: CompileContext) -> CompiledTaskPlan:
    payload = dict(context.payload)
    operation = str(payload.get("operation") or payload.get("action") or "QUERY").strip().upper()
    if context.capability_id == "schedule":
        if operation not in {"QUERY", "LIST", "SEARCH", "CALENDAR"}:
            canonical = {"entity": "personal_schedule", "operation": operation}
            return CompiledTaskPlan(
                plan_id=plan_id(context.capability_id, "metadata_query", canonical), status="UNSUPPORTED",
                capability_id=context.capability_id, execution_class="metadata_query", canonical=canonical,
                issues=["个人日程只读计划必须是 QUERY、LIST、SEARCH 或 CALENDAR"],
            )
        date = str(payload.get("date") or "").strip()
        start_time = str(payload.get("start_time") or payload.get("startTime") or "").strip()
        end_time = str(payload.get("end_time") or payload.get("endTime") or "").strip()
        if date and not start_time and not end_time:
            start_time, end_time = f"{date} 00:00:00", f"{date} 23:59:59"
        if not start_time or not end_time:
            canonical = {"entity": "personal_schedule", "operation": "QUERY"}
            return CompiledTaskPlan(
                plan_id=plan_id(context.capability_id, "metadata_query", canonical), status="CLARIFY",
                capability_id=context.capability_id, execution_class="metadata_query", canonical=canonical,
                issues=["查询个人日程必须提供 date 或完整 start_time/end_time"], missing_fields=["date"],
                clarification_question="请提供要查询的日期或开始、结束时间范围。",
            )
        canonical = {"entity": "personal_schedule", "operation": "QUERY", "startTime": start_time, "endTime": end_time}
        return CompiledTaskPlan(
            plan_id=plan_id(context.capability_id, "metadata_query", canonical), status="RESOLVED",
            capability_id=context.capability_id, execution_class="metadata_query", execution_tool="get_my_calendar",
            canonical=canonical,
        )

    if operation not in {"QUERY", "LIST", "SEARCH"}:
        canonical = {"entity": "meeting", "operation": operation}
        return CompiledTaskPlan(
            plan_id=plan_id(context.capability_id, "metadata_query", canonical), status="UNSUPPORTED",
            capability_id=context.capability_id, execution_class="metadata_query", canonical=canonical,
            issues=["会议查询计划必须是 QUERY、LIST 或 SEARCH"],
        )
    start_time = str(payload.get("start_time") or payload.get("startTime") or "").strip()
    end_time = str(payload.get("end_time") or payload.get("endTime") or "").strip()
    if not start_time or not end_time:
        canonical = {"entity": "meeting", "operation": "QUERY"}
        return CompiledTaskPlan(
            plan_id=plan_id(context.capability_id, "metadata_query", canonical), status="CLARIFY",
            capability_id=context.capability_id, execution_class="metadata_query", canonical=canonical,
            issues=["查询会议预约必须提供完整 start_time/end_time"],
            missing_fields=["start_time", "end_time"], clarification_question="请提供要查询的会议开始和结束时间。",
        )
    canonical = {"entity": "meeting", "operation": "QUERY", "startTime": start_time, "endTime": end_time}
    return CompiledTaskPlan(
        plan_id=plan_id(context.capability_id, "metadata_query", canonical), status="RESOLVED",
        capability_id=context.capability_id, execution_class="metadata_query", execution_tool="list_my_meeting_bookings",
        canonical=canonical,
    )


class ResourcePlanCompiler:
    def __init__(self, capability_id: str) -> None:
        if capability_id not in {"meeting", "schedule"}:
            raise ValueError(f"不支持的资源领域: {capability_id}")
        self.capability_id = capability_id

    def compile(self, context: CompileContext) -> CompiledTaskPlan | None:
        if context.capability_id != self.capability_id:
            return None
        if context.execution_class == "metadata_query":
            return _metadata_plan(context)
        if context.execution_class == "workflow":
            return _workflow_plan(context)
        return None


def infer_workflow_capability(candidate_plan: dict[str, Any] | None) -> str | None:
    """Recover only explicit typed workflow shapes, never user prose."""
    payload = candidate_plan if isinstance(candidate_plan, dict) else {}
    entity = str(
        payload.get("entity") or payload.get("object_type") or payload.get("objectType")
        or payload.get("domain") or ""
    ).strip().lower().replace("-", "_")
    if entity in {"party_file", "party_files", "partyfile", "partyfiles"}:
        return "party_file"
    if entity in {"meeting", "meeting_room", "meeting_booking", "meetingroom", "room_booking"}:
        return "meeting"
    if entity in {"schedule", "personal_schedule", "calendar"}:
        return "schedule"
    if any(payload.get(key) not in (None, "", [], {}) for key in ("category", "categoryId", "publish_time", "publishTime", "targets")) and any(
        payload.get(key) not in (None, "", [], {}) for key in ("title", "content", "summary")
    ):
        return "party_file"
    value = str(payload.get("operation") or payload.get("action") or "").strip().upper()
    if payload.get("type") == "personal_schedule" or value in {"CREATE_DRAFT", "CREATE_SCHEDULE_DRAFT"} or "PERSONAL_SCHEDULE" in value or "_SCHEDULE" in value:
        return "schedule"
    if value in {"CREATE", "NEW"}:
        return None
    for capability, routes in _WORKFLOW_OPERATIONS.items():
        if any(value in aliases for _, aliases in routes.values()):
            return capability
    return None


__all__ = ["ResourcePlanCompiler", "infer_workflow_capability"]
