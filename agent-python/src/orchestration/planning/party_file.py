"""Pure plan compiler for the party-file capability."""

from __future__ import annotations

from typing import Any

from ...domain.plan import CandidateTaskPlan, CompiledTaskPlan
from ..action_validation import validate_action_payload
from ..capabilities import ACTION_SPECS, action_field_specs, resolve_action
from .common import int_or_none, plan_id, present
from .contracts import CompileContext


_WRITE_TOOLS = {
    item.operation: item.execution_tool
    for item in ACTION_SPECS
    if item.capability_id == "party_file"
    and item.execution_class == "workflow"
    and item.execution_tool
}

_OPERATION_ALIASES = {
    "PUBLISH": "CREATE",
    "DRAFT_AND_PUBLISH": "CREATE",
    "DRAFT_AND_PUBLISH_PARTY_DOCUMENT": "CREATE",
    "DRAFT_AND_RELEASE": "CREATE",
    "DRAFT_PUBLISH": "CREATE",
    "DRAFT_RELEASE": "CREATE",
    "CREATE_DRAFT": "CREATE",
    "CREATE_DOCUMENT": "CREATE",
    "CREATE_PARTY_FILE": "CREATE",
    "CREATE_PARTY_DOCUMENT": "CREATE",
    "PUBLISH_PARTY_FILE": "CREATE",
    "NEW": "CREATE",
    "NEW_PARTY_FILE": "CREATE",
    "EDIT": "UPDATE",
    "CHANGE": "UPDATE",
    "RESCHEDULE": "UPDATE",
    "UPDATE_PARTY_FILE": "UPDATE",
    "EDIT_PARTY_FILE": "UPDATE",
    "REMOVE": "DELETE",
    "DELETE_PARTY_FILE": "DELETE",
    "CONFIRM_PUBLISH": "CONFIRM",
    "CONFIRM_RELEASE": "CONFIRM",
}


def normalize_party_file_operation(value: Any) -> str:
    normalized = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    return _OPERATION_ALIASES.get(normalized, normalized)


def compile_metadata(context: CompileContext) -> CompiledTaskPlan:
    payload = dict(context.payload)
    operation = str(payload.get("operation") or payload.get("action") or "").strip().upper().replace("-", "_")
    attachment_operations = {
        "ATTACHMENT", "ATTACHMENTS", "ATTACHMENT_QUERY", "ATTACHMENT_DELIVERY",
        "DETAIL_WITH_ATTACHMENTS", "FILE_ATTACHMENTS",
    }
    if operation in attachment_operations:
        source = (
            payload.get("source_party_file_id") or payload.get("sourcePartyFileId")
            or payload.get("file_id") or payload.get("fileId")
        )
        canonical: dict[str, Any] = {"entity": "party_file", "operation": "attachment_query", "version": "1"}
        if source is not None:
            source_id = int_or_none(source)
            if source_id is None:
                return CompiledTaskPlan(
                    plan_id=plan_id(context.capability_id, context.execution_class, canonical),
                    status="CLARIFY", capability_id=context.capability_id,
                    execution_class="metadata_query", canonical=canonical,
                    issues=["党务文件编号无效"], missing_fields=["source_party_file_id"],
                    clarification_question="请先查询并选择要核对附件的党务文件。",
                )
            canonical["sourcePartyFileId"] = source_id
        if "sourcePartyFileId" not in canonical:
            return CompiledTaskPlan(
                plan_id=plan_id(context.capability_id, context.execution_class, canonical),
                status="CLARIFY", capability_id=context.capability_id,
                execution_class="metadata_query", canonical=canonical,
                issues=["核对党务文件附件必须绑定当前用户可见的来源文件"],
                missing_fields=["source_party_file_id"],
                clarification_question="请先查询并选择要核对附件的党务文件。",
            )
        canonical["action"] = str(payload.get("action") or "inspect").strip().lower() or "inspect"
        return CompiledTaskPlan(
            plan_id=plan_id(context.capability_id, context.execution_class, canonical),
            status="RESOLVED", capability_id=context.capability_id,
            execution_class="metadata_query", execution_tool="get_party_file_attachments",
            canonical=canonical,
        )

    filters = payload.get("filters") or []
    rank = payload.get("rank") or {}
    limit = payload.get("limit", 20)
    projection = payload.get("projection") or ["id", "title", "publishTime", "categoryName"]
    issues: list[str] = []
    allowed_fields = {"title", "categoryId", "categoryName", "publishTime", "readStatus"}
    allowed_operators = {"EQ", "CONTAINS", "GTE", "LTE", "GT", "LT", "NOT_NULL"}
    normalized_filters: list[dict[str, Any]] = []
    if not isinstance(filters, list):
        issues.append("filters 必须是数组")
        filters = []
    for item in filters:
        if not isinstance(item, dict):
            issues.append("文件筛选条件格式无效")
            continue
        field = str(item.get("field") or "").strip()
        operator = str(item.get("operator") or "EQ").strip().upper()
        if field not in allowed_fields:
            issues.append(f"不支持的党务文件元数据字段：{field or '<empty>'}")
            continue
        if operator not in allowed_operators:
            issues.append(f"不支持的党务文件元数据条件：{operator}")
            continue
        if operator != "NOT_NULL" and not present(item.get("value")):
            issues.append(f"条件 {field} 缺少比较值")
            continue
        normalized_filters.append({"field": field, "operator": operator, "value": item.get("value")})
    if not isinstance(rank, dict):
        issues.append("rank 必须是对象")
        rank = {}
    rank_field = str(rank.get("field") or "").strip()
    rank_mode = str(rank.get("mode") or "").strip().lower()
    normalized_rank: dict[str, Any] | None = None
    if rank:
        if rank_field not in {"publishTime", "title", "id"}:
            issues.append(f"不支持的党务文件排序字段：{rank_field or '<empty>'}")
        if rank_mode not in {"nearest", "asc", "desc"}:
            issues.append(f"不支持的党务文件排序方式：{rank_mode or '<empty>'}")
        if rank_mode == "nearest" and not str(rank.get("target") or "").strip():
            issues.append("最近时间排序缺少 target")
        normalized_rank = {"field": rank_field, "mode": rank_mode, "target": rank.get("target")}
    try:
        normalized_limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        issues.append("limit 必须是 1 到 50 之间的整数")
        normalized_limit = 20
    normalized_projection = [field for field in projection if field in allowed_fields | {"id", "summary"}]
    if not normalized_projection:
        normalized_projection = ["id", "title", "publishTime", "categoryName"]
    canonical = {
        "entity": "party_file", "operation": "metadata_query", "filters": normalized_filters,
        "rank": normalized_rank, "limit": normalized_limit, "projection": normalized_projection,
        "execution_order": ["filter", "rank", "limit", "project"],
    }
    compiled_id = plan_id(context.capability_id, context.execution_class, canonical)
    if issues:
        return CompiledTaskPlan(
            plan_id=compiled_id,
            status="UNSUPPORTED" if any("不支持" in item for item in issues) else "CLARIFY",
            capability_id=context.capability_id, execution_class=context.execution_class,
            canonical=canonical, issues=issues,
        )
    return CompiledTaskPlan(
        plan_id=compiled_id, status="RESOLVED", capability_id=context.capability_id,
        execution_class=context.execution_class, execution_tool="execute_party_file_metadata_plan",
        canonical=canonical,
    )


