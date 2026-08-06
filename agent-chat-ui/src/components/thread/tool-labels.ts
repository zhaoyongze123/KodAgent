export const TOOL_LABELS: Record<string, string> = {
  report_progress: "播报执行计划",
  list_available_meeting_rooms: "查询可用会议室",
  search_meeting_attendees: "查询参会人员",
  get_current_meeting_user: "获取当前用户身份",
  get_meeting_attendees_calendar: "查询参会人日程",
  check_meeting_room_conflict: "检查会议室冲突",
  check_meeting_availability: "统一检查可预约性",
  check_meeting_availability_batch: "批量检查会议室可预约性",
  prepare_meeting_booking_request: "解析会议预约请求",
  create_meeting_booking_draft: "生成预约草稿",
  confirm_meeting_booking: "提交会议室预约",
  preview_approval_task_action: "生成单条审批确认卡",
  confirm_approval_task_action: "执行单条审批",
  meeting_report: "会议报表",
  schedule_report: "日程报表",
  party_file_report: "党务文件报表",
  task: "处理子 Agent 任务",
  list_my_pending_approvals: "查询我的待办审批",
  get_my_calendar: "查询我的日历",
  search_party_files: "搜索党务文件",
  get_party_file_detail: "读取党务文件详情",
  get_party_file_attachment: "获取文件附件信息",
  list_party_file_categories: "查询党务文件分类",
};

export function toolLabel(name?: string | null): string {
  return (name && TOOL_LABELS[name]) || name || "业务工具";
}

export function inferToolName(text: string): string {
  if (
    text.includes("check_meeting_availability_batch") ||
    text.includes("批量检查会议室") ||
    text.includes("批量可预约性")
  ) {
    return "check_meeting_availability_batch";
  }
  if (
    text.includes("prepare_meeting_booking_request") ||
    text.includes("解析会议预约") ||
    text.includes("准备会议预约")
  ) {
    return "prepare_meeting_booking_request";
  }
  if (text.includes("个人日历") || text.includes("日历查询")) {
    return "get_my_calendar";
  }
  if (text.includes("待办") || text.includes("审批查询")) {
    return "list_my_pending_approvals";
  }
  if (text.includes("党务文件分类")) return "list_party_file_categories";
  if (text.includes("党务文件详情")) return "get_party_file_detail";
  if (text.includes("附件信息")) return "get_party_file_attachment";
  if (text.includes("党务文件")) return "search_party_files";
  if (text.includes("参会人员") && text.includes("查询")) {
    return "search_meeting_attendees";
  }
  if (text.includes("当前用户身份")) return "get_current_meeting_user";
  if (text.includes("可用会议室")) return "list_available_meeting_rooms";
  if (text.includes("参会人员安排")) {
    return "get_meeting_attendees_calendar";
  }
  if (text.includes("统一检查会议室") || text.includes("可预约性检查")) {
    return "check_meeting_availability";
  }
  if (text.includes("会议室时间冲突")) return "check_meeting_room_conflict";
  if (text.includes("提交会议室预约")) return "confirm_meeting_booking";
  return "";
}
