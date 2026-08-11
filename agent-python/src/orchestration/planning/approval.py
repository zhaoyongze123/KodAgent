"""Pure plan compiler for approval read/process actions."""

from __future__ import annotations

from typing import Any

from ...domain.plan import CompiledTaskPlan
from ..query_canonicalizer import canonicalize_approval_query
from .common import plan_id, present
from .contracts import CompileContext


class ApprovalPlanCompiler:
    capability_id = "approval_read"

    def compile(self, context: CompileContext) -> CompiledTaskPlan | None:
        if context.capability_id == "approval_read":
            return self._compile_read(context)
        if context.capability_id == "approval_process":
            return self._compile_process(context)
        return None

    @staticmethod
    def _compile_read(context: CompileContext) -> CompiledTaskPlan | None:
        payload = dict(context.payload)
        action_id = str(context.action_id or payload.get("action_id") or payload.get("actionId") or "").strip()
        if action_id == "approval.read.analyze":
            canonical: dict[str, Any] = {"actionId": action_id, "operation": "ANALYZE"}
            for key in ("process_types", "processTypes", "sort_by", "sortBy"):
                if present(payload.get(key)):
                    canonical[key] = payload[key]
            return CompiledTaskPlan(
                plan_id=plan_id(context.capability_id, context.execution_class, canonical),
                status="RESOLVED", capability_id=context.capability_id,
                execution_class=context.execution_class,
                execution_tool="analyze_my_pending_approvals", canonical=canonical,
            )

        query = dict(context.query_intent or {})
        if not query and action_id == "approval.read.pending":
            query = {
                key: value for key, value in payload.items()
                if key not in {"action_id", "actionId", "operation", "action", "entity", "type"}
            }
            query.setdefault("entity", "pending_approval")
            query.setdefault("operation", "rank" if query.get("sort") else "list")
        if not query:
            return None
        query.setdefault("action_id", action_id or "approval.read.pending")
        resolution = canonicalize_approval_query(query)
        canonical = resolution.model_dump(mode="json")
        compiled_id = plan_id(context.capability_id, "metadata_query", canonical)
        if resolution.status == "RESOLVED" and resolution.plan is not None:
            return CompiledTaskPlan(
                plan_id=compiled_id, status="RESOLVED", capability_id=context.capability_id,
                execution_class="metadata_query", execution_tool="run_approval_query_plan",
                canonical=resolution.plan.model_dump(mode="json"),
            )
        return CompiledTaskPlan(
            plan_id=compiled_id,
            status="CLARIFY" if resolution.status == "CLARIFY" else "UNSUPPORTED",
            capability_id=context.capability_id, execution_class="metadata_query",
            canonical=canonical, issues=resolution.issues,
            clarification_question=resolution.clarification_question,
        )

    @staticmethod
    def _compile_process(context: CompileContext) -> CompiledTaskPlan:
        payload = dict(context.payload)
        operation = str(payload.get("operation") or payload.get("action") or "").strip().upper()
        operation = {
            "MY_APPLICATIONS": "APPLICATIONS", "MY_HISTORY": "HISTORY",
            "DONE": "HISTORY", "DETAIL": "APPLICATION_DETAIL",
        }.get(operation, operation)
        tools = {
            "APPLICATIONS": "list_my_approval_applications",
            "APPLICATION_DETAIL": "get_my_approval_application",
            "HISTORY": "list_my_approval_history",
            "WITHDRAW": "run_approval_write_workflow",
        }
        canonical: dict[str, Any] = {"operation": operation}
        if operation == "WITHDRAW":
            process_id = payload.get("processInstanceId") or payload.get("process_instance_id")
            reason = payload.get("reason")
            if not str(process_id or "").strip() or not str(reason or "").strip():
                return CompiledTaskPlan(
                    plan_id=plan_id(context.capability_id, context.execution_class, canonical),
                    status="CLARIFY", capability_id=context.capability_id,
                    execution_class=context.execution_class, canonical=canonical,
                    issues=["撤回审批必须指定唯一流程实例编号和撤回理由"],
                    clarification_question="请提供要撤回的流程实例编号和撤回理由。",
                )
            canonical.update({"processInstanceId": str(process_id).strip(), "reason": str(reason).strip()})
        if operation not in tools:
            return CompiledTaskPlan(
                plan_id=plan_id(context.capability_id, context.execution_class, canonical),
                status="CLARIFY", capability_id=context.capability_id,
                execution_class=context.execution_class, canonical=canonical,
                issues=["审批流程查询必须明确是我发起的流程、某条流程详情或已办历史"],
                clarification_question="请说明要查看我发起的审批、某条审批详情，还是已办审批历史。",
            )
        return CompiledTaskPlan(
            plan_id=plan_id(context.capability_id, context.execution_class, canonical),
            status="RESOLVED", capability_id=context.capability_id,
            execution_class=context.execution_class, execution_tool=tools[operation],
            canonical=canonical,
        )


class ApprovalProcessPlanCompiler(ApprovalPlanCompiler):
    capability_id = "approval_process"

    def compile(self, context: CompileContext) -> CompiledTaskPlan | None:
        return self._compile_process(context)


__all__ = ["ApprovalPlanCompiler", "ApprovalProcessPlanCompiler"]
