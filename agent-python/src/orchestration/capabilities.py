"""Capability catalog used for semantic orchestration.

This catalog describes execution boundaries; it deliberately contains no
keyword-to-route rules. The model selects a capability from these contracts,
then the selected tool or sub-agent validates whether the requested fields
are actually supported.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
import re
from typing import Any
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
        "只读取当前用户的待办审批收件箱，支持筛选、排序和分析；例如“我的待办审批”“按金额排序”。“我发起的审批”和“已办历史”不属于本域。",
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
        "查询我发起的流程、已办历史，或撤回本人仍在运行中的审批流程；例如“查看我发起的审批”“查看已办历史”。不处理待办收件箱。",
        "查询走 Java BPM Facade；撤回先生成撤回草稿并通过官方 ApprovalCard，再由 Java 按发起人和流程状态执行。",
        "缺少唯一流程编号或撤回理由时先澄清；不能撤回时返回真实业务错误，不伪造成功。",
        allowed_strategies=("direct", "delegate", "clarify"),
        delegate_agent="approvals_agent",
        direct_tools=("list_my_approval_applications", "get_my_approval_application", "list_my_approval_history", "create_approval_withdraw_draft", "confirm_approval_withdraw_action"),
    ),
    Capability(
        "meeting",
        "查询会议室资源、协调参会人和预约会议室；出现“会议室、预约、参会人、会议冲突”通常属于本域，不是个人日历。",
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
        "查询、协调和维护个人日程；例如“我的日历”“我明天有什么安排”“创建一个个人日程”。会议室预约属于 meeting，不属于本域。",
        "日程写操作使用草稿和确认流程，查询使用只读工具。",
        "无法表达的跨日程任务交给对应的日程协调代理。",
        # CREATE/UPDATE/CANCEL become direct only when a matching workflow
        # contract is enabled. Calendar queries and all other requests remain
        # available through the schedule child.
        allowed_strategies=("direct", "delegate", "clarify"),
        delegate_agent="schedules_agent",
        direct_tools=("get_my_calendar",),
    ),
    Capability(
        "party_file",
        "查询、理解、比较当前用户有权限的党务文件，核对附件并维护文件；例如“制度文件”“正文条款”“文件版本差异”。",
        "元数据筛选/排序和已有附件核对使用 metadata_query Plan；附件预览/下载只返回 Java 授权的入口，不传二进制给模型；正文、条款和制度解释才使用 content_search 或文件工作流；写操作必须先生成 Java 持久草稿，再由对应操作的 HITL 确认工具提交。所有结果必须经过 Java 权限、版本和幂等边界。",
        "没有匹配文件、必要字段或权限时返回真实业务结果，不编造文件内容，也不把草稿说成已发布。",
        delegate_agent="party_files_agent",
        direct_tools=("create_party_file_draft", "confirm_create_party_file", "confirm_update_party_file", "confirm_delete_party_file"),
    ),
    Capability(
        "project",
        "查询当前用户可参与项目的进度、任务、成员负责情况、近期动态和项目资料；例如“项目卡在哪里”“张三负责事项进展如何”。",
        "项目、任务、资料和统计均由 Java Project Provider 根据 KodCloud project 插件实时权限确定；项目资料和制度知识检索只返回可引用证据，不能把索引副本当成权限事实。第一期不支持创建或修改项目、任务和文件。",
        "未指定项目或存在同名项目时先展示项目候选；无项目成员权限、KodCloud 用户未绑定或资料已失效时如实说明，不能改用共享账号或猜选项目。",
        allowed_strategies=("delegate", "clarify"),
        delegate_agent="projects_agent",
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
        "metadata_query", "PENDING", (
            "LIST", "SEARCH", "QUERY",
            # Some providers use the old domain-scoped label rather than the
            # catalog action id.  It is unambiguous only inside
            # ``approval_read`` and therefore belongs in this bounded
            # transport-alias list, not in a prose/intent fallback.
            "approval.query",
            "query_pending_approvals", "list_pending_approvals", "pending_approvals",
            "list_pending_approval_tasks",
        ), True, False,
        "run_approval_query_plan", (),
    ),
    ActionSpec(
        "approval.read.analyze", "approval_read", "分析当前用户待办审批",
        "metadata_query", "ANALYZE", ("INSIGHTS", "ANALYZE_PENDING_APPROVALS", "analyze_pending_approvals"), True, False,
        "analyze_my_pending_approvals", (),
    ),
    ActionSpec(
        "approval.process.applications", APPROVAL_PROCESS_CAPABILITY_ID, "查询我发起的审批",
        "approval_query", "APPLICATIONS", ("MY_APPLICATIONS", "list_my_submitted_approvals", "list_submitted_approvals"), True, False,
        "list_my_approval_applications",
    ),
    ActionSpec(
        "approval.process.application_detail", APPROVAL_PROCESS_CAPABILITY_ID, "查询某条我发起的审批详情",
        "approval_query", "APPLICATION_DETAIL", ("DETAIL", "query_application_detail", "get_application_detail"), True, False,
        "get_my_approval_application", ("processInstanceId",),
    ),
    ActionSpec(
        "approval.process.history", APPROVAL_PROCESS_CAPABILITY_ID, "查询已办审批历史",
        "approval_query", "HISTORY", ("MY_HISTORY", "DONE", "query_approval_history", "list_approval_history"), True, False,
        "list_my_approval_history",
    ),
    ActionSpec(
        "approval.process.withdraw", APPROVAL_PROCESS_CAPABILITY_ID, "撤回本人仍在运行中的审批",
        "approval_query", "WITHDRAW", ("CANCEL", "withdraw_process", "withdraw_approval"), False, True,
        "run_approval_write_workflow", ("processInstanceId", "reason"),
    ),
    ActionSpec(
        "approval.write.request", "approval_write", "发起审批申请草稿",
        "workflow", "CREATE", ("START", "SUBMIT"), False, True,
        "run_approval_write_workflow",
        ("process_definition",),
    ),
    ActionSpec(
        "approval.write.task", "approval_write", "处理单条待办审批",
        "workflow", "TASK_ACTION", ("APPROVE", "REJECT", "approve_approval_task", "reject_approval_task"), False, True,
        "run_approval_write_workflow", ("taskId", "action", "reason"), "approval:write",
    ),
    ActionSpec(
        "approval.write.batch", "approval_write", "批量处理待办审批",
        "workflow", "BATCH_ACTION", ("BATCH", "BATCH_APPROVE", "BATCH_REJECT", "batch_approve_approvals", "batch_reject_approvals"), False, True,
        "run_approval_write_workflow", ("taskIds", "action", "reason"), "approval:write",
    ),
    ActionSpec(
        "meeting.query", "meeting", "查询会议室预约和可用资源",
        "metadata_query", "QUERY", (
            "LIST", "SEARCH", "query_my_recent_reservations", "query_my_reservations",
            "search_meeting_rooms", "list_meeting_rooms", "query_rooms",
            "query_available_rooms", "list_available_rooms", "meeting_room.query",
        ), True, False,
        "list_my_meeting_bookings", (),
    ),
    ActionSpec(
        "meeting.create", "meeting", "创建会议室预约草稿",
        "workflow", "BOOK", (
            "CREATE", "CREATE_DRAFT", "BOOKING", "CREATE_BOOKING", "CREATE_MEETING_BOOKING",
            "BOOK_MEETING_ROOM", "reserve_meeting_room", "create_meeting", "create_reservation",
            "schedule_meeting", "book_meeting", "book_room",
        ), False, True,
        "run_meeting_booking_workflow", ("subject", "start_time", "end_time"),
    ),
    ActionSpec(
        "meeting.update", "meeting", "修改已有会议室预约",
        "workflow", "UPDATE", (
            "EDIT", "RESCHEDULE", "CHANGE", "modify_meeting", "modify_reservation",
            "update_meeting_reservation", "modify_booking", "meeting.modify", "update_booking", "reschedule_booking",
        ), False, True,
        "run_meeting_booking_workflow", ("source_booking_id",),
    ),
    ActionSpec(
        "meeting.cancel", "meeting", "取消已有会议室预约",
        "workflow", "CANCEL", (
            "DELETE", "CANCEL_BOOKING", "cancel_meeting", "cancel_reservation", "cancel_booking",
        ), False, True,
        "run_meeting_booking_workflow", ("source_booking_id",),
    ),
    ActionSpec(
        "schedule.query", "schedule", "查询个人日程",
        "metadata_query", "QUERY", (
            "LIST", "SEARCH", "CALENDAR", "schedule_query", "query_personal_schedule",
            "query_personal_calendar",
        ), True, False,
        "get_my_calendar", (),
    ),
    ActionSpec(
        "schedule.create", "schedule", "创建个人日程草稿",
        "workflow", "CREATE", (
            "CREATE", "CREATE_DRAFT", "NEW", "CREATE_SCHEDULE", "CREATE_SCHEDULE_DRAFT",
            "CREATE_PERSONAL_SCHEDULE", "CREATE_PERSONAL_SCHEDULE_DRAFT",
            "SCHEDULES/CREATE_SCHEDULE_DRAFT",
        ), False, True,
        "run_personal_schedule_workflow", ("title", "start_time", "end_time"),
    ),
    ActionSpec(
        "schedule.update", "schedule", "修改个人日程",
        "workflow", "UPDATE", ("EDIT", "UPDATE_SCHEDULE", "EDIT_SCHEDULE", "update_event", "modify_schedule"), False, True,
        "run_personal_schedule_workflow", ("source_schedule_id",),
    ),
    ActionSpec(
        "schedule.cancel", "schedule", "取消个人日程",
        "workflow", "CANCEL", (
            "CANCEL_SCHEDULE", "schedule_cancel", "DELETE", "DELETE_SCHEDULE",
        ), False, True,
        "run_personal_schedule_workflow", ("source_schedule_id",),
    ),
    ActionSpec(
        "party_file.metadata", "party_file", "按标题、分类、发布时间等查询党务文件",
        "metadata_query", "METADATA_QUERY", (
            "LIST", "SEARCH", "QUERY", "search_documents", "query_recent_published_documents",
            "search_party_files", "party_file.query", "party_file.search",
        ), True, False,
        "execute_party_file_metadata_plan", ("filters", "rank", "limit", "projection"),
    ),
    ActionSpec(
        "party_file.content", "party_file", "检索党务文件正文和条款",
        "content_search", "CONTENT_SEARCH", ("CONTENT", "UNDERSTAND", "party_file_content_search", "search_content", "search_party_file_content"), True, False,
        "search_party_knowledge", ("query",),
    ),
    ActionSpec(
        "party_file.compare", "party_file", "比较党务文件版本",
        "document_compare", "COMPARE", ("DIFF", "compare_documents", "compare_party_files"), True, False,
        "run_party_file_compare", ("left_file_id", "right_file_id"),
    ),
    ActionSpec(
        "party_file.compliance", "party_file", "按制度校验审批材料",
        "compliance_check", "COMPLIANCE_CHECK", ("CHECK", "compliance_check", "check_party_file_compliance"), True, False,
        "check_approval_against_party_file", ("task_id", "file_id"),
    ),
    ActionSpec(
        "party_file.attachments", "party_file", "查询党务文件附件",
        "metadata_query", "ATTACHMENTS", ("ATTACHMENT", "ATTACHMENT_QUERY", "ATTACHMENT_DELIVERY"), True, False,
        "get_party_file_attachments", ("source_party_file_id",),
    ),
    ActionSpec(
        "party_file.create", "party_file", "创建或发布党务文件草稿",
        "workflow", "CREATE", ("DRAFT", "PUBLISH", "create_document_draft", "create_party_file_draft"), False, True,
        "run_party_file_write_workflow", ("title", "content", "category_name"),
        permission="party-file:create",
    ),
    ActionSpec(
        "party_file.update", "party_file", "修改党务文件草稿",
        "workflow", "UPDATE", ("EDIT",), False, True,
        "run_party_file_write_workflow", ("source_party_file_id",),
        permission="party-file:update",
    ),
    ActionSpec(
        "party_file.delete", "party_file", "删除或作废党务文件草稿",
        "workflow", "DELETE", ("REMOVE", "VOID", "CANCEL"), False, True,
        "run_party_file_write_workflow", ("source_party_file_id",),
        permission="party-file:delete",
    ),
    ActionSpec(
        "project.list", "project", "查询当前用户可参与的项目",
        "metadata_query", "LIST", ("LIST", "PROJECT_LIST", "list_projects"), True, False,
        "list_accessible_projects", (), permission="project:read",
    ),
    ActionSpec(
        "project.snapshot", "project", "读取指定项目的概览、成员、配置和资料状态",
        "metadata_query", "SNAPSHOT", ("DETAIL", "PROJECT_DETAIL", "project_detail"), True, False,
        "get_project_snapshot", ("project_id",), permission="project:read",
    ),
    ActionSpec(
        "project.tasks", "project", "读取指定项目当前用户可见的任务树",
        "metadata_query", "TASKS", ("TASK", "TASK_LIST", "project_tasks"), True, False,
        "get_project_tasks", ("project_id",), permission="project:read",
    ),
    ActionSpec(
        "project.activity", "project", "读取指定项目的项目和任务动态",
        "metadata_query", "ACTIVITY", ("LOG", "LOGS", "PROJECT_ACTIVITY"), True, False,
        "get_project_activity", ("project_id",), permission="project:read",
    ),
    ActionSpec(
        "project.documents", "project", "读取指定项目资料目录的文件与同步状态",
        "metadata_query", "DOCUMENTS", ("FILES", "PROJECT_FILES", "PROJECT_DOCUMENTS"), True, False,
        "get_project_documents", ("project_id",), permission="project:read",
    ),
    ActionSpec(
        "project.investigate", "project", "根据问题自主调查项目进度、任务、动态和资料",
        "fallback_react", "INVESTIGATE", (
            "ANALYZE", "ANALYSIS", "ANALYZE_PROJECT", "PROJECT_ANALYSIS",
            "PROJECT_RISK_ANALYSIS", "RISK_ANALYSIS", "PROJECT_INVESTIGATION",
            # 部分 OpenAI 兼容模型会按资源/动作顺序生成进度概览名称。这些仅是
            # 只读调查的传输别名，解析后仍必须编译为唯一正式动作
            # ``project.investigate``，不会新增执行器或放宽项目权限。
            "PROJECT_PROGRESS_OVERVIEW", "project.progress_overview",
            "project_progress_overview", "progress_overview",
        ), True, False,
        "analyze_project", ("project_id",), permission="project:read",
    ),
    ActionSpec(
        "project.knowledge.search", "project", "检索指定项目资料和管理员制度知识库",
        "content_search", "KNOWLEDGE_SEARCH", ("SEARCH", "KNOWLEDGE", "PROJECT_KNOWLEDGE"), True, False,
        "search_project_knowledge", ("project_id", "query"), permission="project:read",
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
    "meeting.query": (
        _field("start_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
        _field("end_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
        _field("date", "date", format="yyyy-MM-dd"),
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
                        _field("end_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
                        _field("time_range", "object")),
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
    # 项目编号由 Java Project Provider 每次重新校验成员关系与任务隐私；它不是
    # 旧候选直接授予的授权 ID，因此保持 user_input，而不是 authorized_query_fact。
    "project.list": (
        _field("page_no", "integer"), _field("page_size", "integer"),
    ),
    "project.snapshot": (_field("project_id", "string", required=True),),
    "project.tasks": (_field("project_id", "string", required=True),),
    "project.activity": (
        _field("project_id", "string", required=True),
        _field("from_time", "datetime", format="yyyy-MM-dd HH:mm:ss"),
    ),
    "project.documents": (_field("project_id", "string", required=True),),
    "project.investigate": (
        _field("project_id", "string", required=True),
        _field("user_question", "string", required=True),
    ),
    "project.knowledge.search": (
        _field("project_id", "string", required=True),
        _field("query", "string", required=True), _field("top_k", "integer"),
        _field("include_policy_library", "boolean"),
    ),
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
        {"type": "exclusive_groups", "groups": [["date"], ["start_time", "end_time"], ["time_range"]]},
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


_TYPED_ROUTE_METADATA_FIELDS = frozenset({
    "action_id", "operation", "action", "entity", "type", "domain",
    "execution_class", "message", "schedule_type", "timezone",
    "authorized_source_fields",
})


# A provider's query envelope often carries an old entity/type label alongside
# a current capability or action.  These are not model-facing names: they are
# a closed compatibility table used only after a read action has already been
# selected, or while a selected read domain has exactly one matching shape.
# Unknown labels must never become executor inputs.
_READ_ACTION_ENTITY_SCOPES: dict[str, tuple[str, frozenset[str]]] = {
    "approval.read.pending": (
        "pending_approval",
        frozenset({"pending_approval", "approval", "approvals", "approval_inbox", "approval_task",
                   "pending", "pending_approvals", "todo", "my_pending"}),
    ),
    "approval.process.applications": (
        "approval_application",
        frozenset({"approval_application", "approval_applications", "my_applications", "my_requests"}),
    ),
    "approval.process.application_detail": (
        "approval_application",
        frozenset({"approval_application", "approval_detail", "application_detail"}),
    ),
    "approval.process.history": (
        "approval_history",
        frozenset({"approval_history", "approval_done", "done_approval", "my_history"}),
    ),
    "meeting.query": (
        "meeting_booking",
        frozenset({"meeting", "meeting_booking", "meeting_room", "room_booking", "reservation"}),
    ),
    "schedule.query": (
        "personal_schedule",
        frozenset({"schedule", "personal_schedule", "calendar", "personal_calendar"}),
    ),
    "party_file.metadata": (
        "party_file",
        frozenset({"party_file", "party_files", "partyfile", "party_document"}),
    ),
    "party_file.attachments": (
        "party_file",
        frozenset({"party_file", "party_files", "partyfile", "party_document", "party_attachment"}),
    ),
    "project.list": (
        "project",
        frozenset({"project", "projects", "project_list"}),
    ),
    "project.snapshot": (
        "project",
        frozenset({"project", "project_snapshot", "project_detail"}),
    ),
    "project.tasks": (
        "project_task",
        frozenset({"project_task", "project_tasks", "task", "tasks"}),
    ),
    "project.activity": (
        "project_activity",
        frozenset({"project_activity", "project_log", "project_logs", "activity"}),
    ),
    "project.documents": (
        "project_document",
        frozenset({"project_document", "project_documents", "project_file", "project_files"}),
    ),
}


def _read_scope_value(values: dict[str, Any]) -> str:
    return str(
        values.get("entity") or values.get("domain") or values.get("type")
        or values.get("object_type") or values.get("objectType") or ""
    ).strip().lower().replace("-", "_")


def canonicalize_read_action_scope(
    action: ActionSpec,
    payload: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """Normalize one registered read action's closed entity aliases.

    This is deliberately not a domain router. It cannot cross the selected
    capability, select a write action, or accept an unregistered entity. A
    disagreeing entity becomes a scope clarification before it reaches a
    domain compiler, where it would otherwise look like an opaque unsupported
    business entity.
    """
    candidate = dict(payload or {})
    intent = dict(query_intent or {})
    if not action.read_only:
        return candidate, intent, None
    scope = _READ_ACTION_ENTITY_SCOPES.get(action.action_id)
    if scope is None:
        return candidate, intent, None
    canonical_entity, accepted_entities = scope
    values = [value for value in (_read_scope_value(candidate), _read_scope_value(intent)) if value]
    if not values:
        return candidate, intent, None
    if any(value not in accepted_entities for value in values):
        return candidate, intent, (
            f"查询实体与已选动作 {action.action_id} 的只读范围不一致；"
            "请确认要查询的业务范围。"
        )
    # Both candidate_plan and query_intent are transport envelopes. Once the
    # action contract proves they refer to this same scope, retain only the
    # canonical entity for downstream domain compilers.
    for values_dict in (candidate, intent):
        if _read_scope_value(values_dict):
            values_dict["entity"] = canonical_entity
            for key in ("domain", "type", "object_type", "objectType"):
                values_dict.pop(key, None)
    return candidate, intent, None


def _normalize_typed_field_name(value: Any) -> str:
    """Normalize provider field spelling for schema matching only."""
    text = str(value or "").strip().replace("-", "_")
    return re.sub(r"(?<!^)(?=[A-Z])", "_", text).lower()


def resolve_typed_read_action(
    capability_id: str | None,
    execution_class: str | None,
    *,
    candidate_plan: dict[str, Any] | None = None,
    query_intent: dict[str, Any] | None = None,
) -> ActionSpec | None:
    """Recover one read action from a typed payload when its id drifted.

    This is an anti-corruption boundary for model/provider transport drift. It
    never infers a write action, executor, or Java endpoint. Recovery is valid
    only when the selected capability and execution class contain exactly one
    read-only action whose declared fields fully explain the payload.
    """
    if str(execution_class or "").strip().lower() not in {
        "metadata_query", "approval_query", "report",
    }:
        return None
    payload = {
        **(query_intent if isinstance(query_intent, dict) else {}),
        **(candidate_plan if isinstance(candidate_plan, dict) else {}),
    }
    supplied = {
        _normalize_typed_field_name(key)
        for key, value in payload.items()
        if _normalize_typed_field_name(key) not in _TYPED_ROUTE_METADATA_FIELDS
        and value not in (None, "", [], {})
    }
    entity = _read_scope_value(payload)

    matches: list[tuple[ActionSpec, int]] = []
    for action in actions_for_capability(capability_id):
        if not action.read_only or action.execution_class != str(execution_class).strip().lower():
            continue
        field_names = {
            _normalize_typed_field_name(field.name)
            for field in action_field_specs(action)
        }
        overlap = supplied & field_names
        entity_scope = _READ_ACTION_ENTITY_SCOPES.get(action.action_id)
        entity_matches = bool(
            entity_scope and entity and entity in entity_scope[1]
        )
        if overlap and supplied <= field_names:
            matches.append((action, len(overlap) + (1 if entity_matches else 0)))
        elif entity_matches and not supplied:
            matches.append((action, 1))
    if not matches:
        return None
    best_score = max(score for _, score in matches)
    best = [action for action, score in matches if score == best_score]
    return best[0] if len(best) == 1 else None


def _normalize_action_reference(value: str | None) -> str:
    """Normalize a provider's transport reference without changing semantics."""
    return str(value or "").strip().lower().replace("-", "_")


