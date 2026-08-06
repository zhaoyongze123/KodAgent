import { GitCompareArrows } from "lucide-react";
import type { PartyFileComparePayload } from "@/types/agent-block";
import { displayDocumentType, displayStatus } from "@/lib/card-display";

export function PartyFileCompareCard({ payload }: { payload: PartyFileComparePayload }) {
  return <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className="mb-3 flex items-center gap-2 text-base font-semibold text-slate-800"><GitCompareArrows className="size-5 text-slate-600" />文件版本对比 <span className="ml-auto text-xs font-normal text-slate-500">{payload.changedLineCount ?? 0} 处变化</span></div>
    <div className="mb-3 flex flex-wrap gap-2 text-xs text-slate-500">
      {payload.left?.title && <span>旧版：{payload.left.title}</span>}
      {payload.right?.title && <span>新版：{payload.right.title}</span>}
      {payload.left?.docType && <span>文件类型：{displayDocumentType(payload.left.docType)}</span>}
      {payload.status && <span>状态：{displayStatus(payload.status, { domain: "party_file" })}</span>}
    </div>
    {payload.added?.length > 0 && <section className="mb-3"><h4 className="mb-1 text-xs font-medium text-emerald-700">新增</h4>{payload.added.map((line, i) => <div key={i} className="text-xs text-slate-700">+ {line}</div>)}</section>}
    {payload.removed?.length > 0 && <section><h4 className="mb-1 text-xs font-medium text-rose-700">删除</h4>{payload.removed.map((line, i) => <div key={i} className="text-xs text-slate-700">- {line}</div>)}</section>}
  </div>;
}
