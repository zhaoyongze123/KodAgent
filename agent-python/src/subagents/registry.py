"""构造 OA 图中使用的领域子 Agent 规格。

文件职责
========
这里维护每个领域子 Agent 的完整工具目录、领域提示词和运行时中间件。完整目录
解决“中央已编译计划但子 Agent 没有能力执行”的问题；实际某次请求能看见和调用
哪些工具，则由 ``WorkOrderToolProjectionMiddleware`` 与
``WorkflowPlanBinderMiddleware`` 根据中央编译的 WorkOrder 决定。

调用关系
========
``oa_agent`` -> ``build_subagents`` -> DeepAgents 子 Agent；子 Agent 收到
WorkOrder 后由投影中间件缩小可见工具，由绑定中间件在真实调用边界再次校验。

结构导读
========
* 导入区：按审批、会议、党务、日程领域收集工具；
* ``build_subagents``：组装工具目录、中间件、工作流开关和子 Agent 规格；
* ``validate_subagent_specs``：在返回前检查规格是否可安全注册。
"""

from ..middleware import (
    ExecutionReceiptMiddleware,
    MeetingExecutionReceiptMiddleware,
    MeetingPrepareFirstMiddleware,
    WorkOrderToolProjectionMiddleware,
    WorkflowPlanBinderMiddleware,
)
from ..runtime.model_runtime import DynamicModelMiddleware
from ..tools.common import report_progress
from ..tools.approval.templates import (
    list_startable_approval_types, preview_approval_request,
)
from ..tools.approval.requests import (
    create_approval_request_draft, create_approval_withdraw_draft,
    create_generic_approval_request_draft,
)
from ..tools.approval.history import (
    list_my_approval_applications, get_my_approval_application, list_my_approval_history,
)
from ..tools.approval.pending import (
    analyze_my_pending_approvals, list_my_pending_approvals, run_approval_query_plan,
    search_my_pending_approvals,
)
from ..tools.approval.actions import (
    get_approval_task_detail, preview_approval_batch_action, preview_approval_task_action,
)
from ..tools.meeting.attendees import (
    get_current_meeting_user, get_meeting_attendees_calendar,
    search_meeting_attendees,
)
from ..tools.meeting.conflicts import (
    check_meeting_availability, check_meeting_availability_batch,
    check_meeting_room_conflict,
)
from ..tools.meeting.drafts import create_meeting_booking_draft
from ..tools.meeting.prepare import prepare_meeting_booking_request
from ..tools.meeting.rooms import list_available_meeting_rooms
from ..tools.meeting.manage import create_meeting_booking_cancellation_draft, get_my_meeting_booking, list_my_meeting_bookings
from ..tools.party_files.query import get_party_file_attachment, get_party_file_attachments, get_party_file_detail, list_party_file_categories, search_party_files
from ..tools.party_files.metadata import execute_party_file_metadata_plan
from ..tools.party_files.knowledge import search_party_knowledge
from ..tools.party_files.manage import (
    create_party_file_draft, delete_party_file_draft, get_manage_party_file,
    update_party_file_draft,
)
from ..tools.workflows.party_files import check_approval_against_party_file, run_party_file_compare, run_party_file_understanding
from ..tools.schedule.drafts import create_personal_schedule_draft, get_personal_schedule
from ..tools.schedule.query import find_calendar_conflicts, get_my_calendar
from ..tools.reports import approval_report, meeting_report, party_file_report, schedule_report
from ..tools.workflows.meeting_booking import run_meeting_booking_workflow
from ..tools.workflows.personal_schedule import run_personal_schedule_workflow
from ..tools.workflows.approval import run_approval_write_workflow
from ..tools.workflows.party_file_write import run_party_file_write_workflow
from ..workflows.registry import workflow_registry
from ..orchestration.policies import (
    CurrentUserMessageMiddleware,
    meeting_booking_workflow_once_middleware,
    meeting_tool_call_limit_middleware,
    meeting_workflow_limit_middleware,
    personal_schedule_workflow_once_middleware,
)
from .contracts import validate_subagent_specs