def is_non_action_reference(value: str | None) -> bool:
    """Return whether a value belongs to another identifier namespace.

    Capability ids, delegate names, and local executor names are valid in
    their own transport fields, but never as ``action_id`` values. Keeping
    this check in the catalog boundary prevents typed read recovery from
    hiding a namespace error.
    """
    requested = _normalize_action_reference(value)
    if not requested:
        return False
    capabilities = {
        _normalize_action_reference(item.name)
        for item in (*CAPABILITIES, GENERAL_CAPABILITY)
    }
    delegates = {
        _normalize_action_reference(item.delegate_agent)
        for item in CAPABILITIES
        if item.delegate_agent
    }
    executors = {
        _normalize_action_reference(item.execution_tool)
        for item in ACTION_SPECS
        if item.execution_tool
    }
    return requested in capabilities or requested in delegates or requested in executors


def _action_matches_reference(action: ActionSpec, requested_id: str) -> bool:
    if _normalize_action_reference(action.action_id) == requested_id:
        return True
    return any(
        _normalize_action_reference(alias) == requested_id
        for alias in action.aliases
    )


def resolve_registered_action_alias(action_id: str | None) -> ActionSpec | None:
    """Resolve one unique catalog-owned legacy alias across capabilities.

    The normal resolver remains capability-scoped.  This narrow adapter is
    used only when a provider puts a known legacy label in ``action_id`` while
    also choosing the wrong capability.  The alias must be declared by one
    registered action; arbitrary fuzzy names and executor names never enter
    this path.
    """
    requested = _normalize_action_reference(action_id)
    if not requested:
        return None
    matches = [
        action
        for action in _visible_action_specs()
        if any(_normalize_action_reference(alias) == requested for alias in action.aliases)
    ]
    return matches[0] if len(matches) == 1 else None


