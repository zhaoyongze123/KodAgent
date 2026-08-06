import { Check, ClipboardCheck, FileText, Loader2, User, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import type { TodoItem, TodoPayload } from "@/types/agent-block";
import { displayFieldValue } from "@/lib/card-display";

function shortTime(value?: string): string {
  if (!value) return "";
  // "yyyy-MM-dd HH:mm:ss" -> "MM-dd HH:mm"
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/);
  if (match) return `${match[2]}-${match[3]} ${match[4]}:${match[5]}`;
  return value;
}

export function PendingApprovalsCard({ payload }: { payload: TodoPayload }) {
  const items = payload.items ?? [];
  const total = payload.total ?? items.length;
  const [pendingAction, setPendingAction] = useState<{
    taskId: string;
    action: "approve" | "reject";
  } | null>(null);
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [settledTaskIds, setSettledTaskIds] = useState<Set<string>>(new Set());

  const submitAction = async () => {
    if (!pendingAction || submitting) return;
    if (pendingAction.action === "reject" && !reason.trim()) {
      toast.error("请填写驳回原因", { richColors: true, closeButton: true });
      return;
    }
    setSubmitting(true);
    try {
      const response = await fetch(
        `/api/agent-tasks/${encodeURIComponent(pendingAction.taskId)}/${pendingAction.action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ reason: reason.trim() || "同意" }),
        },
      );
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body?.msg ?? body?.message ?? body?.error ?? "操作未生效");
      }
      setSettledTaskIds((previous) => new Set(previous).add(pendingAction.taskId));
      toast.success(pendingAction.action === "approve" ? "审批已通过" : "审批已驳回", {
        richColors: true,
        closeButton: true,
      });
      setPendingAction(null);
      setReason("");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "操作失败，请稍后重试", {
        richColors: true,
        closeButton: true,
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-base font-semibold text-slate-800">
        <ClipboardCheck className="size-5 text-slate-600" />
        <span>待办审批</span>
        <span className="ml-auto text-xs font-normal text-slate-500">
          共 {total} 条
        </span>
      </div>

      {items.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 px-4 py-6 text-center text-sm text-slate-400">
          当前没有需要你处理的待办审批
        </div>
      ) : (
        <ol className="flex flex-col gap-2.5">
          {items.map((item: TodoItem, index) => (
            <li
              key={item.taskId ?? `${item.name ?? "task"}-${index}`}
              className="rounded-lg border border-slate-100 bg-slate-50/60 p-3"
            >
              <div className="flex items-start gap-2">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-amber-100 text-[11px] font-medium text-amber-700">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1 text-sm font-medium text-slate-800">
                  {item.name || "待办任务"}
                </span>
                {item.createdTime && (
                  <span className="shrink-0 text-[11px] text-slate-400">
                    {shortTime(item.createdTime)}
                  </span>
                )}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 pl-7 text-xs text-slate-500">
                {item.processDefinitionName && (
                  <span className="flex items-center gap-1">
                    <FileText className="size-3 shrink-0" />
                    {displayFieldValue("审批类型", item.processDefinitionName, { domain: "approval" })}
                  </span>
                )}
                {item.startUserName && (
                  <span className="flex items-center gap-1">
                    <User className="size-3 shrink-0" />
                    发起人：{item.startUserName}
                  </span>
                )}
              </div>
              {item.taskId && !settledTaskIds.has(item.taskId) && (
                <div className="mt-3 flex gap-2 pl-7">
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setPendingAction({ taskId: item.taskId!, action: "approve" });
                      setReason("同意");
                    }}
                  >
                    <Check className="size-3.5" /> 通过
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setPendingAction({ taskId: item.taskId!, action: "reject" });
                      setReason("");
                    }}
                  >
                    <X className="size-3.5" /> 驳回
                  </Button>
                </div>
              )}
              {item.taskId && settledTaskIds.has(item.taskId) && (
                <div className="mt-3 pl-7 text-xs font-medium text-emerald-700">本次已处理，刷新后将同步最新待办。</div>
              )}
            </li>
          ))}
        </ol>
      )}
      {pendingAction && (
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3">
          <div className="text-sm font-medium text-slate-800">
            确认{pendingAction.action === "approve" ? "通过" : "驳回"}该待办？
          </div>
          <textarea
            className="mt-2 min-h-20 w-full rounded-md border border-slate-200 bg-white px-3 py-2 text-sm outline-none focus:border-slate-400"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            placeholder={pendingAction.action === "approve" ? "审批意见（可修改）" : "请填写驳回原因"}
          />
          <div className="mt-3 flex justify-end gap-2">
            <Button type="button" size="sm" variant="outline" disabled={submitting} onClick={() => setPendingAction(null)}>
              取消
            </Button>
            <Button type="button" size="sm" disabled={submitting} onClick={submitAction}>
              {submitting ? <Loader2 className="size-3.5 animate-spin" /> : null}
              确认{pendingAction.action === "approve" ? "通过" : "驳回"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
