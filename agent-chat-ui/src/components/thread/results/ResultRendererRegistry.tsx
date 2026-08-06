"use client";

import { AlertTriangle, ArrowDown, ArrowUp, CheckCircle2, ClipboardCheck, FileDiff, FileText, ListFilter, Sparkles } from "lucide-react";
import { MarkdownText } from "../markdown-text";
import { ErrorCard } from "../cards/ErrorCard";
import { useClaimResultGroup, useClaimResultSource } from "./result-render-context";
import type { AgentError, AgentErrorCode } from "@/types/agent-block";
import type { ResultEnvelope, ResultKind } from "@/types/result-presentation";
import { displayDimensionValue, displayFieldValue, displayStatus, displayVerdict } from "@/lib/card-display";

type RecordValue = Record<string, unknown>;

function record(value: unknown): RecordValue {
  return value && typeof value === "object" ? (value as RecordValue) : {};
}

function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function text(value: unknown, fallback = ""): string {
  return value == null ? fallback : String(value);
}

function EmptyResult() {
  return <div className="rounded-lg border border-dashed border-slate-200 px-4 py-5 text-center text-sm text-slate-400">没有可展示的结果</div>;
}

function dataRecord(data: unknown): RecordValue {
  const root = record(data);
  return record(root.primaryData ?? root.data ?? data);
}

function resultTitle(envelope: ResultEnvelope, fallback: string): string {
  return text(envelope.presentation.title ?? envelope.presentation.headline, fallback);
}

function resultSummary(envelope: ResultEnvelope): string | undefined {
  const summary = envelope.presentation.summary;
  if (typeof summary === "string") return summary;
  return summary && typeof summary.headline === "string" ? summary.headline : undefined;
}

function ScopeSummary({ envelope, itemCount }: { envelope: ResultEnvelope; itemCount?: number }) {
  const scope = record(record(envelope.data).observedScope);
  const total = scope.totalCount ?? scope.totalPending;
  const returned = scope.returnedCount ?? itemCount;
  const sortable = scope.sortableCount;
  const parts: string[] = [];
  if (typeof total === "number") parts.push(`共 ${total} 条`);
  if (typeof returned === "number" && typeof total === "number" && returned < total) {
    parts.push(`当前展示 ${returned} 条`);
  }
  if (typeof sortable === "number") parts.push(`${sortable} 条具备可排序金额`);
  if (!parts.length) return null;
  return <p className="mb-3 text-xs text-slate-500">{parts.join("，")}。</p>;
}

