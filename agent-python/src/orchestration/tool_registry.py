"""组装 OA 主图时使用的工具集合。

本文件仅注册图启动时必须认识的工具，并按工作流开关暴露兼容集合；它不决定某一
回合模型实际可见的工具。运行时工具范围由 ``PlanToolProjectionMiddleware`` 和
WorkOrder 授权契约收紧，避免“注册过”被误解为“本次可以调用”。
"""

from ..tools.approval.templates import list_startable_approval_types, preview_approval_request
from ..tools.approval.requests import (
    create_approval_request_draft,
    create_generic_approval_request_draft,
    create_approval_withdraw_draft,
    confirm_approval_request_action,
    confirm_approval_withdraw_action,
)
from ..tools.approval.history import (
    list_my_approval_applications,
    get_my_approval_application,
    list_my_approval_history,
)
from ..tools.approval.pending import (
    analyze_my_pending_approvals,
    list_my_pending_approvals,
    run_approval_query_plan,
    search_my_pending_approvals,
)
from ..tools.approval.actions import (
    confirm_approval_batch_action,
    get_approval_task_detail,
    preview_approval_batch_action,
    preview_approval_task_action,
    confirm_approval_task_action,
)
from ..tools.meeting.attendees import (
    get_current_meeting_user,
    get_meeting_attendees_calendar,
    search_meeting_attendees,
)
from ..tools.meeting.booking import confirm_meeting_booking
from ..tools.meeting.conflicts import (
    check_meeting_availability,
    check_meeting_availability_batch,
    check_meeting_room_conflict,
)
from ..tools.meeting.drafts import create_meeting_booking_draft
from ..tools.meeting.prepare import prepare_meeting_booking_request
from ..tools.meeting.rooms import list_available_meeting_rooms
from ..tools.meeting.manage import create_meeting_booking_cancellation_draft, get_my_meeting_booking, list_my_meeting_bookings
from ..tools.party_files.query import (
    get_party_file_attachments,
    get_party_file_attachment,
    get_party_file_detail,
    list_party_file_categories,
    search_party_files,
)
from ..tools.party_files.metadata import execute_party_file_metadata_plan
from ..tools.party_files.knowledge import check_party_knowledge_health, search_party_knowledge
from ..tools.party_files.manage import create_party_file_draft, update_party_file_draft, delete_party_file_draft, get_manage_party_file, confirm_create_party_file, confirm_update_party_file, confirm_delete_party_file
from ..tools.reports import approval_report, meeting_report, party_file_report, schedule_report
from ..tools.workflows.party_files import check_approval_against_party_file, run_party_file_compare, run_party_file_understanding
from ..tools.schedule.drafts import (
    confirm_personal_schedule,
    create_personal_schedule_draft,
    get_personal_schedule,
)
from ..tools.schedule.query import find_calendar_conflicts, get_my_calendar
from ..tools.common import (
    report_progress,
    route_conversation,
)
from ..tools.workflows.meeting_booking import run_meeting_booking_workflow
from ..tools.workflows.personal_schedule import run_personal_schedule_workflow
from ..tools.workflows.approval import run_approval_write_workflow
from ..tools.workflows.party_file_write import run_party_file_write_workflow
from ..workflows.registry import workflow_registry


def meeting_workflow_enabled() -> bool:
    """返回确定性会议工作流是否可作为当前部署的执行路径。

    是否使用由工作流注册表决定；关闭时是运维回滚开关，不能靠模型提示词改变。
    """
    return workflow_registry.enabled("meeting_booking")


def personal_schedule_workflow_enabled() -> bool:
    return workflow_registry.enabled("personal_schedule")


def party_knowledge_workflow_enabled() -> bool:
    return workflow_registry.enabled("party_file_understanding")


def party_compare_workflow_enabled() -> bool:
    return workflow_registry.enabled("party_file_compare")


def party_approval_check_enabled() -> bool:
    return workflow_registry.enabled("party_file_approval_check")


def business_tools() -> list:
    """返回图启动时必须注册工具契约的完整集合。"""
    return [
        report_progress,
        route_conversation,
        prepare_meeting_booking_request,
        list_my_meeting_bookings,
        get_my_meeting_booking,
        create_meeting_booking_cancellation_draft,
        list_available_meeting_rooms,
        search_meeting_attendees,
        get_current_meeting_user,
        get_meeting_attendees_calendar,
        check_meeting_room_conflict,
        check_meeting_availability,
        check_meeting_availability_batch,
        create_meeting_booking_draft,
        confirm_meeting_booking,
        list_startable_approval_types,
        preview_approval_request,
        create_approval_request_draft,
        create_generic_approval_request_draft,
        create_approval_withdraw_draft,
        confirm_approval_request_action,
        confirm_approval_withdraw_action,
        list_my_pending_approvals,
        search_my_pending_approvals,
        analyze_my_pending_approvals,
        run_approval_query_plan,
        preview_approval_batch_action,
        confirm_approval_batch_action,
        confirm_approval_task_action,
        list_my_approval_applications,
        get_my_approval_application,
        list_my_approval_history,
        get_approval_task_detail,
        preview_approval_task_action,
        get_my_calendar,
        find_calendar_conflicts,
        get_personal_schedule,
        create_personal_schedule_draft,
        confirm_personal_schedule,
        search_party_files,
        get_manage_party_file,
        create_party_file_draft,
        update_party_file_draft,
        delete_party_file_draft,
        confirm_create_party_file,
        confirm_update_party_file,
        confirm_delete_party_file,
        get_party_file_detail,
        get_party_file_attachments,
        get_party_file_attachment,
        execute_party_file_metadata_plan,
        list_party_file_categories,
        search_party_knowledge,
        check_party_knowledge_health,
        run_party_file_understanding,
        run_party_file_compare,
        check_approval_against_party_file,
        run_meeting_booking_workflow,
        run_personal_schedule_workflow,
        run_approval_write_workflow,
        run_party_file_write_workflow,
        meeting_report,
        schedule_report,
        party_file_report,
        approval_report,
    ]


def main_tools() -> list:
    """Return control-plane tools exposed on the parent graph.

    A normal business executor belongs to its domain child and is reached only
    through a code-owned WorkOrder.  Root confirmation tools are the one
    deliberate exception: LangGraph's interrupt/resume lifecycle is a shared
    control-plane boundary, not an action the parent model may freely choose.
    """
    return [
        report_progress,
        route_conversation,
        confirm_meeting_booking,
        confirm_personal_schedule,
        confirm_approval_request_action,
        confirm_approval_withdraw_action,
        confirm_approval_batch_action,
        confirm_approval_task_action,
        confirm_create_party_file,
        confirm_update_party_file,
        confirm_delete_party_file,
    ]