def compile_write(context: CompileContext) -> CompiledTaskPlan:
    payload = dict(context.payload)
    operation = normalize_party_file_operation(payload.get("operation") or payload.get("action"))
    tool = _WRITE_TOOLS.get(operation)
    canonical: dict[str, Any] = {"operation": operation, "version": "1"}
    action_id = str(payload.get("action_id") or payload.get("actionId") or f"party_file.{operation.lower()}").strip()
    action = resolve_action("party_file", action_id, operation)
    if action is not None:
        for field in action_field_specs(action):
            if present(payload.get(field.name)):
                canonical[field.name] = payload[field.name]
    if operation == "CONFIRM":
        return CompiledTaskPlan(
            plan_id=plan_id("party_file", "workflow", canonical), status="CLARIFY",
            capability_id="party_file", execution_class="workflow", canonical=canonical,
            issues=["普通文本确认不能替代党务文件 ApprovalCard"],
            clarification_question="请点击当前党务文件确认卡完成发布，不能通过普通文本直接提交。",
        )
    if operation in {"UPDATE", "DELETE"}:
        source = payload.get("source_party_file_id") or payload.get("sourcePartyFileId")
        if source is not None:
            source_id = int_or_none(source)
            if source_id is None:
                return CompiledTaskPlan(
                    plan_id=plan_id("party_file", "workflow", canonical), status="CLARIFY",
                    capability_id="party_file", execution_class="workflow", canonical=canonical,
                    issues=["来源党务文件编号无效"], missing_fields=["source_party_file_id"],
                    clarification_question="请先查询并选择要修改或删除的党务文件。",
                )
            canonical["sourcePartyFileId"] = source_id
        if "sourcePartyFileId" not in canonical:
            return CompiledTaskPlan(
                plan_id=plan_id("party_file", "workflow", canonical), status="CLARIFY",
                capability_id="party_file", execution_class="workflow", canonical=canonical,
                issues=["修改或删除党务文件必须绑定当前用户可见的来源文件"],
                missing_fields=["source_party_file_id"],
                clarification_question="请先查询并选择要修改或删除的党务文件。",
            )
    if not tool:
        return CompiledTaskPlan(
            plan_id=plan_id("party_file", "workflow", canonical), status="CLARIFY",
            capability_id="party_file", execution_class="workflow", canonical=canonical,
            issues=["党务文件写操作必须是 CREATE、UPDATE 或 DELETE"], missing_fields=["operation"],
            clarification_question="请明确要发布新文件、更新已有文件还是删除文件。",
        )
    return CompiledTaskPlan(
        plan_id=plan_id("party_file", "workflow", canonical), status="RESOLVED",
        capability_id="party_file", execution_class="workflow", execution_tool=tool,
        canonical=canonical,
    )


class PartyFilePlanCompiler:
    capability_id = "party_file"

    def compile(self, context: CompileContext) -> CompiledTaskPlan | None:
        if context.execution_class == "metadata_query":
            return compile_metadata(context)
        if context.execution_class == "workflow":
            return compile_write(context)
        return None


__all__ = ["PartyFilePlanCompiler", "compile_metadata", "compile_write", "normalize_party_file_operation"]