# A provider may put a typed operation in the route envelope instead of the
# canonical action id.  Generic CRUD verbs are deliberately excluded: a bare
# ``CREATE`` is not enough to cross the action boundary, while a catalog-owned
# alias such as ``CREATE_BOOKING`` is specific enough within its capability.
_GENERIC_OPERATION_REFERENCES = frozenset({
    "create", "update", "delete", "cancel", "query", "list", "search",
    "read", "write", "book", "edit", "new", "draft", "publish", "check",
    "detail", "approve", "reject", "batch", "content", "compare", "diff",
    "analyze", "filter", "rank", "calendar",
})


def _action_matches_operation_alias(action: ActionSpec, operation: str) -> bool:
    requested = _normalize_action_reference(operation)
    if not requested or requested in _GENERIC_OPERATION_REFERENCES:
        return False
    return any(
        _normalize_action_reference(alias) == requested
        for alias in action.aliases
    )


def resolve_action(
    capability_id: str | None,
    action_id: str | None = None,
    operation: str | None = None,
) -> ActionSpec | None:
    """Resolve a registered action without exposing executor names.

    ``action_id`` remains the canonical production contract.  When it is
    absent, ``operation`` may recover one action only through a specific alias
    explicitly registered in the current capability.  This repairs provider
    transport drift (for example ``create_booking``) without allowing a bare
    CRUD verb to select an executor.
    """
    canonical = canonical_capability_id(capability_id)
    requested_id = _normalize_action_reference(action_id)
    if requested_id:
        runtime = runtime_action(requested_id)
        item = _runtime_action_spec(runtime) if runtime else _ACTION_MAP.get(requested_id)
        if item and item.capability_id == canonical:
            return item
        # The canonical action id remains the Java contract.  These aliases
        # are only a bounded transport adapter for providers that emit a
        # registered capability/action label (for example ``create_booking``)
        # instead of the canonical ``meeting.create`` reference.  Never use
        # an alias to select an executor outside the selected capability.
        for candidate in actions_for_capability(canonical):
            if _action_matches_reference(candidate, requested_id):
                return candidate
        return None
    requested_operation = _normalize_action_reference(operation)
    if requested_operation:
        matches = [
            candidate
            for candidate in actions_for_capability(canonical)
            if _action_matches_operation_alias(candidate, requested_operation)
        ]
        return matches[0] if len(matches) == 1 else None
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
    "approvals_agent": "approval_read",
    "schedules": "schedule",
    "personal_schedule": "schedule",
    "schedules_agent": "schedule",
    "meeting_rooms": "meeting",
    "meeting_room": "meeting",
    "meeting_booking": "meeting",
    "meeting_rooms_agent": "meeting",
    "party_files_agent": "party_file",
    "projects_agent": "project",
    # Providers may use the plural/domain label from the user-facing
    # capability description.  The runtime registry is intentionally
    # singular; normalize all aliases at this boundary before strategy and
    # plan compilation so a read-only child name can never become the source
    # of truth for a write workflow.
    "party_files": "party_file",
    "partyfile": "party_file",
    "party_documents": "party_file",
    "party_document": "party_file",
    "projects": "project",
    "project_agent": "project",
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
        "unsupportedCriteria": unsupported,
        "missingFields": missing,
        "fallback": item.fallback,
    }


