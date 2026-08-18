"""Deterministic compilation of natural-language query intent.

The model supplies a CandidateQueryIntent; this module owns business-neutral
ordering, validation and ambiguity handling. It never calls an OA service.
"""

from __future__ import annotations

import re
from typing import Any

from ..domain.query_plan import (
    CandidateQueryIntent,
    CanonicalQueryPlan,
    QueryFilter,
    QuerySort,
    ResolutionResult,
)


_APPROVAL_FIELDS = {"amount", "process_type", "created_time", "department", "pending_days"}
_APPROVAL_SORT_FIELDS = {"amount", "created_time", "pending_days"}
_APPROVAL_OPERATORS = {"LT", "LTE", "EQ", "GTE", "GT", "CONTAINS", "NOT_NULL", "GTE_DAYS"}
_APPROVAL_SORT_ALIASES = {
    # Providers use natural-language ranking labels for the same business
    # meaning.  Normalize them here, after the approval domain has already
    # been selected, so this remains a schema compatibility rule rather than
    # a global keyword router.
    "createtime": "created_time",
    "create_time": "created_time",
    "createdtime": "created_time",
    "created_at": "created_time",
    "createdat": "created_time",
    # Some OA/provider payloads use the application-time label instead of
    # the public created-time field.  This is an unambiguous schema alias
    # inside the already-selected approval query domain.
    "applytime": "created_time",
    "apply_time": "created_time",
    "applicationtime": "created_time",
    "application_time": "created_time",
    "recent": "created_time",
    "latest": "created_time",
    "newest": "created_time",
    "new": "created_time",
    "pendingdays": "pending_days",
    "pending_days": "pending_days",
    "processtype": "process_type",
    "process_type": "process_type",
}


def _contradictory_filters(filters: list[QueryFilter]) -> list[str]:
    """Detect conditions that cannot describe one record.

    This is deliberately conservative: only provable contradictions are
    rejected.  More complex boolean expressions remain a domain-agent task.
    """

    issues: list[str] = []
    by_field: dict[str, list[QueryFilter]] = {}
    for item in filters:
        by_field.setdefault(item.field, []).append(item)
    for field, values in by_field.items():
        equals = [item.value for item in values if item.operator == "EQ"]
        if len({repr(value) for value in equals}) > 1:
            issues.append(f"字段 {field} 同时等于多个不同值")
        if equals and any(item.operator == "NOT_NULL" and item.value is None for item in values) and any(item.operator == "EQ" and item.value is None for item in values):
            issues.append(f"字段 {field} 同时要求为空和非空")
        lower_values = [
            (float(item.value), item.operator == "GTE")
            for item in values
            if item.operator in {"GT", "GTE"} and isinstance(item.value, (int, float))
        ]
        upper_values = [
            (float(item.value), item.operator == "LTE")
            for item in values
            if item.operator in {"LT", "LTE"} and isinstance(item.value, (int, float))
        ]
        lower = max(lower_values, default=None)
        upper = min(upper_values, default=None)
        if lower and upper and (lower[0] > upper[0] or (lower[0] == upper[0] and not (lower[1] and upper[1]))):
            issues.append(f"字段 {field} 的范围条件没有交集")
    return issues


def _contradictory_sorts(sorts: list[QuerySort]) -> list[str]:
    seen: dict[str, str] = {}
    issues: list[str] = []
    for item in sorts:
        previous = seen.setdefault(item.field, item.direction)
        if previous != item.direction:
            issues.append(f"字段 {item.field} 同时要求升序和降序")
    return issues


