"""The single pure boundary from a candidate plan to an executable plan.

The model may propose an action and typed fields, but only this compiler can
bind that proposal to an executor. Domain-specific rules live in the bounded
compilers under :mod:`orchestration.planning`; this module owns transport
normalization, action lookup and shared validation.
"""

from __future__ import annotations

from typing import Any

from ..domain.plan import CandidateTaskPlan, CompiledTaskPlan, ExecutionClass, PlanStatus
from ..domain.query_plan import CandidateQueryIntent
from .action_validation import authorized_source_fields, validate_action_payload
from .capabilities import (
    action_field_specs,
    build_clarification_question,
    canonicalize_read_action_scope,
    canonical_capability_id,
    resolve_action,
    resolve_typed_read_action,
)
from .planning.approval import ApprovalPlanCompiler, ApprovalProcessPlanCompiler
from .planning.common import plan_id
from .planning.contracts import CompileContext
from .planning.normalization import normalize_action_payload
from .planning.party_file import PartyFilePlanCompiler, normalize_party_file_operation
from .planning.registry import build_plan_compiler_registry
from .planning.resources import ResourcePlanCompiler, infer_workflow_capability
from .planning.reports import ReportPlanCompiler


_REGISTRY = build_plan_compiler_registry()


def _clarification_canonical(action: Any, payload: dict[str, Any], validation: Any) -> dict[str, Any]:
    """Keep only reusable, schema-owned facts while awaiting user input.

    A ``CLARIFY`` plan is persisted as a ``PendingPlan`` and merged with the
    user's next patch.  Retaining only the action id used to discard fields
    that had already passed validation (for example a meeting's time range),
    forcing the user to repeat them on every clarification turn.

    Do not turn this continuation store into a backdoor for executor options
    or untrusted record IDs: it contains declared action fields only.  A
    source field governed by ``authorized_query_fact`` survives only when the
    route boundary has already marked that exact field as authorized.
    """
    canonical: dict[str, Any] = {
        "action_id": action.action_id,
        "operation": action.operation,
        "version": "1",
    }
    authorized = authorized_source_fields(payload)
    invalid = set(getattr(validation, "invalid_fields", ()) or ())

    for field in action_field_specs(action):
        name = field.name
        if name not in payload:
            continue
        value = payload[name]
        # Empty values convey no reusable fact.  Keep ``False`` and ``0`` --
        # both are meaningful values for declared boolean/integer fields.
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if isinstance(value, (list, dict)) and not value:
            continue
        if field.source_policy == "authorized_query_fact" and name not in authorized:
            continue
        # Direct field validation failures (type/enum/bounds) cannot be
        # reused. Composite relationship issues deliberately do not erase
        # their individual values: a follow-up patch can correct only one end
        # of an interval while retaining the other.
        if name in invalid or any(issue.startswith(f"{name}(") for issue in invalid):
            continue
        canonical[name] = value

    authorized_retained = [
        field.name
        for field in action_field_specs(action)
        if field.source_policy == "authorized_query_fact" and field.name in canonical
    ]
    if authorized_retained:
        canonical["_authorized_source_fields"] = authorized_retained
    return canonical


def _resolved_action(
    capability: str,
    execution_class: str,
    candidate_payload: dict[str, Any],
    query_intent: dict[str, Any],
) -> tuple[Any | None, str | None, CompiledTaskPlan | None]:
    proposed_action_id = str(
        candidate_payload.get("action_id") or candidate_payload.get("actionId")
        or query_intent.get("action_id") or query_intent.get("actionId") or ""
    ).strip()
    proposed_operation = str(
        candidate_payload.get("operation") or candidate_payload.get("action")
        or query_intent.get("operation") or query_intent.get("action") or ""
    ).strip()
    action = resolve_action(capability, proposed_action_id, proposed_operation)
    if proposed_operation and not proposed_action_id and action is None:
        canonical = {"operation": proposed_operation, "version": "1"}
        return None, None, CompiledTaskPlan(
            plan_id=plan_id(capability or "general_agent", execution_class or "clarify", canonical),
            status="CLARIFY", capability_id=capability or "general_agent",
            execution_class=execution_class or "clarify", canonical=canonical,
            issues=["operation 未能唯一解析为当前领域的已注册 action_id"],
            missing_fields=["action_id"],
            clarification_question="请从当前领域动作目录中选择具体 action_id 后继续。",
        )
    if proposed_action_id and action is None:
        canonical = {"actionId": proposed_action_id, "operation": proposed_operation}
        return None, None, CompiledTaskPlan(
            plan_id=plan_id(capability or "general_agent", execution_class or "clarify", canonical),
            status="UNSUPPORTED", capability_id=capability or "general_agent",
            execution_class=execution_class or "clarify", canonical=canonical,
            issues=[f"未注册的业务动作：{proposed_action_id}"],
            clarification_question="当前业务动作未注册，请从当前领域支持的动作中选择。",
        )
    if action is None:
        return None, None, None
    if not action.execution_tool:
        canonical = {
            "actionId": action.action_id, "operation": action.operation,
            "version": "1", "errorCode": "ACTION_EXECUTOR_BINDING_MISSING",
        }
        return None, None, CompiledTaskPlan(
            plan_id=plan_id(capability or action.capability_id, action.execution_class, canonical),
            status="UNSUPPORTED", capability_id=capability or action.capability_id,
            execution_class=action.execution_class, canonical=canonical,
            issues=[f"业务动作 {action.action_id} 已由 Java 注册，但当前 Agent 尚未绑定执行器"],
            clarification_question="当前业务动作已登记但尚未接入执行能力，请联系管理员完成执行器绑定。",
        )
    return action, proposed_action_id or action.action_id, None


