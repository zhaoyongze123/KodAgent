"""Approval tools for the domain boundary."""

from __future__ import annotations

from typing import Annotated, Any

from langchain.tools import InjectedToolCallId, tool
from langgraph.config import get_stream_writer

from ..common import (
    ToolResponse, bind_tool_call_id, current_agent_context, emit, java_get,
    java_post, tool_failure, tool_success,
)
from ...domain.query_plan import CanonicalQueryPlan
from ...orchestration.query_canonicalizer import canonicalize_approval_query
from .common import (
    approval_failure as _approval_failure,
    bounded_approval_page as _bounded_approval_page,
)

@tool
def list_my_pending_approvals(
    page_no: int = 1,
    page_size: int = 10,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """查询当前登录用户的待办审批，只读，不会修改审批状态。

    仅适用于用户没有提出筛选、排序、金额比较或积压条件的普通列表请求。
    一旦用户要求按金额、流程类型、部门、日期或待办时长处理，必须调用
    search_my_pending_approvals，并把条件放入结构化参数。
    """
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    tool_name = "list_my_pending_approvals"
    emit(writer, "tool_started", "🔧 正在调用待办查询工具……", toolName=tool_name, toolCallId=tool_call_id)
    try:
        requested_limit = min(50, max(1, page_size))
        result = java_get("/agent/tools/tasks/todo", {"pageNo": max(1, page_no), "pageSize": requested_limit})
    except Exception as exc:
        return _approval_failure(writer, tool_name, tool_call_id, "待办查询失败，请稍后重试", exc)
    result = _bounded_approval_page(result, requested_limit, collection_key="list")
    presentation = {"blockType": "card", "cardType": "todo"}
    emit(writer, "tool_completed", f"✅ 待办查询完成，共获取 {result.get('total', 0)} 条记录", toolName=tool_name,
         toolCallId=tool_call_id, result=result, presentation=presentation)
    return tool_success(result, presentation)


@tool
def search_my_pending_approvals(
    process_types: list[str] | None = None,
    amount_operator: str | None = None,
    amount: float | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    department: str | None = None,
    min_pending_days: int | None = None,
    sort_by: str = "CREATED_DESC",
    page_size: int = 20,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """按多个条件智能筛选当前用户的待办审批，只读。

    适用于按审批类型、金额、发起时间、发起人部门、待办时长筛选或排序。
    process_types 是流程名称或流程 key 的列表；amount_operator 只能是 LT、LTE、EQ、GTE、GT。
    min_pending_days 表示任务从创建到现在至少等待的完整天数。该工具只返回候选和排除原因，绝不通过或驳回审批。
    """
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    tool_name = "search_my_pending_approvals"
    normalized_types = [value.strip() for value in (process_types or []) if isinstance(value, str) and value.strip()]
    params: dict[str, Any] = {
        "processTypes": normalized_types or None,
        "amountOperator": amount_operator.strip().upper() if isinstance(amount_operator, str) and amount_operator.strip() else None,
        "amount": amount,
        "createdFrom": created_from.strip() if isinstance(created_from, str) and created_from.strip() else None,
        "createdTo": created_to.strip() if isinstance(created_to, str) and created_to.strip() else None,
        "department": department.strip() if isinstance(department, str) and department.strip() else None,
        "minPendingDays": min_pending_days,
        "sortBy": sort_by.strip().upper() if sort_by.strip() else "CREATED_DESC",
        "pageSize": min(50, max(1, page_size)),
    }
    params = {key: value for key, value in params.items() if value is not None}
    emit(writer, "tool_started", "🔧 正在按条件筛选待办审批……", toolName=tool_name, toolCallId=tool_call_id)
    requested_limit = min(50, max(1, page_size))
    params["pageSize"] = requested_limit
    try:
        result = java_get("/agent/tools/approvals/inbox", params)
    except Exception as exc:
        return _approval_failure(writer, tool_name, tool_call_id, "审批智能筛选失败，请稍后重试", exc)
    result = _bounded_approval_page(result, requested_limit, collection_key="candidates")
    candidate_count = len(result.get("candidates", [])) if isinstance(result, dict) else 0
    excluded_count = result.get("excludedCount", 0) if isinstance(result, dict) else 0
    presentation = {"blockType": "card", "cardType": "approval_inbox"}
    emit(writer, "tool_completed", f"✅ 已筛出 {candidate_count} 条候选待办，排除 {excluded_count} 条",
         toolName=tool_name, toolCallId=tool_call_id, result=result, presentation=presentation)
    return tool_success(result, presentation)


@tool
def run_approval_query_plan(
    plan: dict,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """Execute a previously canonicalized, read-only approval query plan.

    The model cannot choose endpoint ordering here. The plan is revalidated and
    translated to the permission-checked Java facade on every execution.
    """
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    try:
        canonical = CanonicalQueryPlan.model_validate(plan)
    except Exception as exc:
        return tool_failure("QUERY_PLAN_INVALID", "审批查询计划无效，请重新描述筛选条件。", details=str(exc))
    requested_limit = max(1, min(int(canonical.limit), 50))
    params: dict[str, Any] = {"pageNo": 1, "pageSize": requested_limit}
    for item in canonical.filters:
        if item.field == "amount" and item.operator != "NOT_NULL":
            params["amountOperator"] = item.operator
            params["amount"] = item.value
        elif item.field == "amount" and item.operator == "NOT_NULL":
            params["amountPresent"] = True
        elif item.field == "process_type":
            params["processTypes"] = item.value if isinstance(item.value, list) else [item.value]
        elif item.field == "department":
            params["department"] = item.value
        elif item.field == "pending_days":
            params["minPendingDays"] = item.value
        elif item.field == "created_time" and isinstance(item.value, dict):
            params["createdFrom"] = item.value.get("from")
            params["createdTo"] = item.value.get("to")
    if canonical.sort:
        sort = canonical.sort[0]
        sort_name = {"amount": "AMOUNT", "created_time": "CREATED", "pending_days": "PENDING_DAYS"}[sort.field]
        params["sortBy"] = f"{sort_name}_{sort.direction}"
    emit(writer, "tool_started", "🔧 正在按已确认的查询计划筛选待办审批……", toolName="run_approval_query_plan", toolCallId=tool_call_id)
    try:
        result = java_get("/agent/tools/approvals/inbox", {key: value for key, value in params.items() if value is not None})
    except Exception as exc:
        return _approval_failure(writer, "run_approval_query_plan", tool_call_id, "审批查询失败，请稍后重试", exc)
    result = _bounded_approval_page(result, requested_limit, collection_key="candidates")
    result["requestedScope"] = canonical.requested_scope
    result.setdefault("sortApplied", params.get("sortBy", "CREATED_DESC"))
    result.setdefault("nullPolicy", canonical.null_policy)
    result.setdefault("appliedPolicies", canonical.applied_policies)
    presentation = {
        "blockType": "card",
        "cardType": "approval_inbox",
        "resultKind": "ranked_list" if canonical.sort else "record_list",
        "requestedScope": canonical.requested_scope,
        "summary": {"headline": "已按确定性查询计划返回审批结果"},
    }
    emit(writer, "tool_completed", "✅ 已按查询计划完成审批筛选", toolName="run_approval_query_plan", toolCallId=tool_call_id, result=result, presentation=presentation)
    return tool_success(result, presentation)


@tool
def analyze_my_pending_approvals(
    process_types: list[str] | None = None,
    sort_by: str = "PENDING_DAYS_DESC",
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> ToolResponse:
    """分析当前用户待办审批的积压和高金额异常，只读。"""
    bind_tool_call_id(tool_call_id)
    writer = get_stream_writer()
    params: dict[str, Any] = {"sortBy": sort_by.strip().upper() if sort_by else "PENDING_DAYS_DESC"}
    if process_types:
        params["processTypes"] = [value.strip() for value in process_types if isinstance(value, str) and value.strip()]
    emit(writer, "tool_started", "🔧 正在分析审批积压和异常……", toolName="analyze_my_pending_approvals", toolCallId=tool_call_id)
    try:
        result = java_get("/agent/tools/approvals/insights", params)
    except Exception as exc:
        return _approval_failure(writer, "analyze_my_pending_approvals", tool_call_id, "审批分析失败，请稍后重试", exc)
    presentation = {"blockType": "card", "cardType": "approval_insights"}
    emit(writer, "tool_completed", result.get("summary", "审批分析完成") if isinstance(result, dict) else "✅ 审批分析完成",
         toolName="analyze_my_pending_approvals", toolCallId=tool_call_id, result=result, presentation=presentation)
    return tool_success(result, presentation)


__all__ = [
    "list_my_pending_approvals",
    "search_my_pending_approvals",
    "run_approval_query_plan",
    "analyze_my_pending_approvals",
]
