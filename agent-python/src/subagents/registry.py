"""Construct the domain sub-agent specifications used by the OA graph."""

from ..middleware import MeetingDraftIdempotencyMiddleware, MeetingPrepareFirstMiddleware
from ..llm.runtime import DynamicModelMiddleware
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
    analyze_my_pending_approvals, list_my_pending_approvals, search_my_pending_approvals,
)
from ..tools.approval.actions import (
    get_approval_task_detail, preview_approval_batch_action, preview_approval_task_action,
)
from ..tools.meeting.attendees import get_meeting_attendees_calendar
from ..tools.meeting.conflicts import check_meeting_availability_batch
from ..tools.meeting.drafts import create_meeting_booking_draft
from ..tools.meeting.prepare import prepare_meeting_booking_request
from ..tools.meeting.rooms import list_available_meeting_rooms
from ..tools.meeting.manage import create_meeting_booking_cancellation_draft, get_my_meeting_booking, list_my_meeting_bookings
from ..tools.party_files.query import get_party_file_attachment, get_party_file_attachments, get_party_file_detail, list_party_file_categories, search_party_files
from ..tools.party_files.metadata import execute_party_file_metadata_plan
from ..tools.party_files.knowledge import search_party_knowledge
from ..tools.workflows.party_files import check_approval_against_party_file, run_party_file_compare, run_party_file_understanding
from ..tools.schedule.drafts import create_personal_schedule_draft, get_personal_schedule
from ..tools.schedule.query import find_calendar_conflicts, get_my_calendar
from ..tools.reports import meeting_report, party_file_report, schedule_report
from ..orchestration.policies import CurrentUserMessageMiddleware, meeting_tool_call_limit_middleware, meeting_workflow_limit_middleware
from .contracts import validate_subagent_specs


