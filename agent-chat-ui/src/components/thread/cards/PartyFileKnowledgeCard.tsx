import { BookOpen, Quote } from "lucide-react";
import type { PartyFileKnowledgePayload } from "@/types/agent-block";
import { displayDocumentType, displayStatus, displayFieldValue } from "@/lib/card-display";

export function PartyFileKnowledgeCard({ payload }: { payload: PartyFileKnowledgePayload }) {
  const evidence = payload.evidence ?? [];
  return <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className="mb-3 flex items-center gap-2 text-base font-semibold text-slate-800"><BookOpen className="size-5 text-slate-600" />文件内容理解</div>
    {payload.document?.title && <div className="mb-2 text-sm font-medium">{payload.document.title}</div>}
    {(payload.document?.docType || payload.document?.status || payload.document?.origin) && <div className="mb-3 flex flex-wrap gap-2 text-xs text-slate-500">
      {payload.document.docType && <span>{displayDocumentType(payload.document.docType)}</span>}
      {payload.document.status && <span>状态：{displayStatus(payload.document.status, { domain: "party_file" })}</span>}
      {payload.document.origin && <span>来源：{displayFieldValue("来源", payload.document.origin, { domain: "party_file" })}</span>}
    </div>}
    {payload.content && <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">{payload.content}</p>}
    {evidence.length > 0 && <div className="mt-4 grid gap-2 border-t pt-3">{evidence.map((item, index) => <div key={item.citation?.chunkId ?? index} className="rounded-md bg-slate-50 p-2 text-xs text-slate-600"><div className="mb-1 flex items-center gap-1 font-medium"><Quote className="size-3" />{item.citation?.section || "引用"}</div>{item.quote}</div>)}</div>}
  </div>;
}
