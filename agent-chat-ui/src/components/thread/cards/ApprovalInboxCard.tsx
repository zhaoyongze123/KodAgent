import { ClipboardList, FileText, UserRound } from "lucide-react";
import type { ApprovalInboxItem, ApprovalInboxPayload } from "@/types/agent-block";
import { displayDimensionValue, displayFieldValue } from "@/lib/card-display";

const exclusionLabels: Record<string, string> = {
  PROCESS_TYPE_MISMATCH: "审批类型不符",
  AMOUNT_UNAVAILABLE: "未找到可比较的金额字段",
  AMOUNT_MISMATCH: "金额条件不符",
  CREATED_TIME_MISMATCH: "发起时间不符",
  DEPARTMENT_MISMATCH: "发起部门不符",
  PENDING_DAYS_MISMATCH: "待办时长不符",
};

function amountLabel(value?: number): string | undefined {
  if (value == null) return undefined;
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 2,
  }).format(value);
}

function shortTime(value?: string): string | undefined {
  if (!value) return undefined;
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  return match ? `${match[2]}-${match[3]} ${match[4]}:${match[5]}` : value;
}

function CandidateRow({ item, index }: { item: ApprovalInboxItem; index: number }) {
  const details = [
    item.startUserName ? `发起人：${item.startUserName}` : undefined,
    item.departmentName ? `部门：${displayFieldValue("部门", item.departmentName, { domain: "approval" })}` : undefined,
    amountLabel(item.amount),
    item.pendingDays != null ? `已待办 ${item.pendingDays} 天` : undefined,
  ].filter((detail): detail is string => Boolean(detail));
  return (
    <li className="border-t border-slate-100 py-3 first:border-t-0 first:pt-0">
      <div className="flex items-start gap-2">
        <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-[11px] font-medium text-amber-700 tabular-nums">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <span className="text-pretty text-sm font-medium text-slate-800">{item.name || "待办任务"}</span>
            {shortTime(item.createdTime) && <span className="shrink-0 text-xs text-slate-400 tabular-nums">{shortTime(item.createdTime)}</span>}
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
            {item.processDefinitionName && <span className="flex items-center gap-1"><FileText className="size-3 shrink-0" />{displayFieldValue("审批类型", item.processDefinitionName, { domain: "approval" })}</span>}
            {item.startUserName && <span className="flex items-center gap-1"><UserRound className="size-3 shrink-0" />{details.join(" · ")}</span>}
            {!item.startUserName && details.map((detail) => <span key={detail}>{detail}</span>)}
          </div>
        </div>
      </div>
    </li>
  );
}

export function ApprovalInboxCard({ payload }: { payload: ApprovalInboxPayload }) {
  const reasonSummary = Object.entries(payload.exclusionReasonCounts)
    .map(([code, count]) => `${exclusionLabels[code] || displayDimensionValue(code, "排除原因")} ${count} 条`)
    .join("；");
  return (
    <div className="my-2 w-full max-w-xl rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-2 text-base font-semibold text-slate-800">
        <ClipboardList className="size-5 text-slate-600" />
        <span className="text-balance">审批智能分拣</span>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 border-y border-slate-100 py-3 text-center text-xs text-slate-500">
        <div><div className="text-base font-semibold text-slate-800 tabular-nums">{payload.totalPending}</div>当前待办</div>
        <div><div className="text-base font-semibold text-slate-800 tabular-nums">{payload.matchedCount}</div>符合条件</div>
        <div><div className="text-base font-semibold text-slate-800 tabular-nums">{payload.excludedCount}</div>已排除</div>
      </div>
      {payload.candidates.length === 0 ? (
        <div className="py-5 text-pretty text-center text-sm text-slate-500">当前没有符合条件的待办审批</div>
      ) : (
        <ol className="mt-3">{payload.candidates.map((item, index) => <CandidateRow key={item.taskId || index} item={item} index={index} />)}</ol>
      )}
      {reasonSummary && <div className="mt-3 border-t border-slate-100 pt-3 text-pretty text-xs leading-5 text-slate-500">排除原因：{reasonSummary}</div>}
      {payload.truncated && <div className="mt-2 text-pretty text-xs leading-5 text-amber-700">当前仅检查了前 {payload.scannedCount} 条待办，可缩小时间或类型范围继续筛选。</div>}
    </div>
  );
}