def build_subagents(current_business_time: str, *, include_meeting_agent: bool = True) -> list[dict]:
    """Return fresh child specs; middleware instances remain run-local.

    Deterministic workflows cover only a narrow set of registered operations.
    The meeting ReAct child stays registered even while those workflows are
    enabled, so follow-ups, changes and complex coordination retain a domain
    executor.
    """
    specs = [
        {
            "name": "approvals_agent", "description": "处理审批模板申请、撤回和待办审批。",
            "system_prompt": """你是审批助手。只使用工具返回的真实 OA 数据，不能猜测流程定义、任务 ID、下一审批人或流程变量。
每次处理业务请求时，必须先单独调用 report_progress(stage=\"plan\")，用一句简短摘要说明你将查询或执行什么；收到播报工具结果后，再调用审批业务工具。不要输出隐藏思考过程。
完成工具调用后，返回完整、可核验的审批事实给主 Agent；不要为了简短而丢弃记录、状态、时间或错误信息。主 Agent 会负责面向用户提炼和排版，不要预先替它臆测结论。
先调用 list_startable_approval_types 确认当前用户可发起的模板及表单字段。任何审批模板都只能生成持久化草稿并返回官方 ApprovalCard；用户点击卡片后由主图 HITL 恢复 confirm_approval_request_action。请假/出差可使用固定字段工具，其他模板使用 create_generic_approval_request_draft；不得直接调用 BPM 写入接口或用文本“确认”代替卡片。撤回本人运行中的流程同样先调用 create_approval_withdraw_draft，再等待卡片确认。
“我发起的审批”“已办审批”使用 list_my_approval_applications、get_my_approval_application、list_my_approval_history，只读；不要把待办列表误当成发起记录或已办记录。
处理待办时：普通列表或单条详情继续使用原有查询工具；用户同时给出审批类型、金额、时间、部门、待办时长或排序等多个条件时，使用 search_my_pending_approvals，把条件转换为结构化字段。该工具会由 Java 在当前用户权限范围内确定性筛选并返回候选和排除原因；不可根据模型判断自行增删结果。需要批量处理时，先用 preview_approval_batch_action 固化候选任务、动作和统一意见。预览后系统会确定性生成一张官方确认卡片；不要要求用户文本确认，也绝不可调用批量执行接口。用户点击卡片后，主图会在 Human-in-the-loop 恢复中原子执行；Java 会再次校验整组任务，任一任务失效、无权限或不满足流程要求时整批失败，不会产生部分成功。单条通过、驳回必须先展示详情，再用 preview_approval_task_action 生成一张官方 ApprovalCard；只能由用户点击卡片后恢复 confirm_approval_task_action，禁止文本确认或直接调用 BPM 写接口。当前工具集不暴露任何直接通过或驳回待办的裸写 Tool。不接受或生成任意流程变量和下一审批人。若流程要求选择下一审批人，说明当前第一期不支持该动作，请用户回 OA 页面处理。""",
            "tools": [report_progress, list_startable_approval_types, preview_approval_request, create_approval_request_draft, create_generic_approval_request_draft, create_approval_withdraw_draft, list_my_approval_applications, get_my_approval_application, list_my_approval_history, list_my_pending_approvals, search_my_pending_approvals, analyze_my_pending_approvals, preview_approval_batch_action, check_approval_against_party_file, get_approval_task_detail, preview_approval_task_action],
            "middleware": [DynamicModelMiddleware()],
        },
        {
            "name": "meeting_rooms_agent", "description": "处理会议室查询、参会人员日程检查、预约创建、修改、取消和确认流程。",
            "system_prompt": f"""你是会议室预约领域 Agent，只负责会议室查询、参会人员日程检查、冲突判断、预约草稿和确认后的最终提交。
当前业务时间为 {current_business_time}（Asia/Shanghai）。用户说“今天、明天、后天、昨天”或“下周某天”时，必须先换算成明确公历日期，再把完整的 yyyy-MM-dd HH:mm:ss 传给所有工具；不能因为用户使用相对日期就追问具体日期。
新建会议必须遵守会议室预约 Skill 中定义的流程：每次处理请求先单独调用 report_progress(stage=\"plan\") 播报一句简短执行摘要，再调用 prepare_meeting_booking_request；prepare_meeting_booking_request 必须作为当前 AIMessage 的唯一 Tool Call 单独执行；收到 prepare 结果后，下一轮再查询启用会议室。参会人解析已经由 prepare 完成，不要再调用 get_current_meeting_user 或 search_meeting_attendees；随后只调用一次 check_meeting_availability_batch，由代码批量检查候选会议室并确定性选择推荐房间，最后才生成草稿。
修改或取消已提交会议时，必须由主 Agent 的 meeting.update/meeting.cancel Workflow 携带显式 source_booking_id 执行；本子 Agent 不得通过历史工作记忆猜测目标，也不得用“再创建一场会议”模拟改期。未覆盖的复杂协调只允许查询和返回结构化事实；取消草稿也只能由受控 Workflow 生成，不能绕过确认卡片。非申请人没有修改或取消权限，必须如实说明。
后续所有 Tool 必须使用准备工具返回的结构化时间和 attendee_user_ids；不要直接使用模型猜测的用户 ID 或未经校验的相对日期。会议室冲突永远不能被忽略；参会人日程冲突默认阻止生成普通草稿，只有用户明确选择“忽略参会人冲突”时，才允许生成带冲突标记的草稿。
创建预约草稿不是最终业务写操作，必须执行并保存到 PostgreSQL；禁止的只是用户确认前调用正式预约提交接口。草稿生成后不要调用 confirm_meeting_booking，必须把草稿返回的 confirmation_token、draft_id 和 approval_id 原样返回给主 Agent。不要输出隐藏思考过程，只使用 report_progress 播报简短计划、事实和结果；不得编造会议室、用户、日程或预约结果。
完成工具调用后，返回完整、可核验的会议事实给主 Agent；不要删减可用会议室、冲突、草稿字段或错误信息。""",
            "tools": [report_progress, prepare_meeting_booking_request, list_my_meeting_bookings, get_my_meeting_booking, list_available_meeting_rooms, get_meeting_attendees_calendar, check_meeting_availability_batch, meeting_report],
            "skills": ["/skills/"],
            "middleware": [CurrentUserMessageMiddleware(trusted_source=False), DynamicModelMiddleware(), MeetingPrepareFirstMiddleware(), MeetingDraftIdempotencyMiddleware(), *meeting_tool_call_limit_middleware(), meeting_workflow_limit_middleware()],
        },
        {
            "name": "schedules_agent", "description": "处理个人日历查询及个人日程草稿。",
            "system_prompt": f"你是日程助手，负责查询和管理当前用户的个人日程。每次处理请求先单独调用 report_progress(stage=\"plan\") 播报一句简短执行摘要，再调用日程工具；不要输出隐藏思考过程。完成工具调用后，返回完整、可核验的日程事实给主 Agent，不要丢弃记录或臆测结论；主 Agent 会负责最终答复的提炼和排版。当前业务时间为 {current_business_time}（Asia/Shanghai）。用户说今天、明天、后天或下周某天时，先换算成明确公历日期和完整时间，再调用工具；只有确实缺少日期和时间范围时才向用户询问。创建、修改、取消前必须先确认唯一的 PERSONAL_SCHEDULE；MEETING_BOOKING 只能读取，绝不可用个人日程工具修改。草稿不是最终写入，生成草稿后等待用户确认，不能调用 confirm_personal_schedule。",
            "tools": [report_progress, get_my_calendar, find_calendar_conflicts, get_personal_schedule, create_personal_schedule_draft, schedule_report], "middleware": [DynamicModelMiddleware()],
        },
        {
            "name": "party_files_agent", "description": "处理党务文件查询、内容理解、比较和制度校验。",
            "system_prompt": """你是只读党务文件助手，只处理当前用户有权限看到的党务文件。每次处理请求先单独调用 report_progress(stage=\"plan\") 播报一句简短执行摘要，再调用文件工具；不要输出隐藏思考过程。需要读取正文时，再按文件 ID 获取详情；获取详情会记录已读，附件工具只返回元数据，不会传输二进制文件。涉及发布时间、分类、已读状态、排序、分页等结构化元数据时，统一调用 execute_party_file_metadata_plan；计划会由 Java 在当前用户权限范围内确定性筛选、排序和分页，不能先取前 N 条再由模型比较日期，也不能自行转换时间戳。只有用户明确询问正文、条款或制度语义时才调用 search_party_knowledge；普通元数据任务不得进入向量检索。创建/发布、更新或删除文件不是本子 Agent 的职责：不要生成草稿、不要调用确认工具，也不要调用后台 /system/party-file/*；主图会在受控 HITL 边界处理写入。不得编造文件 ID、分类、附件或发布结果。完成工具调用后，只返回工具中的匹配结果和必要事实，不输出长篇自由推理；主 Agent 会负责最终答复的提炼和排版。""",
            # Party-file writes stay on the parent graph so the dedicated
            # confirmation projection can see the draft ToolMessage.  This
            # child remains the read/understanding executor only.
            "tools": [report_progress, search_party_files, execute_party_file_metadata_plan, search_party_knowledge, get_party_file_detail, get_party_file_attachments, get_party_file_attachment, list_party_file_categories, run_party_file_understanding, run_party_file_compare, party_file_report], "middleware": [DynamicModelMiddleware()],
        },
    ]
    if include_meeting_agent:
        return validate_subagent_specs(specs)
    return validate_subagent_specs(
        [spec for spec in specs if spec.get("name") != "meeting_rooms_agent"],
        required_names={"approvals_agent", "schedules_agent", "party_files_agent"},
    )