def capability_catalog_prompt() -> str:
    lines = [
        "第一阶段可用领域能力（Domain Capability，只选择 capability_id，不要选择 action_id、子 Agent 名称或工具名）：",
    ]
    for item in (*CAPABILITIES, GENERAL_CAPABILITY):
        lines.append(f"- {item.name}: {item.description} 执行边界：{item.execution_boundary} 回退：{item.fallback}")
    return "\n".join(lines)


FIELD_LABELS: dict[str, str] = {
    "subject": "主题",
    "start_time": "开始时间",
    "end_time": "结束时间",
    "date": "查询日期",
    "source_booking_id": "已授权会议预约编号",
    "source_schedule_id": "已授权个人日程编号",
    "processInstanceId": "已授权流程编号",
    "process_instance_id": "已授权流程编号",
    "taskId": "已授权任务编号",
    "task_id": "已授权任务编号",
    "taskIds": "已授权任务编号列表",
    "task_ids": "已授权任务编号列表",
    "source_party_file_id": "已授权党务文件编号",
    "project_id": "项目编号",
    "page_no": "页码",
    "page_size": "每页数量",
    "from_time": "动态起始时间",
    "include_policy_library": "是否同时检索制度知识库",
    "report_type": "报告类型",
    "left_file_id": "已授权左侧文件编号",
    "right_file_id": "已授权右侧文件编号",
    "title": "文件或日程标题",
    "content": "文件正文",
    "reason": "操作理由",
    "attendees": "参会人",
    "attendee_names": "参会人",
    "attendee_user_ids": "参会人用户",
    "other_participants": "其他参与人",
    "room_capacity": "会议室容量",
    "equipment": "设备",
    "room_preference": "会议室偏好",
    "remark": "备注",
    "cancel_reason": "取消理由",
    "description": "说明",
    "location": "地点",
    "category_name": "分类名称",
    "summary": "摘要",
    "publish_time": "发布时间",
    "targets": "发布对象",
    "distribute_to_self": "是否抄送本人",
    "storage_type": "存储类型",
    "status": "状态",
    "attachment_file_ids": "附件文件编号",
    "source_file_id": "已授权源文件编号",
    "query": "检索内容",
    "keyword": "关键词",
    "title_keyword": "标题关键词",
    "content_keyword": "正文关键词",
    "top_k": "返回条数",
    "limit": "返回条数",
    "offset": "起始位置",
    "sort": "排序方式",
    "filters": "筛选条件",
    "outcome": "审批结论",
    "comment": "审批意见",
    "variables": "流程变量",
}


