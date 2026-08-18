import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import type { PartyFileCompliancePayload } from "@/types/agent-block";
import { displayStatus, displayVerdict } from "@/lib/card-display";

export function PartyFileComplianceCard({ payload }: { payload: PartyFileCompliancePayload }) {
  const verdict = String(payload.verdict || "WARN").toUpperCase();
  const blocked = verdict === "BLOCK";
  const passed = verdict === "PASS";
  const Icon = blocked ? ShieldAlert : passed ? CheckCircle2 : AlertTriangle;
  const tone = blocked ? "text-rose-700" : passed ? "text-emerald-700" : "text-amber-700";
  return <div className="my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
    <div className={`mb-3 flex items-center gap-2 text-base font-semibold ${tone}`}><Icon className="size-5" />制度符合性校验 <span className="ml-auto text-xs font-normal">{displayVerdict(verdict)}</span></div>
    {payload.checks?.map((check, index) => <div key={index} className="border-b border-slate-100 py-2 text-xs"><div className="font-medium text-slate-800">{check.requirement || "制度要求"} · {displayStatus(check.status || "WARN", { domain: "party_file" })}</div><div className="mt-1 text-slate-500">{check.evidence}</div></div>)}
    {payload.missingMaterials?.length ? <div className="mt-3 text-xs text-rose-700">缺失材料：{payload.missingMaterials.join("、")}</div> : null}
  </div>;
}