function ResultShell({
  title,
  summary,
  icon: Icon,
  children,
  tone = "slate",
}: {
  title: string;
  summary?: string;
  icon: typeof FileText;
  children: React.ReactNode;
  tone?: "slate" | "amber" | "green" | "red";
}) {
  const toneClasses = {
    slate: "border-slate-200 bg-white",
    amber: "border-amber-200 bg-amber-50/40",
    green: "border-emerald-200 bg-emerald-50/40",
    red: "border-red-200 bg-red-50/40",
  }[tone];
  return (
    <section className={`my-2 w-full max-w-3xl rounded-xl border p-4 shadow-sm ${toneClasses}`}>
      <header className="mb-3 flex items-start gap-2">
        <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-600" />
        <div className="min-w-0">
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {summary && <p className="mt-1 text-xs leading-5 text-slate-600">{summary}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

function itemLabel(item: unknown, index: number): string {
  const value = record(item);
  const raw = value.title ?? value.name ?? value.processDefinitionName ?? value.label;
  if (raw == null || String(raw).trim() === "") return `第 ${index + 1} 项`;
  return typeof raw === "number" || /^-?\d+(?:\.\d+)?$/.test(String(raw).trim())
    ? displayDimensionValue(raw, "名称")
    : String(raw);
}

function itemMeta(item: unknown): string[] {
  const value = record(item);
  const entries: Array<[string, unknown]> = [
    ["金额", value.amount ?? value.totalAmount],
    ["发起人", value.startUserName ?? value.applicant],
    ["部门", value.departmentName ?? value.department],
    ["状态", value.status ?? value.state],
    ["分类", value.categoryName ?? value.category],
    ["类型", value.type ?? value.sourceType],
    ["积压", value.pendingDays == null ? undefined : `${value.pendingDays} 天`],
    ["时间", value.createdTime ?? value.startTime],
  ];
  return entries
    .filter(([, raw]) => raw != null && String(raw).trim())
    .map(([label, raw]) => `${label}：${displayFieldValue(label, raw, { domain: "generic" })}`);
}

function RankedListRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  const items = list(data.items ?? data.candidates ?? data.records);
  const observed = record(record(envelope.data).observedScope);
  return (
    <ResultShell title={resultTitle(envelope, "排序结果")} summary={resultSummary(envelope) ?? text(observed.totalCount != null ? `共 ${observed.totalCount} 条记录，展示 ${items.length} 条。` : "")} icon={ListFilter}>
      <ScopeSummary envelope={envelope} itemCount={items.length} />
      {items.length ? <ol className="grid gap-2">{items.map((item, index) => <li key={text(record(item).id ?? record(item).taskId, String(index))} className="rounded-lg border border-slate-100 bg-slate-50/70 p-3"><div className="flex gap-2 text-sm font-medium text-slate-800"><span className="text-slate-400">{index + 1}.</span><span>{itemLabel(item, index)}</span></div>{itemMeta(item).length > 0 && <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 pl-5 text-xs text-slate-500">{itemMeta(item).map((value) => <span key={value}>{value}</span>)}</div>}</li>)}</ol> : <EmptyResult />}
    </ResultShell>
  );
}

function RecordListRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  const items = list(data.items ?? data.records ?? data.list ?? data.candidates);
  return <ResultShell title={resultTitle(envelope, "查询结果")} summary={resultSummary(envelope)} icon={ClipboardCheck}><ScopeSummary envelope={envelope} itemCount={items.length} />{items.length ? <div className="grid divide-y divide-slate-100">{items.map((item, index) => <div key={text(record(item).id ?? record(item).taskId, String(index))} className="py-3 first:pt-0 last:pb-0"><div className="text-sm font-medium text-slate-800">{itemLabel(item, index)}</div>{itemMeta(item).length > 0 && <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">{itemMeta(item).map((value) => <span key={value}>{value}</span>)}</div>}</div>)}</div> : <EmptyResult />}</ResultShell>;
}

function AnalysisRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  const groups = list(data.groups ?? data.metrics ?? data.insights);
  const anomalies = list(data.anomalies ?? data.risks);
  return <ResultShell title={resultTitle(envelope, "分析结果")} summary={resultSummary(envelope) ?? text(data.summary)} icon={Sparkles}>{groups.length > 0 && <div className="grid gap-2">{groups.map((raw, index) => { const item = record(raw); const groupKey = item.key ?? item.label ?? item.name; const metricValue = item.value ?? item.count ?? item.totalAmount ?? item.maxPendingDays; return <div key={text(groupKey, String(index))} className="flex justify-between gap-3 border-b border-slate-100 py-2 text-sm"><span>{groupKey == null ? `指标 ${index + 1}` : displayDimensionValue(groupKey, "分组")}</span><span className="text-slate-500">{displayFieldValue(String(item.key ?? item.label ?? "指标"), metricValue, { domain: "generic" })}</span></div>; })}</div>}{anomalies.length > 0 && <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3"><div className="flex items-center gap-1 text-xs font-medium text-amber-800"><AlertTriangle className="size-3.5" />需要关注</div><ul className="mt-2 grid gap-1 text-xs text-amber-900">{anomalies.slice(0, 8).map((raw, index) => <li key={String(index)}>· {displayFieldValue("说明", record(raw).message ?? record(raw).reason ?? raw, { domain: "generic" })}</li>)}</ul></div>}{groups.length === 0 && anomalies.length === 0 && <EmptyResult />}</ResultShell>;
}

function WorkflowDraftRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  const fields = list(data.fields ?? data.requestFields ?? data.preview);
  return <ResultShell title={resultTitle(envelope, "操作预览")} summary={resultSummary(envelope) ?? text(data.statusText)} icon={ClipboardCheck} tone="amber"><div className="grid gap-2">{fields.map((raw, index) => { const item = record(raw); const label = text(item.label ?? item.name, `字段 ${index + 1}`); return <div key={String(index)} className="flex gap-3 border-b border-amber-100 py-2 text-sm last:border-0"><span className="w-28 shrink-0 text-amber-900/70">{label}</span><span className="text-slate-800">{displayFieldValue(label, item.value ?? item.text ?? raw, { domain: "generic" })}</span></div>; })}</div><div className="mt-3 text-xs font-medium text-amber-800">提交前请确认以上内容。</div></ResultShell>;
}

function ComparisonRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  const added = list(data.added ?? data.additions);
  const removed = list(data.removed ?? data.deletions);
  const changed = list(data.changed ?? data.modified);
  return <ResultShell title={resultTitle(envelope, "版本对比")} summary={resultSummary(envelope)} icon={FileDiff}><DiffGroup title="新增" items={added} icon={ArrowUp} tone="text-emerald-700" /><DiffGroup title="删除" items={removed} icon={ArrowDown} tone="text-red-700" /><DiffGroup title="修改" items={changed} icon={FileDiff} tone="text-amber-700" /></ResultShell>;
}

function DiffGroup({ title, items, icon: Icon, tone }: { title: string; items: unknown[]; icon: typeof ArrowUp; tone: string }) {
  if (!items.length) return null;
  return <div className="mb-3 last:mb-0"><div className={`mb-1 flex items-center gap-1 text-xs font-medium ${tone}`}><Icon className="size-3.5" />{title}（{items.length}）</div><ul className="grid gap-1 pl-5 text-xs text-slate-700">{items.slice(0, 12).map((item, index) => <li key={String(index)}>{displayFieldValue("变更内容", record(item).text ?? record(item).content ?? item, { domain: "generic" })}</li>)}</ul></div>;
}

function ApprovalCheckRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  const verdict = text(data.verdict ?? data.status, "WARN").toUpperCase();
  const tone = verdict === "PASS" || verdict === "OK" ? "green" : verdict === "BLOCK" ? "red" : "amber";
  const checks = list(data.checks ?? data.items);
  const missing = list(data.missingMaterials ?? data.missing);
  return <ResultShell title={resultTitle(envelope, "制度校验")} summary={resultSummary(envelope)} icon={CheckCircle2} tone={tone}><div className="mb-3 text-sm font-semibold">结论：{displayVerdict(verdict)}</div>{checks.length > 0 && <div className="grid gap-2">{checks.map((raw, index) => { const item = record(raw); return <div key={String(index)} className="rounded-lg border border-slate-100 bg-white/70 p-2 text-xs"><div className="font-medium text-slate-800">{text(item.requirement ?? item.label, `校验项 ${index + 1}`)}{item.status != null ? ` · ${displayStatus(item.status, { domain: "party_file" })}` : ""}</div>{typeof item.evidence === "string" && <div className="mt-1 text-slate-600">{item.evidence}</div>}</div>; })}</div>}{missing.length > 0 && <div className="mt-3 text-xs text-red-700">缺少材料：{missing.map((item) => displayFieldValue("材料", item, { domain: "party_file" })).join("、")}</div>}</ResultShell>;
}

function ClarificationRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  const fields = list(data.missingFields ?? data.questions ?? data.options);
  return <ResultShell title={resultTitle(envelope, "需要补充信息")} summary={resultSummary(envelope)} icon={FileText} tone="amber"><ul className="grid gap-2 text-sm text-slate-700">{fields.length ? fields.map((item, index) => <li key={String(index)} className="rounded-md bg-amber-50 px-3 py-2">{displayFieldValue("需补充字段", record(item).label ?? record(item).question ?? item, { domain: "generic" })}</li>) : <li>请补充任务所需的信息。</li>}</ul></ResultShell>;
}

function ErrorResultRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  const error: AgentError = { code: text(data.code ?? "UNKNOWN") as AgentErrorCode, message: text(data.message ?? envelope.presentation.summary, "处理请求时发生异常"), retryable: data.retryable === true };
  return <ErrorCard error={error} />;
}

function RichTextRenderer({ envelope }: { envelope: ResultEnvelope }) {
  const data = dataRecord(envelope.data);
  return <div className="my-2 w-full max-w-3xl"><MarkdownText>{text(data.markdown ?? data.text ?? data.content ?? envelope.presentation.summary)}</MarkdownText></div>;
}

const RESULT_RENDERERS: Record<ResultKind, React.ComponentType<{ envelope: ResultEnvelope }>> = {
  ranked_list: RankedListRenderer,
  record_list: RecordListRenderer,
  analysis: AnalysisRenderer,
  workflow_draft: WorkflowDraftRenderer,
  comparison: ComparisonRenderer,
  approval_check: ApprovalCheckRenderer,
  clarification: ClarificationRenderer,
  error: ErrorResultRenderer,
  rich_text: RichTextRenderer,
};

export function ResultRendererRegistry({ envelope }: { envelope: ResultEnvelope }) {
  const sourceId = envelope.sourceResultId ?? envelope.presentation.sourceResultId;
  const sourceClaimed = useClaimResultSource(sourceId, envelope.messageId);
  const groupClaimed = useClaimResultGroup(
    envelope.resultGroupId ?? envelope.presentation.resultGroupId,
    envelope.messageId,
  );
  if (!sourceClaimed || !groupClaimed) return null;
  const Renderer = RESULT_RENDERERS[envelope.presentation.resultKind as ResultKind] ?? RichTextRenderer;
  return <Renderer envelope={envelope} />;
}

export function resultRendererKinds(): ResultKind[] {
  return Object.keys(RESULT_RENDERERS) as ResultKind[];
}
