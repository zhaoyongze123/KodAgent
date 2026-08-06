import { ClipboardCheck } from "lucide-react";
import type { ApprovalWorkflowPayload } from "@/types/agent-block";
import { displayFieldValue } from "@/lib/card-display";

export function ApprovalWorkflowCard({ payload }: { payload: ApprovalWorkflowPayload }) {
  return (
    <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-4 flex items-center gap-2 text-base font-semibold text-slate-800">
        <ClipboardCheck className="size-5 text-slate-600" />
        <span>{payload.title}</span>
      </div>
      <div className="grid gap-2.5 text-sm">
        {payload.fields.length === 0 ? (
          <div className="text-slate-500">当前没有可展示的数据</div>
        ) : payload.fields.map((field) => (
          <div key={field.label} className="flex gap-3">
            <span className="w-20 shrink-0 text-slate-500">{field.label}</span>
            <span className="text-slate-800">
              {displayFieldValue(field.label, field.value, { domain: "approval" })}
            </span>
          </div>
        ))}
      </div>
      {payload.statusText && <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">{payload.statusText}</div>}
    </div>
  );
}
