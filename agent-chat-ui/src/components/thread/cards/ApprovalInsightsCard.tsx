import { AlertTriangle, BarChart3 } from "lucide-react";
import type { ApprovalInsightPayload } from "@/types/agent-block";
import { displayDimensionValue, displayFieldValue } from "@/lib/card-display";

export function ApprovalInsightsCard({ payload }: { payload: ApprovalInsightPayload }) {
  return <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className="mb-3 flex items-center gap-2 text-base font-semibold text-slate-800"><BarChart3 className="size-5 text-slate-600" />审批分析</div>
    {payload.summary && <p className="mb-3 text-sm text-slate-600">{payload.summary}</p>}
    {(payload.groups ?? []).map((group, index) => <div key={group.key ?? index} className="flex justify-between border-b border-slate-100 py-2 text-sm"><span>{group.key == null ? "未分组" : displayDimensionValue(group.key, "分组")}</span><span className="text-slate-500">{group.count ?? 0} 条 · 最久 {group.maxPendingDays ?? 0} 天</span></div>)}
    {(payload.anomalies ?? []).length > 0 && <div className="mt-4"><div className="mb-2 flex items-center gap-1 text-sm font-medium text-amber-700"><AlertTriangle className="size-4" />需要关注</div>{payload.anomalies!.map((item, index) => <div key={item.taskId ?? index} className="mb-1 text-xs text-slate-600">{item.processName ? displayFieldValue("审批类型", item.processName, { domain: "approval" }) : "审批"} · {item.startUserName || "未知发起人"}：{(item.reasons ?? []).join("、")}</div>)}</div>}
  </div>;
}