def field_display_label(field_name: str, action: ActionSpec | None = None) -> str:
    """Return a user-facing label for a field name.

    The static label table is the primary source; when a field is not listed
    there, fall back to the registered action schema's description and then to
    the raw field name. This keeps clarification copy readable for any action
    that grows new fields without touching the mapping table.
    """
    name = str(field_name or "").strip()
    if not name:
        return ""
    label = FIELD_LABELS.get(name)
    if label:
        return label
    if action is not None:
        for field in action_field_specs(action):
            if field.name == name and field.description:
                return field.description
    return name


def _invalid_field_hint(field_name: str, action: ActionSpec | None = None) -> str:
    """Render a readable hint for a field whose value failed validation."""
    name = str(field_name or "").strip()
    if not name:
        return ""
    label = field_display_label(name, action)
    if not label:
        label = name
    if action is not None:
        for field in action_field_specs(action):
            if field.name == name and field.format:
                return f"{label}（需要格式 {field.format}）"
    return label


def build_clarification_question(
    missing_fields: list[str] | tuple[str, ...],
    action: ActionSpec | None = None,
    invalid_fields: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Render a readable clarification question from structured field results.

    Missing fields tell the user what to add; invalid fields tell the user (and
    the model) what to correct and in which format. Composite constraint labels
    such as ``start_time/end_time(必须同时提供)`` already carry their own
    explanation and pass through unchanged.
    """
    missing_labels = [field_display_label(name, action) for name in (missing_fields or [])]
    missing_labels = [label for label in missing_labels if label]
    invalid_labels = [_invalid_field_hint(name, action) for name in (invalid_fields or [])]
    invalid_labels = [label for label in invalid_labels if label]
    clauses: list[str] = []
    if missing_labels:
        clauses.append(f"还需补充以下信息：{'、'.join(missing_labels)}")
    if invalid_labels:
        clauses.append(f"以下字段的取值不正确：{'、'.join(invalid_labels)}")
    if not clauses:
        return "请补充动作所需的信息后继续。"
    return "；".join(clauses) + "。请补充或修正后继续。"


def suggest_action_id_from_payload(
    capability_id: str | None,
    candidate_plan: dict[str, Any] | None,
    query_intent: dict[str, Any] | None,
    execution_class: str | None = None,
) -> str | None:
    """Suggest one registered action from a complete typed payload.

    This is a presentation aid for the second routing stage, not a prose
    classifier. The payload must contain only fields declared by the action,
    satisfy every required field, and match the selected execution class when
    one is known. This prevents shared optional fields such as meeting times
    from selecting update/cancel actions that still lack their required source
    booking id.
    """
    payload = {
        **(query_intent if isinstance(query_intent, dict) else {}),
        **(candidate_plan if isinstance(candidate_plan, dict) else {}),
    }
    ignored = {
        "action_id", "actionId", "operation", "action", "entity", "type",
        "domain", "execution_class", "executionClass", "_authorized_source_fields",
        "_action_id_synthesized",
    }

    def normalize(name: Any) -> str:
        return re.sub(r"(?<!^)(?=[A-Z])", "_", str(name or "").strip()).lower().replace("-", "_")

    supplied = {
        normalize(key)
        for key, value in payload.items()
        if key not in ignored and value not in (None, "", [], {})
    }
    if not supplied:
        return None
    matches: list[tuple[str, int]] = []
    requested_class = str(execution_class or "").strip().lower()
    for action in actions_for_capability(capability_id):
        if requested_class and action_execution_class(action).strip().lower() != requested_class:
            continue
        fields = action_field_specs(action)
        names = {normalize(field.name) for field in fields}
        overlap = supplied & names
        required = {normalize(name) for name in action_required_fields(action)}
        # Read-only actions are eligible only through their declared schema;
        # in particular, never let a domain-level or executor-shaped payload
        # select a read action with no typed field overlap.
        if overlap and supplied <= names and required <= supplied:
            matches.append((action.action_id, len(overlap)))
    if not matches:
        return None
    best_score = max(score for _, score in matches)
    best = [action_id for action_id, score in matches if score == best_score]
    return best[0] if len(best) == 1 else None


def action_catalog_prompt(capability_id: str | None = None) -> str:
    """Render the second-stage action catalog returned after domain routing.

    Besides the action list, the prompt pins the exact JSON shape the model
    must emit for ``candidate_plan``: canonical field names, field types and
    format rules, plus a concrete example.  The compile layer still enforces
    these rules deterministically; the prompt only keeps model output stable
    so the compile layer rarely has to repair it.
    """
    actions = actions_for_capability(capability_id)
    if not actions:
        return "当前领域没有可用的细粒度业务动作。"
    canonical = canonical_capability_id(capability_id)
    lines = [
        f"第二阶段业务动作（Action，领域={canonical}）：",
        "只能从以下正式 action_id 中选择；不要把 capability_id、delegateAgent、子 Agent 名称、Executor 名称或 Java 路径作为 action_id。别名只用于服务端迁移兼容，不属于模型可选值。",
    ]
    for item in actions:
        risk = "只读" if action_read_only(item) else "写操作，需要确认"
        fields = action_field_specs(item)
        field_text = ",".join(
            f"{field.name}({FIELD_LABELS.get(field.name, field.name)}):{field.field_type}{'*' if field.required else ''}"
            for field in fields
        ) or "无"
        lines.append(
            f"- {item.action_id}: {action_description(item)}；执行类别={action_execution_class(item)}；{risk}；字段={field_text}"
        )
    enum_fields = []
    for item in actions:
        for field in action_field_specs(item):
            if field.enum:
                enum_fields.append((field.name, ", ".join(str(value) for value in field.enum)))
    lines.append("字段格式约定（提交 candidate_plan 时严格遵守）：")
    lines.append(
        "- datetime 字段：yyyy-MM-dd HH:mm:ss，必须含日期和时间（例：2026-08-09 10:00:00；不要只写 10:00）。"
    )
    lines.append("- date 字段：yyyy-MM-dd（例：2026-08-09）。")
    if canonical == "schedule" and any(item.action_id == "schedule.query" for item in actions):
        lines.append(
            "- schedule.query 的时间只可三选一：date、完整 start_time/end_time，或 time_range 对象。"
            "本周/上周/下周使用日历周期："
            '{"kind":"CALENDAR_PERIOD","unit":"WEEK","offset":0,"precision":"DAY"}'
            "（上周 offset=-1、下周 offset=1）；本月/下月把 unit 改为 MONTH。"
            "最近 7 天等滑动区间使用："
            '{"kind":"RELATIVE","anchor":"CURRENT_DATE","precision":"DAY",'
            '"start_offset_days":-6,"end_offset_days":0}。不要把“最近一周/本周”等原文填进 date 或 datetime；'
            "服务端会以 Asia/Shanghai 业务时钟编译为明确 start/end。"
        )
    lines.append("- integer/number 字段：纯数字，不带单位、引号或货币符号。")
    lines.append('- array 字段：JSON 字符串数组（例：["张三","李四"]）。')
    for name, values in enum_fields:
        lines.append(f"- {name} 字段：只能取 {values} 之一。")
    lines.append(
        "candidate_plan 必须是 JSON 对象：键名用上述正式字段名（不能用别名），值符合上面的格式约定；"
        "只提交用户明确给出或工具真实返回的字段，缺失字段不要编造。"
        "candidate_plan 样例：{\"subject\":\"周会\",\"start_time\":\"2026-08-09 10:00:00\",\"end_time\":\"2026-08-09 11:00:00\"}"
        "（样例日期仅为格式演示，实际日期以用户消息和业务时钟为准）"
    )
    lines.append(
        "动作 ID 由当前运行时的 Action Catalog 注入到 route_conversation 工具 schema；"
        "选择时以 schema 的 action_id 枚举为准，不要使用本提示词之外的固定动作名。"
    )
    return "\n".join(lines)


__all__ = [
    "ActionSpec",
    "ActionFieldSpec",
    "ACTION_SPECS",
    "CAPABILITIES",
    "FIELD_LABELS",
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
    "build_clarification_question",
    "capability_catalog_prompt",
    "canonical_capability_id",
    "field_display_label",
    "is_non_action_reference",
    "resolve_typed_read_action",
    "resolve_action",
    "resolve_registered_action_alias",
    "resolve_capability",
    "suggest_action_id_from_payload",
]
