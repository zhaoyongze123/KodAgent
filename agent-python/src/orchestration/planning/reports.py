"""Pure compiler for read-only report plans."""

from __future__ import annotations

from typing import Any

from ...domain.plan import CompiledTaskPlan
from ..action_validation import authorized_source_fields, validate_action_payload
from ..capabilities import action_field_specs, resolve_action
from .common import plan_id, present
from .contracts import CompileContext


_REPORT_TOOLS = {
    "APPROVAL": "approval_report", "APPROVALS": "approval_report",
    "MEETING": "meeting_report", "MEETINGS": "meeting_report",
    "SCHEDULE": "schedule_report", "CALENDAR": "schedule_report",
    "PARTY_FILE": "party_file_report", "PARTY_FILES": "party_file_report",
}


class ReportPlanCompiler:
    capability_id = "reporting"

    def compile(self, context: CompileContext) -> CompiledTaskPlan | None:
        if context.capability_id != self.capability_id or context.execution_class != "report":
            return None
        payload = dict(context.payload)
        operation = str(payload.get("operation") or "").strip().upper()
        tool_name = _REPORT_TOOLS.get(operation)
        canonical: dict[str, Any] = {"operation": operation, "rangeRequired": True}
        if not tool_name:
            return CompiledTaskPlan(
                plan_id=plan_id(context.capability_id, context.execution_class, canonical), status="UNSUPPORTED",
                capability_id=context.capability_id, execution_class="report", canonical=canonical,
                issues=["报表类型必须是 APPROVAL、MEETING、SCHEDULE 或 PARTY_FILE"],
            )
        action = resolve_action(context.capability_id, str(payload.get("action_id") or payload.get("actionId") or ""), operation)
        if action is not None:
            for field in action_field_specs(action):
                if present(payload.get(field.name)):
                    canonical[field.name] = payload[field.name]
            validation = validate_action_payload(action, payload, authorized_source_fields=authorized_source_fields(payload))
            if not validation.ok:
                return CompiledTaskPlan(
                    plan_id=plan_id(context.capability_id, context.execution_class, canonical), status="CLARIFY",
                    capability_id=context.capability_id, execution_class="report", canonical=canonical,
                    issues=validation.issues, missing_fields=validation.missing_fields,
                    clarification_question="请补充报表所需的时间范围和筛选字段后继续。",
                )
        return CompiledTaskPlan(
            plan_id=plan_id(context.capability_id, context.execution_class, canonical), status="RESOLVED",
            capability_id=context.capability_id, execution_class="report", execution_tool=tool_name,
            canonical=canonical,
        )


__all__ = ["ReportPlanCompiler"]
