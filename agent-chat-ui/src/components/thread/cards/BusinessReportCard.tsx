import { BarChart3 } from "lucide-react";
import type { BusinessReportPayload } from "@/types/agent-block";
import { displayDimensionValue, displaySourceType } from "@/lib/card-display";

function label(type?: string) {
  return type === "meeting" ? "会议报表" : type === "schedule" ? "日程报表" : type === "party_file" ? "党务文件报表" : type === "approval" ? "审批报表" : displaySourceType(type || "业务");
}

function distribution(values?: Record<string, number>) {
  return Object.entries(values ?? {}).slice(0, 8);
}

export function BusinessReportCard({ payload }: { payload: BusinessReportPayload }) {
  const total = payload.total ?? payload.items?.length ?? payload.events?.length ?? 0;
  const metric = payload.reportType === "approval"
    ? `待办 ${total} 条 · 有金额 ${payload.amountCount ?? 0} 条 · 金额合计 ${payload.totalAmount ?? 0}`
    : payload.reportType === "meeting"
    ? `总计 ${total} 场 · ${payload.totalMinutes ?? 0} 分钟`
    : payload.reportType === "schedule"
      ? `总计 ${total} 项 · 占用 ${payload.busyMinutes ?? 0} 分钟 · 冲突 ${payload.conflictCount ?? 0} 个`
      : `总计 ${total} 份 · 已读 ${payload.readCount ?? 0} · 未读 ${payload.unreadCount ?? 0}`;
  const groups = payload.byProcess ?? payload.byDepartment ?? payload.byRoom ?? payload.bySource ?? payload.byCategory ?? payload.byDay;
  const dimension = payload.byProcess ? "审批流程" : payload.byDepartment ? "部门名称" : payload.byRoom ? "会议室名称" : payload.bySource ? "来源类型" : payload.byCategory ? "分类名称" : "日期";
  return (
    <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-base font-semibold text-slate-800"><BarChart3 className="size-5 text-slate-600" />{label(payload.reportType)}</div>
      <div className="text-sm text-slate-600">{metric}</div>
      {(payload.startTime || payload.endTime) && <div className="mt-1 text-xs text-slate-400">范围：{payload.startTime ?? ""} 至 {payload.endTime ?? ""}</div>}
      <div className="mt-4 grid gap-2 text-sm">
        {distribution(groups).map(([key, value]) => <div key={key} className="flex justify-between border-b border-slate-100 py-1.5"><span>{displayDimensionValue(key, dimension)}</span><span className="text-slate-500">{value}</span></div>)}
      </div>
    </div>
  );
}