def build_subagents(current_business_time: str, *, include_meeting_agent: bool = True) -> list[dict]:
    """构造本次运行独享的领域子 Agent 规格。

    参数：
        current_business_time：上海时区的当前业务时间，供子 Agent 将相对日期换算
            为明确日期，不能使用模型自行猜测的系统时间。
        include_meeting_agent：是否注册会议领域子 Agent；默认注册，测试或受控
            部署场景可显式关闭。

    返回：
        可直接传给 DeepAgents 的子 Agent 规格列表。中间件实例必须每次新建，避免
        不同 Run 之间共享可变状态。

    确定性工作流只覆盖已注册操作的一部分。即使工作流开启，会议 ReAct 子 Agent
    仍需保留，以支持追问、修改和复杂协调；其真实可调用范围由 WorkOrder 决定。
    """
    # 这里是“领域完整能力目录”，不再随 feature flag 删除工具。某次请求实际
    # 可见什么，由 WorkOrderToolProjectionMiddleware 按中央执行契约投影。
    # 这样回滚/诊断能力不丢，也不会让默认工作流订单看到低层写工具。
    meeting_tools = [
        report_progress,
        list_my_meeting_bookings,
        get_my_meeting_booking,
        list_available_meeting_rooms,
        search_meeting_attendees,
        get_current_meeting_user,
        get_meeting_attendees_calendar,
        check_meeting_room_conflict,
        check_meeting_availability,
        check_meeting_availability_batch,
        prepare_meeting_booking_request,
        create_meeting_booking_draft,
        create_meeting_booking_cancellation_draft,
        meeting_report,
        run_meeting_booking_workflow,
    ]
    meeting_workflow_enabled = workflow_registry.enabled("meeting_booking")
    meeting_middleware = [
        CurrentUserMessageMiddleware(trusted_source=False),
        DynamicModelMiddleware(),
        WorkOrderToolProjectionMiddleware(),
        WorkflowPlanBinderMiddleware(),
        # 会议工作流已有专用草稿回执；普通会议查询使用通用回执。
        ExecutionReceiptMiddleware(
            skip_tools=frozenset({"run_meeting_booking_workflow"})
        ),
    ]
    if meeting_workflow_enabled:
        meeting_middleware = [
            *meeting_middleware,
            meeting_booking_workflow_once_middleware(),
            meeting_workflow_limit_middleware(),
            MeetingExecutionReceiptMiddleware(),
        ]
        meeting_execution_rules = """新建、修改、取消会议预约时，只能调用一次 run_meeting_booking_workflow。它内部会依次整理请求、查询会议室、批量检查冲突并生成草稿；不要单独调用准备、冲突检查或草稿工具，也不能调用最终确认工具。"""
    else:
        # 显式关闭工作流仅用于紧急回滚。保留旧的分步只读/草稿入口，但不改变
        # 默认路径；生产默认仍走上方的受控工作流。
        meeting_middleware = [
            *meeting_middleware,
            MeetingPrepareFirstMiddleware(),
            *meeting_tool_call_limit_middleware(),
            meeting_workflow_limit_middleware(),
        ]
        meeting_execution_rules = """会议工作流已被运维显式关闭。仅在此紧急回滚模式下，按准备请求、查询候选、批量检查、生成草稿的顺序执行；绝不能调用最终确认工具。"""

    schedule_tools = [
        report_progress, get_my_calendar, find_calendar_conflicts,
        get_personal_schedule, create_personal_schedule_draft, schedule_report,
        run_personal_schedule_workflow,
    ]
    schedule_middleware = [
        DynamicModelMiddleware(), WorkOrderToolProjectionMiddleware(),
        # 通用回执中间件会把 DRAFT_READY 提升为个人日程专用回执。
        WorkflowPlanBinderMiddleware(), ExecutionReceiptMiddleware(),
    ]
    if workflow_registry.enabled("personal_schedule"):
        schedule_middleware.append(personal_schedule_workflow_once_middleware())

    specs = [
        {
            "name": "approvals_agent", "description": "处理审批模板申请、撤回和待办审批。",
            "system_prompt": """你是审批助手。只使用工具返回的真实 OA 数据，不能猜测流程定义、任务 ID、下一审批人或流程变量。
每次处理业务请求时，必须先单独调用 report_progress(stage=\"plan\")，用一句简短摘要说明你将查询或执行什么；收到播报工具结果后，再调用审批业务工具。不要输出隐藏思考过程。
完成工具调用后，返回完整、可核验的审批事实给主 Agent；不要为了简短而丢弃记录、状态、时间或错误信息。主 Agent 会负责面向用户提炼和排版，不要预先替它臆测结论。
收到 KODAGENT_WORK_ORDER 时，canonicalPlan 是唯一权威业务字段，userContext 只作上下文；只可用领域只读工具核验事实，并且只能调用 allowedExecutors 中指定的执行器完成该订单，不能重新路由或替换动作。
先调用 list_startable_approval_types 确认当前用户可发起的模板及表单字段。任何审批写操作只能调用一次 run_approval_write_workflow；它会根据 REQUEST、WITHDRAW、TASK_ACTION、BATCH_ACTION 生成持久化草稿或确认预览。用户点击官方确认卡后，主图才会恢复相应确认工具；不得直接调用 BPM 写入接口或用文本“确认”代替卡片。
“我发起的审批”“已办审批”使用 list_my_approval_applications、get_my_approval_application、list_my_approval_history，只读；不要把待办列表误当成发起记录或已办记录。
处理待办时：普通列表或单条详情继续使用原有查询工具；用户同时给出审批类型、金额、时间、部门、待办时长或排序等多个条件时，使用 search_my_pending_approvals，把条件转换为结构化字段。该工具会由 Java 在当前用户权限范围内确定性筛选并返回候选和排除原因；不可根据模型判断自行增删结果。单条和批量待办的确认预览均由 run_approval_write_workflow 生成；绝不可直接调用批量执行或 BPM 写接口。不接受或生成任意流程变量和下一审批人。若流程要求选择下一审批人，说明当前第一期不支持该动作，请用户回 OA 页面处理。""",
            "tools": [report_progress, list_startable_approval_types, preview_approval_request, create_approval_request_draft, create_generic_approval_request_draft, create_approval_withdraw_draft, list_my_approval_applications, get_my_approval_application, list_my_approval_history, list_my_pending_approvals, search_my_pending_approvals, analyze_my_pending_approvals, run_approval_query_plan, get_approval_task_detail, preview_approval_task_action, preview_approval_batch_action, approval_report, run_approval_write_workflow],
            "skills": ["/skills/approvals/"],
            "middleware": [DynamicModelMiddleware(), WorkOrderToolProjectionMiddleware(), WorkflowPlanBinderMiddleware(), ExecutionReceiptMiddleware()],
        },
        {
            "name": "meeting_rooms_agent", "description": "处理会议室查询、参会人员日程检查及会议预约待确认草稿。",
            "system_prompt": f"""你是会议室预约领域 Agent，只负责会议室查询、参会人员日程检查、冲突判断和预约草稿生成。最终提交只能由主 Agent 在用户确认后执行。
当前业务时间为 {current_business_time}（Asia/Shanghai）。用户说“今天、明天、后天、昨天”或“下周某天”时，必须先换算成明确公历日期，再把完整的 yyyy-MM-dd HH:mm:ss 传给所有工具；不能因为用户使用相对日期就追问具体日期。
{meeting_execution_rules}
收到 KODAGENT_WORK_ORDER 时，说明主图已完成路由和计划编译。WorkOrder 的 canonicalPlan 是唯一权威业务字段，userContext 仅用于理解上下文；可用领域只读工具先做校验，但只能调用 allowedExecutors 中指定的执行器完成该订单。工作流会确定性生成受控草稿，必须把返回的草稿状态、confirmation_token、draft_id、approval_id 或结构化错误原样返回给主 Agent，不要调用 confirm_meeting_booking。未覆盖的复杂协调只允许查询和返回结构化事实；非申请人没有修改或取消权限，必须如实说明。
后续所有 Tool 必须使用准备工具返回的结构化时间和 attendee_user_ids；不要直接使用模型猜测的用户 ID 或未经校验的相对日期。会议室冲突永远不能被忽略；参会人日程冲突默认阻止生成普通草稿，只有用户明确选择“忽略参会人冲突”时，才允许生成带冲突标记的草稿。
创建预约草稿不是最终业务写操作，必须执行并保存到 PostgreSQL；禁止的只是用户确认前调用正式预约提交接口。不要输出隐藏思考过程，只使用 report_progress 播报简短计划、事实和结果；不得编造会议室、用户、日程或预约结果。
完成工具调用后，返回完整、可核验的会议事实给主 Agent；不要删减可用会议室、冲突、草稿字段或错误信息。""",
            "tools": meeting_tools,
            "skills": ["/skills/meeting-room-booking/"],
            "middleware": meeting_middleware,
        },
        {
            "name": "schedules_agent", "description": "处理个人日程查询、协调和维护请求。",
            "system_prompt": f"你是个人日程领域 Agent，只处理主图明确委派的个人日历查询、协调和维护请求，不要把 schedules_agent 当作 action_id，也不要重新解释或替换主图已经编译的 Action。每次处理请求先单独调用 report_progress(stage=\"plan\") 播报一句简短执行摘要，再调用日程工具；不要输出隐藏思考过程。完成工具调用后，返回完整、可核验的日程事实给主 Agent，不要丢弃记录或臆测结论；主 Agent 会负责最终答复的提炼和排版。当前业务时间为 {current_business_time}（Asia/Shanghai）。用户说今天、明天、后天或下周某天时，先换算成明确公历日期和完整时间，再调用工具；只有确实缺少日期和时间范围时才向用户询问。创建、修改、取消前必须先确认唯一的 PERSONAL_SCHEDULE；MEETING_BOOKING 只能读取，绝不可用个人日程工具修改。收到 KODAGENT_WORK_ORDER 时，canonicalPlan 是唯一权威业务字段，userContext 只作上下文；可用只读工具核验事实，但只能调用 allowedExecutors 中指定的执行器。修改/取消的 source_schedule_id 由计划提供，不得猜测。草稿不是最终写入，生成草稿后等待用户确认，不能调用 confirm_personal_schedule。",
            "tools": schedule_tools, "skills": ["/skills/personal-schedule/"], "middleware": schedule_middleware,
        },
        {
            "name": "party_files_agent", "description": "处理党务文件查询、内容理解、比较和制度校验。",
            "system_prompt": """你是党务文件领域 Agent，只处理当前用户有权限看到的文件查询、理解、比较和受控草稿生成。每次处理业务请求时先调用 report_progress(stage=\"plan\")，再调用一个领域工具；不要输出隐藏思考过程。需要读取正文时，再按文件 ID 获取详情；获取详情会记录已读，附件工具只返回元数据，不会传输二进制文件。涉及发布时间、分类、已读状态、排序、分页等结构化元数据时，统一调用 execute_party_file_metadata_plan；计划会由 Java 在当前用户权限范围内确定性筛选、排序和分页，不能先取前 N 条再由模型比较日期，也不能自行转换时间戳。只有用户明确询问正文、条款或制度语义时才调用 search_party_knowledge；普通元数据任务不得进入向量检索。收到 KODAGENT_WORK_ORDER 时，canonicalPlan 是唯一权威业务字段，写操作只能调用 run_party_file_write_workflow 一次；它会根据 CREATE、UPDATE、DELETE 生成持久化草稿。绝不调用确认工具或后台 /system/party-file/*。根图会从已验证的 Operation/Approval 回执生成确认卡。不得编造文件 ID、分类、附件或发布结果。完成工具调用后，只返回工具中的匹配结果和必要事实，不输出长篇自由推理；主 Agent 会负责最终答复的提炼和排版。""",
            "tools": [report_progress, search_party_files, execute_party_file_metadata_plan, search_party_knowledge, get_party_file_detail, get_party_file_attachments, get_party_file_attachment, list_party_file_categories, get_manage_party_file, create_party_file_draft, update_party_file_draft, delete_party_file_draft, run_party_file_understanding, run_party_file_compare, check_approval_against_party_file, party_file_report, run_party_file_write_workflow], "skills": ["/skills/party-files/"], "middleware": [DynamicModelMiddleware(), WorkOrderToolProjectionMiddleware(), WorkflowPlanBinderMiddleware(), ExecutionReceiptMiddleware()],
        },
    ]
    if include_meeting_agent:
        return validate_subagent_specs(specs)
    return validate_subagent_specs(
        [spec for spec in specs if spec.get("name") != "meeting_rooms_agent"],
        required_names={"approvals_agent", "schedules_agent", "party_files_agent"},
    )