def _normalize_approval_intent(value: CandidateQueryIntent | dict[str, Any]) -> CandidateQueryIntent:
    """Normalize the small legacy aliases emitted by OpenAI-compatible models.

    The planner contract uses ``entity``/``operation``/``sort``.  Some
    providers still emit a typed approval query as ``{limit, order_by}``.
    Because this function is called only after the route has selected the
    approval capability, filling the approval entity here is a scoped schema
    migration—not a global keyword route or a new business decision.
    """
    if isinstance(value, CandidateQueryIntent):
        return value
    payload = dict(value or {})
    entity = str(payload.get("entity") or payload.get("type") or "").strip().lower().replace("-", "_")
    if entity in {"todo", "pending", "pending_approvals", "my_pending", "my_requests", "my_approvals"}:
        payload["entity"] = "pending_approval"
    else:
        payload.setdefault("entity", "pending_approval")
    raw_operation = str(payload.get("operation") or "").strip().lower()
    # Providers often reuse the action vocabulary (QUERY/PENDING/SEARCH)
    # inside the query envelope. Normalize those typed aliases before
    # Pydantic validation so a valid action is not rejected as an invalid
    # QueryOperation and sent into an unnecessary tool-retry loop.
    raw_operation = {
        "query": "list",
        "pending": "list",
        "search": "list",
        "list": "list",
        "filter": "filter",
        "rank": "rank",
        "analyze": "analyze",
    }.get(raw_operation, raw_operation)
    if raw_operation:
        payload["operation"] = raw_operation
    raw_order = payload.get("order_by") or payload.get("orderBy")
    raw_sort = payload.get("sort")
    if raw_order and not raw_sort:
        raw_sort = [raw_order] if isinstance(raw_order, str) else raw_order
    elif isinstance(raw_sort, str):
        # Some providers collapse the one-element sort array to a string,
        # e.g. ``{"sort": "recent"}``.  Treat it as one sort descriptor;
        # iterating the string would incorrectly produce fields ``r``, ``e``
        # and so on and send the otherwise valid query to UNSUPPORTED.
        raw_sort = [raw_sort]
    elif isinstance(raw_sort, dict):
        # A one-item object is another common provider collapse of the
        # registered sort array: {"field": "created_at", "order": "desc"}.
        raw_sort = [raw_sort]
    normalized_sort: list[dict[str, Any]] = []
    for item in raw_sort or []:
        if isinstance(item, str):
            # OpenAI-compatible providers serialize a one-item sort in
            # several equivalent forms: ``field desc``, ``field,desc`` or
            # ``field：desc``.  Normalize punctuation before parsing so a
            # provider shape cannot turn a valid pending-list query into an
            # unsupported plan.
            parts = [
                part for part in re.split(r"[\s,:，：]+", item.strip())
                if part
            ]
            field = parts[0].strip() if parts else ""
            direction = parts[1].strip().upper() if len(parts) > 1 else "DESC"
            normalized_sort.append({"field": field, "direction": direction})
        elif isinstance(item, dict):
            field = item.get("field") or item.get("name")
            direction = item.get("direction") or item.get("order") or "DESC"
            # A provider may put the complete compact descriptor in ``field``
            # while also emitting the default direction, e.g.
            # ``{"field": "applytime,desc", "direction": "DESC"}``.
            # Parse that compact descriptor at the same schema boundary.
            if isinstance(field, str):
                parts = [
                    part for part in re.split(r"[\s,:，：]+", field.strip())
                    if part
                ]
                if len(parts) > 1 and str(direction).upper() == "DESC":
                    field = parts[0]
                    direction = parts[1]
            normalized_sort.append({"field": field, "direction": str(direction).upper()})
    if normalized_sort:
        payload["sort"] = normalized_sort
        if not raw_operation:
            payload["operation"] = "rank"
    elif not raw_operation:
        payload["operation"] = "list"
    if "explicit_order" not in payload and payload.get("order"):
        payload["explicit_order"] = payload["order"]
    # Field names are also part of the typed compatibility contract.  Keep
    # canonicalizer aliases here so the execution layer never sees provider
    # spelling variants.
    for item in payload.get("sort", []) or []:
        if isinstance(item, dict):
            raw_field = str(item.get("field") or "").strip()
            normalized_field = raw_field.lower().replace("-", "_").replace(" ", "_")
            item["field"] = _APPROVAL_SORT_ALIASES.get(normalized_field, normalized_field)
    return CandidateQueryIntent.model_validate(payload)


