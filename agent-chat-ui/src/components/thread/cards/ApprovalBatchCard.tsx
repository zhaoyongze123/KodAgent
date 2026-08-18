import { CheckCircle2, ClipboardCheck, Clock3, XCircle } from "lucide-react";
import type { ApprovalBatchPayload } from "@/types/agent-block";
import { displayBatchStatus, displayOperation } from "@/lib/card-display";

export function ApprovalBatchCard({ payload, result = false }: { payload: ApprovalBatchPayload; result?: boolean }) {
  const items = result ? payload.results ?? [] : payload.tasks ?? [];
  const action = payload.action === "REJECT" ? "驳回" : displayOperation(payload.action || "APPROVE");
  return (
    <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center gap-2 text-base font-semibold text-slate-800">
        <ClipboardCheck className="size-5 text-slate-600" />
        <span>{result ? `批量${action}结果` : `批量${action}预览`}</span>
        <span className="ml-auto text-xs font-normal text-slate-500">{payload.taskCount ?? items.length} 条</span>
      </div>
      {!result && <p className="mb-3 text-sm text-amber-700">已生成不可变的操作预览。请使用下方确认卡片完成一次确认；文本回复不会执行该操作。</p>}
      {payload.reason && <p className="mb-3 text-xs text-slate-500">统一意见：{payload.reason}</p>}
      <ol className="flex flex-col gap-2">
        {items.map((item, index) => {
          const batchItem = item as { taskId?: string; name?: string; status?: string; message?: string };
          const status = batchItem.status ?? "READY";
          const Icon = status === "SUCCESS" ? CheckCircle2 : status === "FAILED" ? XCircle : Clock3;
          return <li key={item.taskId ?? index} className="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
            <Icon className={status === "SUCCESS" ? "size-4 text-emerald-600" : status === "FAILED" ? "size-4 text-rose-600" : "size-4 text-amber-600"} />
            <span className="min-w-0 flex-1 truncate">{batchItem.name || "待办任务"}</span>
            <span className="shrink-0 text-xs text-slate-500">{displayBatchStatus(status)}</span>
            {batchItem.message && <span className="text-xs text-slate-500">{batchItem.message}</span>}
          </li>;
        })}
      </ol>
    </div>
  );
}