def compile_task_plan(
    *,
    capability_id: str | None,
    execution_class: str | None,
    candidate_plan: dict[str, Any] | None = None,
    query_intent: dict[str, Any] | None = None,
) -> CompiledTaskPlan | None:
    """Compile a model proposal without models, I/O or business side effects."""
    capability = canonical_capability_id(capability_id)
    proposed_class = str(execution_class or "").strip() or "clarify"
    payload = dict(candidate_plan) if isinstance(candidate_plan, dict) else {}
    intent = dict(query_intent) if isinstance(query_intent, dict) else {}

    # Query intent is a typed part of the same plan envelope. Merge it before
    # action resolution so metadata-only calls that carry the action or
    # operation in candidate_plan still retain legal fields such as a date or
    # start/end interval in the resource compiler payload.
    for key, value in intent.items():
        if key not in {"action_id", "actionId", "operation", "action", "entity", "type"}:
            payload.setdefault(key, value)

    # A metadata query may carry its typed fields in query_intent while the
    # provider leaves action_id out and keeps only operation=QUERY in the
    # candidate envelope. Recover an action only through the catalog's unique
    # read-only schema; this boundary can never infer a write action or an
    # executor from an operation verb.
    if not (
        payload.get("action_id")
        or payload.get("actionId")
        or intent.get("action_id")
        or intent.get("actionId")
    ):
        typed_read_action = resolve_typed_read_action(
            capability,
            proposed_class,
            candidate_plan=payload,
            query_intent=intent,
        )
        if typed_read_action is not None:
            payload["action_id"] = typed_read_action.action_id
            payload.setdefault("operation", typed_read_action.operation)

    action, action_id, early = _resolved_action(capability, proposed_class, payload, intent)
    if early is not None:
        return early
    if action is not None:
        payload = normalize_action_payload(action, payload)
        payload.setdefault("action_id", action.action_id)
        payload.setdefault("operation", action.operation)
        proposed_class = action.execution_class
        payload, intent, scope_issue = canonicalize_read_action_scope(action, payload, intent)
        if scope_issue:
            canonical = {
                "action_id": action.action_id,
                "operation": action.operation,
                "version": "1",
            }
            return CompiledTaskPlan(
                plan_id=plan_id(capability or action.capability_id, proposed_class, canonical),
                status="CLARIFY", capability_id=capability or action.capability_id,
                execution_class=proposed_class, canonical=canonical,
                issues=[scope_issue], missing_fields=["scope"],
                clarification_question="请确认是待办审批、我发起的审批、已办历史，还是当前领域对应的查询对象。",
            )
        if action.capability_id == "approval_read" and action.action_id == "approval.read.pending" and not intent:
            intent = {
                key: value for key, value in payload.items()
                if key not in {"action_id", "actionId", "operation", "action", "entity", "type"}
            }
            intent.setdefault("entity", "pending_approval")
            intent.setdefault("operation", "rank" if intent.get("sort") else "list")
        if not (action.capability_id == "approval_read" and intent):
            validation = validate_action_payload(
                action, payload, authorized_source_fields=authorized_source_fields(payload)
            )
            if not validation.ok:
                canonical = _clarification_canonical(action, payload, validation)
                return CompiledTaskPlan(
                    plan_id=plan_id(capability or action.capability_id, proposed_class, canonical),
                    status="CLARIFY", capability_id=capability or action.capability_id,
                    execution_class=proposed_class, canonical=canonical,
                    issues=validation.issues, missing_fields=validation.missing_fields,
                    clarification_question=build_clarification_question(
                        validation.missing_fields, action,
                        invalid_fields=validation.invalid_fields,
                    ),
                )
    context = CompileContext(
        capability_id=capability, execution_class=proposed_class,
        payload=payload, query_intent=intent or None, action_id=action_id,
    )
    compiled = _REGISTRY.compile(context)
    if compiled is not None:
        # Every compiled plan must carry the catalog action that produced it.
        # Domain compilers are responsible for business normalization, but
        # this shared boundary owns the stable action identity consumed by
        # routing traces, audit records, and executor projection.  Without
        # this invariant a recovery path can execute the right tool while
        # reporting an empty action_id.
        if action is not None:
            canonical = dict(compiled.canonical or {})
            canonical.setdefault("action_id", action.action_id)
            compiled = compiled.model_copy(update={"canonical": canonical})
        return compiled
    if proposed_class in {"content_search", "document_understanding", "document_compare", "compliance_check", "workflow"}:
        return CompiledTaskPlan(
            plan_id=plan_id(capability or "general_agent", proposed_class, payload),
            status="FALLBACK", capability_id=capability or "general_agent",
            execution_class=proposed_class, issues=["该计划类型继续使用现有 Workflow 或领域 ReAct 执行器"],
        )
    return None


class PlanCompiler:
    """Small object boundary for dependency injection and future variants."""

    def compile(self, **kwargs: Any) -> CompiledTaskPlan | None:
        return compile_task_plan(**kwargs)


plan_compiler = PlanCompiler()


def compile_plan(**kwargs: Any) -> CompiledTaskPlan | None:
    """Stable public function used by route tools and executor projection."""
    return plan_compiler.compile(**kwargs)


__all__ = [
    "CandidateQueryIntent", "CandidateTaskPlan", "CompiledTaskPlan", "ExecutionClass", "PlanStatus",
    "ApprovalPlanCompiler", "ApprovalProcessPlanCompiler", "PartyFilePlanCompiler",
    "ResourcePlanCompiler", "ReportPlanCompiler", "PlanCompiler", "compile_plan",
    "compile_task_plan", "infer_workflow_capability", "normalize_party_file_operation",
]