def canonicalize_approval_query(intent: CandidateQueryIntent | dict[str, Any]) -> ResolutionResult:
    """Compile one approval intent into one stable execution plan."""
    candidate = _normalize_approval_intent(intent)
    issues: list[str] = []
    if candidate.entity not in {"pending_approval", "approval", "approval_inbox"}:
        return ResolutionResult(status="UNSUPPORTED", original_intent=candidate, issues=["当前计划不支持该业务实体"])
    if candidate.ambiguities:
        return ResolutionResult(
            status="CLARIFY",
            original_intent=candidate,
            issues=list(candidate.ambiguities),
            clarification_question="请确认审批查询的筛选范围和执行顺序。",
            alternatives=[
                {"id": "rank_all", "label": "先过滤可排序金额，再按金额排序"},
                {"id": "first_page", "label": "先按默认顺序取前 N 条，再查看其中金额"},
            ],
        )

    filters: list[QueryFilter] = []
    for item in candidate.filters:
        field = item.field.strip().lower()
        operator = item.operator.strip().upper()
        if field not in _APPROVAL_FIELDS:
            issues.append(f"不支持的审批字段：{item.field}")
            continue
        if operator not in _APPROVAL_OPERATORS:
            issues.append(f"不支持的审批条件：{item.operator}")
            continue
        if operator not in {"NOT_NULL"} and item.value in (None, ""):
            issues.append(f"条件 {field} 缺少比较值")
            continue
        filters.append(QueryFilter(field=field, operator=operator, value=item.value))

    sorts: list[QuerySort] = []
    for item in candidate.sort:
        field = item.field.strip().lower()
        if field not in _APPROVAL_SORT_FIELDS:
            issues.append(f"不支持的审批排序字段：{item.field}")
            continue
        sorts.append(QuerySort(field=field, direction=item.direction))

    issues.extend(_contradictory_filters(filters))
    issues.extend(_contradictory_sorts(sorts))
    if issues:
        return ResolutionResult(status="INVALID", original_intent=candidate, issues=issues)

    limit = candidate.limit if candidate.limit is not None else 20
    if limit < 1 or limit > 50:
        return ResolutionResult(
            status="INVALID",
            original_intent=candidate,
            issues=["返回数量必须在 1 到 50 之间"],
        )

    order = [value.strip().lower() for value in candidate.explicit_order if value.strip()]
    if order and order not in (["filter", "sort", "limit"], ["sort", "limit"], ["limit", "sort"]):
        return ResolutionResult(status="INVALID", original_intent=candidate, issues=["无法识别查询执行顺序"])

    null_policy = "NOT_APPLICABLE"
    applied: list[str] = []
    execution_order = order or ["filter", "sort", "limit"]
    if sorts and sorts[0].field == "amount":
        null_policy = "EXCLUDE"
        if execution_order == ["filter", "sort", "limit"] or not order:
            filters.insert(0, QueryFilter(field="amount", operator="NOT_NULL"))
            applied.append("金额排序前排除空金额")
        elif execution_order == ["limit", "sort"]:
            applied.append("按用户明确要求先截取再排序")
        else:
            filters.insert(0, QueryFilter(field="amount", operator="NOT_NULL"))
            applied.append("金额排序前排除空金额")

    if candidate.operation == "rank" and not sorts:
        return ResolutionResult(status="INVALID", original_intent=candidate, issues=["排序查询缺少排序字段"])

    plan = CanonicalQueryPlan(
        entity="pending_approval",
        operation=candidate.operation,
        filters=filters,
        sort=sorts,
        limit=limit,
        null_policy=null_policy,
        execution_order=execution_order,
        requested_scope={
            "operation": candidate.operation,
            "filters": [item.model_dump(mode="json") for item in filters],
            "sort": [item.model_dump(mode="json") for item in sorts],
            "limit": limit,
            "nullPolicy": null_policy,
        },
        applied_policies=applied,
    )
    return ResolutionResult(status="RESOLVED", original_intent=candidate, plan=plan)


class QueryCanonicalizer:
    """Reusable facade for callers that resolve more than one query per run.

    Domain policies are intentionally selected by the caller.  The first
    supported policy is approvals; unsupported entities are returned as an
    ``UNSUPPORTED`` result without contacting a business service.
    """

    def canonicalize(self, intent: CandidateQueryIntent | dict[str, Any]) -> ResolutionResult:
        return canonicalize_approval_query(intent)


def canonicalize_query(intent: CandidateQueryIntent | dict[str, Any]) -> ResolutionResult:
    """Functional compatibility entry point for the canonicalization layer."""

    return canonicalize_approval_query(intent)
