"""Capability catalog used for semantic orchestration.

This catalog describes execution boundaries; it deliberately contains no
keyword-to-route rules. The model selects a capability from these contracts,
then the selected tool or sub-agent validates whether the requested fields
are actually supported.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from ..domain.conversation import RouteStrategy
from .action_catalog_runtime import runtime_action, runtime_action_catalog


APPROVAL_PROCESS_CAPABILITY_ID = "approval_process"


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    execution_boundary: str
    fallback: str
    allowed_strategies: tuple[RouteStrategy, ...] = ("direct", "delegate", "clarify")
    delegate_agent: str | None = None
    direct_tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionFieldSpec:
    """Machine-readable field contract shared by the planner and Java Facade."""

    name: str
    field_type: str = "any"
    required: bool = False
    nullable: bool = True
    description: str = ""
    source_policy: str = "user_input"
    format: str | None = None
    enum: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActionSpec:
    """A registered business action inside a domain capability.

    The model may propose ``action_id`` and business arguments, but it never
    chooses a Python tool or Java path.  The compiler resolves this registry
    entry to the only executor that can run the action.
    """

    action_id: str
    capability_id: str
    description: str
    execution_class: str
    operation: str
    aliases: tuple[str, ...] = ()
    read_only: bool = True
    requires_confirmation: bool = False
    execution_tool: str | None = None
    required_fields: tuple[str, ...] = ()
    permission: str = "agent:read"


CAPABILITIES = (
    Capability(
        "approval_read",
        "读取、筛选、排序和分析当前用户有权限的待办审批；筛选字段由工具 schema 决定，不能猜测未返回的字段。",
        "结构化筛选、排序和分页必须由确定性查询计划宏工具执行；普通列表和未覆盖分析可回退到审批子 Agent。",
        "如果请求涉及工具 schema 未表达的条件，委派 approvals_agent 读取详情或明确说明缺少字段。",
        delegate_agent="approvals_agent",
        direct_tools=("run_approval_query_plan",),
    ),
    Capability(
        "approval_write",
        "预览并处理当前用户待办的单条或批量通过、驳回。",
        "所有可发起审批模板都必须先生成持久化草稿，再由官方 ApprovalCard 确认；请假/出差使用固定表单工具，其他模板使用模板字段白名单；待办通过/驳回仍走审批任务专用预览和确认边界。",
        "字段、流程状态或权限不满足时返回结构化业务错误，禁止降级为直接 BPM 写入。",
        allowed_strategies=("delegate", "clarify"),
        delegate_agent="approvals_agent",
    ),
    Capability(
        APPROVAL_PROCESS_CAPABILITY_ID,
        "查询我发起的流程、已办历史，或撤回本人仍在运行中的审批流程。",
        "查询走 Java BPM Facade；撤回先生成撤回草稿并通过官方 ApprovalCard，再由 Java 按发起人和流程状态执行。",
        "缺少唯一流程编号或撤回理由时先澄清；不能撤回时返回真实业务错误，不伪造成功。",
        allowed_strategies=("direct", "delegate", "clarify"),
        delegate_agent="approvals_agent",
        direct_tools=("list_my_approval_applications", "get_my_approval_application", "list_my_approval_history", "create_approval_withdraw_draft", "confirm_approval_withdraw_action"),
    ),
    Capability(
        "meeting",
        "查询会议资源、协调参会人和预约会议室。",
        "会议预约优先使用确定性工作流，实体和冲突由业务工具校验。",
        "缺少参数或存在歧义时请求补充，不猜测人员或会议室。",
        # The parent only becomes a direct executor after compiler.py has
        # resolved a registered, enabled workflow operation.  Everything
        # else stays with the domain ReAct child.
        allowed_strategies=("delegate", "clarify"),
        delegate_agent="meeting_rooms_agent",
    ),
    Capability(
        "schedule",
        "查询、协调和维护个人日程。",
        "日程写操作使用草稿和确认流程，查询使用只读工具。",
        "无法表达的跨日程任务交给 schedules_agent。",
        # CREATE/UPDATE/CANCEL become direct only when a matching workflow
        # contract is enabled. Calendar queries and all other requests remain
        # available through the schedule child.
        allowed_strategies=("delegate", "clarify"),
        delegate_agent="schedules_agent",
        direct_tools=("get_my_calendar",),
    ),
    Capability(
        "party_file",
        "查询、理解、比较当前用户有权限的党务文件，核对已有附件，并在确认卡后创建、发布、更新或删除文件。",
        "元数据筛选/排序和已有附件核对使用 metadata_query Plan；附件预览/下载只返回 Java 授权的入口，不传二进制给模型；正文、条款和制度解释才使用 content_search 或文件工作流；写操作必须先生成 Java 持久草稿，再由对应操作的 HITL 确认工具提交。所有结果必须经过 Java 权限、版本和幂等边界。",
        "没有匹配文件、必要字段或权限时返回真实业务结果，不编造文件内容，也不把草稿说成已发布。",
        delegate_agent="party_files_agent",
        direct_tools=("create_party_file_draft", "confirm_create_party_file", "confirm_update_party_file", "confirm_delete_party_file"),
    ),
    Capability(
        "reporting",
        "对审批、会议、个人日程和当前用户可见党务文件做只读汇总和分布分析。",
        "时间范围、权限和聚合由 Java Facade 确定性执行；Agent 只选择报表域并补齐时间范围。",
        "缺少时间范围时请求开始和结束时间，不把原始记录交给模型自行统计。",
        allowed_strategies=("direct", "clarify", "delegate"),
        delegate_agent="general_agent",
        direct_tools=("approval_report", "meeting_report", "schedule_report", "party_file_report"),
    ),
)


# This is the single action catalog used by the planner prompt, runtime
# validation and executor selection.  Keep aliases here instead of adding
# another operation enum to a Prompt or a regex table.
ACTION_SPECS = (
    ActionSpec(
        "approval.read.pending", "approval_read", "查询、筛选和排序当前用户待办审批",
        "metadata_query", "PENDING", ("LIST", "SEARCH", "QUERY"), True, False,
        "run_approval_query_plan", (),
    ),
    ActionSpec(
        "approval.read.analyze", "approval_read", "分析当前用户待办审批",
        "metadata_query", "ANALYZE", ("INSIGHTS",), True, False,
        "analyze_my_pending_approvals", (),
    ),
    ActionSpec(
        "approval.process.applications", APPROVAL_PROCESS_CAPABILITY_ID, "查询我发起的审批",
        "approval_query", "APPLICATIONS", ("MY_APPLICATIONS",), True, False,
        "list_my_approval_applications",
    ),
    ActionSpec(
        "approval.process.application_detail", APPROVAL_PROCESS_CAPABILITY_ID, "查询某条我发起的审批详情",
        "approval_query", "APPLICATION_DETAIL", ("DETAIL",), True, False,
        "get_my_approval_application", ("processInstanceId",),
    ),
    ActionSpec(
        "approval.process.history", APPROVAL_PROCESS_CAPABILITY_ID, "查询已办审批历史",
        "approval_query", "HISTORY", ("MY_HISTORY", "DONE"), True, False,
        "list_my_approval_history",
    ),
    ActionSpec(
        "approval.process.withdraw", APPROVAL_PROCESS_CAPABILITY_ID, "撤回本人仍在运行中的审批",
        "approval_query", "WITHDRAW", ("CANCEL",), False, True,
        "create_approval_withdraw_draft", ("processInstanceId", "reason"),
    ),
    ActionSpec(
        "approval.write.request", "approval_write", "发起审批申请草稿",
        "workflow", "CREATE", ("START", "SUBMIT"), False, True,
        "create_generic_approval_request_draft",
        ("process_definition",),
    ),
    ActionSpec(
        "approval.write.task", "approval_write", "处理单条待办审批",
        "workflow", "TASK_ACTION", ("APPROVE", "REJECT"), False, True,
        "preview_approval_task_action", ("taskId", "action", "reason"), "approval:write",
    ),
    ActionSpec(
        "approval.write.batch", "approval_write", "批量处理待办审批",
        "workflow", "BATCH_ACTION", ("BATCH", "BATCH_APPROVE", "BATCH_REJECT"), False, True,
        "preview_approval_batch_action", ("taskIds", "action", "reason"), "approval:write",
    ),
    ActionSpec(
        "meeting.query", "meeting", "查询会议室预约和可用资源",
        "metadata_query", "QUERY", ("LIST", "SEARCH"), True, False,
        "list_my_meeting_bookings", (),
    ),
    ActionSpec(
        "meeting.create", "meeting", "创建会议室预约草稿",
        "workflow", "BOOK", ("CREATE", "CREATE_DRAFT", "BOOKING"), False, True,
        "run_meeting_booking_workflow", ("subject", "start_time", "end_time"),
    ),
    ActionSpec(
        "meeting.update", "meeting", "修改已有会议室预约",
        "workflow", "UPDATE", ("EDIT", "RESCHEDULE", "CHANGE"), False, True,
        "run_meeting_booking_workflow", ("source_booking_id",),
    ),
    ActionSpec(
        "meeting.cancel", "meeting", "取消已有会议室预约",
        "workflow", "CANCEL", ("DELETE", "CANCEL_BOOKING"), False, True,
        "run_meeting_booking_workflow", ("source_booking_id",),
    ),
    ActionSpec(
        "schedule.query", "schedule", "查询个人日程",
        "metadata_query", "QUERY", ("LIST", "SEARCH", "CALENDAR"), True, False,
        "get_my_calendar", (),
    ),
    ActionSpec(
        "schedule.create", "schedule", "创建个人日程草稿",
        "workflow", "CREATE", ("CREATE_DRAFT", "NEW"), False, True,
        "run_personal_schedule_workflow", ("title", "start_time", "end_time"),
    ),
    ActionSpec(
        "schedule.update", "schedule", "修改个人日程",
        "workflow", "UPDATE", ("EDIT",), False, True,
        "run_personal_schedule_workflow", ("source_schedule_id",),
    ),
    ActionSpec(
        "schedule.cancel", "schedule", "取消个人日程",
        "workflow", "CANCEL", ("DELETE",), False, True,
        "run_personal_schedule_workflow", ("source_schedule_id",),
    ),
    ActionSpec(
        "party_file.metadata", "party_file", "按标题、分类、发布时间等查询党务文件",
        "metadata_query", "METADATA_QUERY", ("LIST", "SEARCH", "QUERY"), True, False,
        "execute_party_file_metadata_plan", ("filters", "rank", "limit", "projection"),
    ),
    ActionSpec(
        "party_file.content", "party_file", "检索党务文件正文和条款",
        "content_search", "CONTENT_SEARCH", ("CONTENT", "UNDERSTAND"), True, False,
        "search_party_knowledge", ("query",),
    ),
    ActionSpec(
        "party_file.compare", "party_file", "比较党务文件版本",
        "document_compare", "COMPARE", ("DIFF",), True, False,
        "run_party_file_compare", ("left_file_id", "right_file_id"),
    ),
    ActionSpec(
        "party_file.compliance", "party_file", "按制度校验审批材料",
        "compliance_check", "COMPLIANCE_CHECK", ("CHECK",), True, False,
        "check_approval_against_party_file", ("task_id", "file_id"),
    ),
    ActionSpec(
        "party_file.attachments", "party_file", "查询党务文件附件",
        "metadata_query", "ATTACHMENTS", ("ATTACHMENT", "ATTACHMENT_QUERY", "ATTACHMENT_DELIVERY"), True, False,
        "get_party_file_attachments", ("source_party_file_id",),
    ),
    ActionSpec(
        "party_file.create", "party_file", "创建或发布党务文件草稿",
        "workflow", "CREATE", ("DRAFT", "PUBLISH"), False, True,
        "create_party_file_draft", ("title", "content", "category_name"),
    ),
    ActionSpec(
        "party_file.update", "party_file", "修改党务文件草稿",
        "workflow", "UPDATE", ("EDIT",), False, True,
        "update_party_file_draft", ("source_party_file_id",),
    ),
    ActionSpec(
        "party_file.delete", "party_file", "删除或作废党务文件草稿",
        "workflow", "DELETE", ("REMOVE", "VOID", "CANCEL"), False, True,
        "delete_party_file_draft", ("source_party_file_id",),
    ),
    ActionSpec(
        "reporting.approval", "reporting", "生成审批报表",
        "report", "APPROVAL", (), True, False, "approval_report",
    ),
    ActionSpec(
        "reporting.meeting", "reporting", "生成会议报表",
        "report", "MEETING", (), True, False, "meeting_report",
    ),
    ActionSpec(
        "reporting.schedule", "reporting", "生成日程报表",
        "report", "SCHEDULE", (), True, False, "schedule_report",
    ),
    ActionSpec(
        "reporting.party_file", "reporting", "生成党务文件报表",
        "report", "PARTY_FILE", (), True, False, "party_file_report",
    ),
)

_ACTION_MAP = {item.action_id: item for item in ACTION_SPECS}


def _field(name: str, field_type: str = "any", *, required: bool = False,
           nullable: bool | None = None, description: str = "",
           source_policy: str = "user_input", format: str | None = None,
           enum: tuple[str, ...] = ()) -> ActionFieldSpec:
    return ActionFieldSpec(
        name=name,
        field_type=field_type,
        required=required,
        nullable=(not required) if nullable is None else nullable,
        description=description,
        source_policy=source_policy,
        format=format,
        enum=enum,
    )


# Local copies are used for offline/unit validation.  In a configured Run the
# Java catalog is synchronized before the first model call and is the
# authority for drift detection; these definitions keep local tooling useful
# when the OA service is intentionally unavailable.
_ACTION_FIELD_SPECS: dict[str, tuple[ActionFieldSpec, ...]] = {
    "approval.read.pending": (
        _field("filters", "array", description="待办筛选条件"),
        _field("sort", "object", description="排序条件"),
        _field("limit", "integer", description="返回条数"),
    ),
    "approval.process.application_detail": (_field("processInstanceId", "string", required=True),),
    "approval.process.withdraw": (
        _field("processInstanceId", "string", required=True),
        _field("reason", "string", required=True),
    ),
    "approval.write.task": (
        _field("taskId", "string", required=True, source_policy="authorized_query_fact"),
        _field("action", "string", required=True, enum=("APPROVE", "REJECT")),
        _field("reason", "string"),
    ),
    "approval.write.request": (
        _field("process_definition", "string", required=True),
        _field("variables", "object"),
        _field("start_user_select_assignees", "object"),
    ),
    "approval.write.batch": (
        _field("taskIds", "array", required=True, source_policy="authorized_query_fact"),
        _field("action", "string", required=True, enum=("APPROVE", "REJECT")),
        _field("reason", "string"),
    ),
    "meeting.create": (
        _field("subject", "string", required=True),
        _field("start_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
        _field("end_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
        _field("attendees", "array"),
        _field("room_preference", "string"),
        _field("equipment", "array"),
        _field("room_capacity", "integer"),
        _field("remark", "string"),
    ),
    "meeting.update": (_field("source_booking_id", "integer", required=True, source_policy="authorized_query_fact"),
                        _field("start_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
                        _field("end_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
                        _field("subject", "string"),
                        _field("attendees", "array"),
                        _field("room_preference", "string"),
                        _field("equipment", "array"),
                        _field("room_capacity", "integer"),
                        _field("remark", "string")),
    "meeting.cancel": (_field("source_booking_id", "integer", required=True, source_policy="authorized_query_fact"),
                        _field("reason", "string")),
    "schedule.query": (_field("date", "date", format="yyyy-MM-dd"),
                        _field("start_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
                        _field("end_time", "datetime", format="yyyy-MM-dd HH:mm:ss")),
    "schedule.create": (_field("title", "string", required=True),
                         _field("start_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
                         _field("end_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
                         _field("description", "string"), _field("location", "string"),
                         _field("attendees", "array"), _field("other_participants", "string")),
    "schedule.update": (_field("source_schedule_id", "integer", required=True, source_policy="authorized_query_fact"),
                         _field("title", "string"), _field("start_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
                         _field("end_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
                         _field("description", "string"), _field("location", "string"),
                         _field("attendees", "array"), _field("other_participants", "string")),
    "schedule.cancel": (_field("source_schedule_id", "integer", required=True, source_policy="authorized_query_fact"),
                         _field("reason", "string")),
    "party_file.attachments": (_field("source_party_file_id", "integer", required=True, source_policy="authorized_query_fact"),),
    "party_file.metadata": (
        _field("filters", "array"), _field("rank", "object"),
        _field("limit", "integer"), _field("projection", "array"),
    ),
    "party_file.content": (
        _field("query", "string", required=True), _field("top_k", "integer"),
        _field("origin", "string"), _field("doc_type", "string"),
    ),
    "party_file.compare": (
        _field("left_file_id", "integer", required=True, source_policy="authorized_query_fact"),
        _field("right_file_id", "integer", required=True, source_policy="authorized_query_fact"),
    ),
    "party_file.compliance": (
        _field("task_id", "string", required=True, source_policy="authorized_query_fact"),
        _field("file_id", "integer", required=True, source_policy="authorized_query_fact"),
    ),
    "party_file.create": (_field("title", "string", required=True), _field("content", "string", required=True),
                           _field("category_name", "string"), _field("summary", "string"),
                           _field("publish_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
                           _field("targets", "array"), _field("distribute_to_self", "boolean"),
                           _field("attachment_file_ids", "array")),
    "party_file.update": (_field("source_party_file_id", "integer", required=True, source_policy="authorized_query_fact"),
                           _field("title", "string"), _field("content", "string"), _field("category_name", "string"),
                           _field("summary", "string"), _field("attachment_file_ids", "array")),
    "party_file.delete": (_field("source_party_file_id", "integer", required=True, source_policy="authorized_query_fact"),
                           _field("reason", "string")),
    # Reporting actions are still deterministic read-only calls.  The
    # explicit range fields prevent the planner from asking a backend report
    # tool to aggregate an unbounded dataset.
    "reporting.approval": (
        _field("process_types", "array"),
        _field("amount_operator", "string", enum=("LT", "LTE", "EQ", "GTE", "GT")),
        _field("amount", "number"),
        _field("created_from", "date", format="yyyy-MM-dd"),
        _field("created_to", "date", format="yyyy-MM-dd"),
        _field("department", "string"),
        _field("min_pending_days", "integer"),
        _field("sort_by", "string", enum=("CREATED_DESC", "CREATED_ASC", "AMOUNT_DESC", "AMOUNT_ASC", "PENDING_DAYS_DESC")),
    ),
    "reporting.meeting": (
        _field("start_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
        _field("end_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
    ),
    "reporting.schedule": (
        _field("start_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
        _field("end_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
    ),
    "reporting.party_file": (
        _field("start_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
        _field("end_time", "datetime", required=True, format="yyyy-MM-dd HH:mm:ss"),
    ),
}

# Portable cross-field constraints.  Java publishes the same declarations in
# the live action catalog; these copies keep offline/unit validation useful
# when the OA facade is intentionally unavailable.  They describe structural
# input relationships only, not authorization, conflict or persistence rules.
_ACTION_CONSTRAINTS: dict[str, tuple[dict[str, object], ...]] = {
    "meeting.create": ({"type": "interval", "start": "start_time", "end": "end_time"},),
    "meeting.update": (
        {"type": "interval", "start": "start_time", "end": "end_time"},
        {"type": "at_least_one", "fields": ["start_time", "end_time", "subject", "attendees", "room_preference", "equipment", "room_capacity", "remark"]},
    ),
    "schedule.create": ({"type": "interval", "start": "start_time", "end": "end_time"},),
    "schedule.update": (
        {"type": "interval", "start": "start_time", "end": "end_time"},
        {"type": "at_least_one", "fields": ["title", "start_time", "end_time", "description", "location", "attendees", "other_participants"]},
    ),
    "reporting.meeting": ({"type": "interval", "start": "start_time", "end": "end_time"},),
    "reporting.schedule": ({"type": "interval", "start": "start_time", "end": "end_time"},),
    "reporting.party_file": ({"type": "interval", "start": "start_time", "end": "end_time"},),
    "schedule.query": (
        {"type": "exclusive_groups", "groups": [["date"], ["start_time", "end_time"]]},
    ),
    "approval.write.batch": ({"type": "non_empty_unique", "field": "taskIds"},),
    "party_file.create": (
        {"type": "non_empty_if_present", "field": "targets"},
        {"type": "non_empty_if_present", "field": "attachment_file_ids"},
    ),
    "reporting.approval": (
        {"type": "paired", "fields": ["created_from", "created_to"]},
        {"type": "requires_if_present", "field": "amount", "requires": ["amount_operator"]},
        {"type": "requires_if_present", "field": "amount_operator", "requires": ["amount"]},
    ),
}


def action_field_specs(
    action: ActionSpec | str, *, use_runtime: bool = True
) -> tuple[ActionFieldSpec, ...]:
    action_id = action.action_id if isinstance(action, ActionSpec) else str(action)
    remote = runtime_action(action_id) if use_runtime else None
    if isinstance(remote, dict) and isinstance(remote.get("fields"), list):
        return tuple(
            ActionFieldSpec(
                name=str(field.get("name") or ""),
                field_type=str(field.get("type") or "any"),
                required=bool(field.get("required", False)),
                nullable=bool(field.get("nullable", not field.get("required", False))),
                description=str(field.get("description") or ""),
                source_policy=str(field.get("sourcePolicy") or "user_input"),
                format=field.get("format"),
                enum=tuple(str(value) for value in (field.get("enum") or ())),
            )
            for field in remote["fields"]
            if isinstance(field, dict) and str(field.get("name") or "").strip()
        )
    return _ACTION_FIELD_SPECS.get(action_id, ())


def action_required_fields(action: ActionSpec | str, *, use_runtime: bool = True) -> tuple[str, ...]:
    """Return the contract's declared requiredFields for one action.

    Java publishes both ``fields[].required`` and ``requiredFields``.  The
    synchronizer rejects disagreement; this helper makes the declared list
    available to every planner/presentation boundary instead of having each
    caller independently re-derive it.
    """
    action_id = action.action_id if isinstance(action, ActionSpec) else str(action)
    remote = runtime_action(action_id) if use_runtime else None
    if isinstance(remote, dict) and isinstance(remote.get("requiredFields"), list):
        return tuple(str(value) for value in remote["requiredFields"] if str(value).strip())
    return tuple(field.name for field in action_field_specs(action, use_runtime=use_runtime) if field.required)


def action_constraints(
    action: ActionSpec | str, *, use_runtime: bool = True
) -> tuple[dict[str, object], ...]:
    """Return the Java-owned structural constraints for an action.

    Runtime catalog values are copied before use so a provider response or a
    caller cannot mutate the per-run contract held in the ContextVar.
    """
    action_id = action.action_id if isinstance(action, ActionSpec) else str(action)
    remote = runtime_action(action_id) if use_runtime else None
    values = remote.get("constraints") if isinstance(remote, dict) else None
    if not isinstance(values, list):
        values = _ACTION_CONSTRAINTS.get(action_id, ())
    return tuple(dict(value) for value in values if isinstance(value, dict))


def action_description(action: ActionSpec) -> str:
    remote = runtime_action(action.action_id)
    return str(remote.get("description") or "") if remote else action.description


def action_execution_class(action: ActionSpec) -> str:
    remote = runtime_action(action.action_id)
    return str(remote.get("executionClass") or "") if remote else action.execution_class


def action_read_only(action: ActionSpec) -> bool:
    remote = runtime_action(action.action_id)
    return bool(remote.get("readOnly", action.read_only)) if remote else action.read_only


def action_requires_confirmation(action: ActionSpec) -> bool:
    remote = runtime_action(action.action_id)
    return bool(remote.get("requiresConfirmation", action.requires_confirmation)) if remote else action.requires_confirmation


def action_operation(action: ActionSpec) -> str:
    remote = runtime_action(action.action_id)
    return str(remote.get("operation") or "") if remote else action.operation


def _runtime_action_spec(item: dict[str, object]) -> ActionSpec:
    """Project one Java action into the planner model without inventing a tool.

    Java owns the public action contract.  Python contributes only the local
    executor binding and legacy aliases for an action it explicitly knows how
    to run.  A Java-only action is still visible to the model and plan
    compiler, but its ``execution_tool`` remains ``None`` so dispatch can
    return a structured binding error instead of guessing a tool.
    """
    action_id = str(item.get("actionId") or "").strip()
    local = _ACTION_MAP.get(action_id)
    execution_class = str(item.get("executionClass") or (local.execution_class if local else "clarify"))
    if execution_class not in {
        "metadata_query", "approval_query", "content_search", "document_understanding",
        "document_compare", "compliance_check", "report", "workflow", "fallback_react", "clarify",
    }:
        execution_class = "clarify"
    return ActionSpec(
        action_id=action_id,
        capability_id=str(item.get("capabilityId") or "").strip(),
        description=str(item.get("description") or (local.description if local else "")),
        execution_class=execution_class,
        operation=str(item.get("operation") or (local.operation if local else "")),
        aliases=local.aliases if local else (),
        read_only=bool(item.get("readOnly", local.read_only if local else True)),
        requires_confirmation=bool(
            item.get("requiresConfirmation", local.requires_confirmation if local else False)
        ),
        execution_tool=local.execution_tool if local else None,
        required_fields=tuple(
            str(value) for value in (item.get("requiredFields") or ()) if str(value).strip()
        ),
        permission=str(item.get("permission") or (local.permission if local else "agent:read")),
    )


def _visible_action_specs() -> tuple[ActionSpec, ...]:
    """Return the Java snapshot when one exists, otherwise local offline specs."""
    catalog = runtime_action_catalog()
    if catalog:
        return tuple(_runtime_action_spec(item) for item in catalog.values())
    return ACTION_SPECS


def actions_for_capability(capability_id: str | None) -> tuple[ActionSpec, ...]:
    canonical = canonical_capability_id(capability_id)
    return tuple(item for item in _visible_action_specs() if item.capability_id == canonical)


def resolve_action(
    capability_id: str | None,
    action_id: str | None = None,
    operation: str | None = None,
) -> ActionSpec | None:
    """Resolve a registered action without exposing executor names.

    ``action_id`` is the only production contract. ``operation`` remains in
    the signature for bounded compiler callers that normalize workflow verbs,
    but it can never select an executor by itself.
    """
    del operation
    canonical = canonical_capability_id(capability_id)
    requested_id = str(action_id or "").strip().lower()
    if requested_id:
        runtime = runtime_action(requested_id)
        item = _runtime_action_spec(runtime) if runtime else _ACTION_MAP.get(requested_id)
        if item and item.capability_id == canonical:
            return item
        return None
    return None

GENERAL_CAPABILITY = Capability(
    "general_agent",
    "未能确定为已注册领域的请求，保留 DeepAgents 的通用处理和澄清能力。",
    "不得伪造业务事实；需要业务数据时必须先获得明确领域能力。",
    "向用户说明需要的业务条件，或交给通用 Agent 继续理解。",
    allowed_strategies=("fallback", "clarify"),
)

_CAPABILITY_MAP = {item.name: item for item in (*CAPABILITIES, GENERAL_CAPABILITY)}

# Models sometimes return the registered delegate name when the prompt asks
# for a capability. Normalize those names at the capability boundary; the
# executor and permission policy still come from this catalog.
_CAPABILITY_ALIASES = {
    # Providers often shorten the read-only approval domain to ``approval``
    # or ``approvals``.  Keep that transport alias at the capability boundary
    # so it cannot turn a valid pending-query request into general fallback.
    "approval": "approval_read",
    "approvals": "approval_read",
    "approval_query": "approval_read",
    "schedules_agent": "schedule",
    "meeting_rooms_agent": "meeting",
    "party_files_agent": "party_file",
    # Providers may use the plural/domain label from the user-facing
    # capability description.  The runtime registry is intentionally
    # singular; normalize all aliases at this boundary before strategy and
    # plan compilation so a read-only child name can never become the source
    # of truth for a write workflow.
    "party_files": "party_file",
    "partyfile": "party_file",
    "party_documents": "party_file",
    "party_document": "party_file",
}


def canonical_capability_id(capability_id: str | None) -> str:
    value = str(capability_id or "").strip().lower().replace("-", "_")
    return _CAPABILITY_ALIASES.get(value, value)


def capability_routing_enabled() -> bool:
    return os.getenv("OA_AGENT_CAPABILITY_ROUTING_V2", "true").strip().lower() not in {"0", "false", "no", "off"}


def resolve_capability(capability_id: str | None, requested_strategy: RouteStrategy | None,
                       confidence: float | None, unsupported_criteria: list[str] | None = None,
                       missing_fields: list[str] | None = None) -> dict:
    """Validate a model proposal against the registered capability boundary."""
    item = _CAPABILITY_MAP.get(canonical_capability_id(capability_id), GENERAL_CAPABILITY)
    score = max(0.0, min(1.0, float(confidence or 0.0)))
    unsupported = [str(value).strip() for value in (unsupported_criteria or []) if str(value).strip()]
    missing = [str(value).strip() for value in (missing_fields or []) if str(value).strip()]
    requested = requested_strategy if requested_strategy in {"direct", "delegate", "clarify", "fallback"} else None
    if item is GENERAL_CAPABILITY:
        strategy: RouteStrategy = "clarify" if unsupported else "fallback"
    elif unsupported:
        strategy = "delegate" if item.delegate_agent else "clarify"
    elif missing:
        strategy = "clarify"
    elif score and score < 0.55:
        strategy = "clarify"
    elif requested in item.allowed_strategies:
        strategy = requested
    elif "direct" in item.allowed_strategies:
        strategy = "direct"
    else:
        strategy = item.allowed_strategies[0]
    return {
        "capabilityId": item.name,
        "strategy": strategy,
        "confidence": score,
        "delegateAgent": item.delegate_agent,
        "directTools": list(item.direct_tools),
        "unsupportedCriteria": unsupported,
        "missingFields": missing,
        "fallback": item.fallback,
    }


def capability_catalog_prompt() -> str:
    lines = ["第一阶段可用领域能力（Domain Capability，先选择领域，不要选择工具）："]
    for item in (*CAPABILITIES, GENERAL_CAPABILITY):
        lines.append(f"- {item.name}: {item.description} 执行边界：{item.execution_boundary} 回退：{item.fallback}")
    return "\n".join(lines)


def action_catalog_prompt(capability_id: str | None = None) -> str:
    """Render the second-stage action catalog returned after domain routing."""
    actions = actions_for_capability(capability_id)
    if not actions:
        return "当前领域没有可用的细粒度业务动作。"
    lines = [
        f"第二阶段业务动作（Action，领域={canonical_capability_id(capability_id)}）：",
        "只能从以下 action_id 中选择；不要传工具名、Java 路径或数据库字段。",
    ]
    for item in actions:
        risk = "只读" if action_read_only(item) else "写操作，需要确认"
        fields = action_field_specs(item)
        field_text = ",".join(
            f"{field.name}:{field.field_type}{'*' if field.required else ''}"
            for field in fields
        ) or "无"
        lines.append(
            f"- {item.action_id}: {action_description(item)}；执行类别={action_execution_class(item)}；{risk}；字段={field_text}"
        )
    return "\n".join(lines)


__all__ = [
    "ActionSpec",
    "ActionFieldSpec",
    "ACTION_SPECS",
    "CAPABILITIES",
    "GENERAL_CAPABILITY",
    "actions_for_capability",
    "action_field_specs",
    "action_required_fields",
    "action_constraints",
    "action_description",
    "action_execution_class",
    "action_operation",
    "action_read_only",
    "action_requires_confirmation",
    "action_catalog_prompt",
    "capability_catalog_prompt",
    "canonical_capability_id",
    "resolve_action",
    "resolve_capability",
]
