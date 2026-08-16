"use client";

import { useState } from "react";
import { BarChart3, CheckCircle2, Download, FileText, FolderKanban, ListChecks, RefreshCw, Users } from "lucide-react";
import type { ProjectCardKind, ProjectPayload } from "@/types/agent-block";

function text(value: unknown, fallback = "-") {
  return value == null || value === "" ? fallback : String(value);
}

function number(value: unknown) {
  return typeof value === "number" ? value : Number(value ?? 0) || 0;
}

function percent(value: unknown) {
  const raw = number(value);
  return `${Math.round((raw <= 1 ? raw * 100 : raw) * 10) / 10}%`;
}

function shell(title: string, icon: React.ReactNode, children: React.ReactNode) {
  return <section className="my-2 w-full max-w-2xl rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
    <header className="mb-2 flex items-center gap-2 border-b border-slate-100 pb-2 text-sm font-semibold text-slate-800">{icon}{title}</header>
    {children}
  </section>;
}

function kpi(label: string, value: React.ReactNode) {
  return <div className="rounded-md border border-slate-100 bg-slate-50 px-2 py-1.5"><div className="text-[11px] text-slate-500">{label}</div><div className="mt-0.5 text-sm font-semibold text-slate-800">{value}</div></div>;
}

/**
 * 报告下载只能走当前站点的受控代理。
 *
 * ``downloadPath`` 可能来自旧版本持久化消息，不能据此信任任意 URL；前端仅接受
 * 合法的 Java 报告编号和格式，并让 Next.js 代理在下载时重新携带当前用户身份。
 */
function reportDownload(item: Record<string, unknown>) {
  const reportId = text(item.reportId, "").trim();
  const format = text(item.format, "").trim().toLowerCase();
  if (!/^[0-9a-f-]{16,80}$/i.test(reportId) || !["docx", "xlsx"].includes(format)) {
    return undefined;
  }
  return {
    href: `/api/project-reports/${encodeURIComponent(reportId)}?format=${format}`,
    format,
    filename: text(item.filename, `项目报告.${format}`),
  };
}

function projectDocumentTitle(documentType: unknown) {
  switch (text(documentType, "").toUpperCase()) {
    case "WEEKLY_REPORT": return "项目周报";
    case "MONTHLY_REPORT": return "项目月报";
    case "PROGRESS_REPORT": return "项目进度报告";
    default: return "项目分析报告";
  }
}

/** 项目领域的结构化结果卡片；只展示 Java 返回的事实，不在前端重算业务数字。 */
export function ProjectCard({ kind, payload }: { kind: ProjectCardKind; payload: ProjectPayload }) {
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState("");
  const analysis = payload.analysis && typeof payload.analysis === "object" ? payload.analysis as ProjectPayload : payload;
  const project = analysis.project && typeof analysis.project === "object" ? analysis.project as Record<string, unknown> : analysis;
  const kpis = analysis.kpis && typeof analysis.kpis === "object" ? analysis.kpis as Record<string, unknown> : {};
  const projectName = text(project.name, "项目");
  if (kind === "project_list") {
    const items = Array.isArray(payload.items) ? payload.items as Array<Record<string, unknown>> : [];
    return shell("可参与项目", <FolderKanban className="size-4 text-slate-500" />, <div className="divide-y divide-slate-100 text-xs">{items.length ? items.map((item, index) => <div key={String(item.projectID ?? index)} className="flex items-center justify-between gap-3 py-2"><div><div className="font-medium text-slate-800">{text(item.name, "未命名项目")}</div><div className="mt-0.5 text-[11px] text-slate-500">项目编号 {text(item.projectID)} · 角色 {text(item.role)}</div></div><span className="shrink-0 text-[11px] text-slate-500">更新于 {text(item.updatedAt)}</span></div>) : <div className="py-3 text-slate-500">当前没有可参与的项目</div>}</div>);
  }
  if (kind === "project_knowledge") {
    const hits = Array.isArray(payload.hits) ? payload.hits as Array<Record<string, unknown>> : [];
    return shell("项目资料与制度依据", <FileText className="size-4 text-slate-500" />, <div><div className="mb-2 text-xs text-slate-500">检索：{text(payload.query)} · {text(payload.retrievalMode, "全文检索")}</div>{hits.length ? <div className="space-y-2">{hits.map((hit, index) => <article key={String(hit.chunkId ?? index)} className="rounded-md border border-slate-100 px-2.5 py-2"><div className="flex items-center justify-between gap-2 text-xs font-medium text-slate-800"><span>{text(hit.name, "未命名资料")}</span><span className="text-[11px] font-normal text-slate-400">{text(hit.sourceType)}</span></div><p className="mt-1 line-clamp-3 text-xs leading-5 text-slate-600">{text(hit.content)}</p><div className="mt-1 text-[11px] text-slate-400">文件编号 {text(hit.fileId)} · 第 {number(hit.ordinal) + 1} 段</div></article>)}</div> : <div className="py-3 text-xs text-slate-500">没有找到当前权限范围内的资料证据</div>}</div>);
  }
  if (kind === "project_report") {
    const exportsList = Array.isArray(payload.exports) ? payload.exports as Array<Record<string, unknown>> : [];
    const title = projectDocumentTitle(payload.documentType);
    return shell(title, <BarChart3 className="size-4 text-slate-500" />, <div><div className="mb-2 text-sm font-medium text-slate-800">{projectName}</div><div className="mb-3 text-xs text-slate-500">附件内容与本次回答同步生成，下载权限由当前项目成员身份复核。</div><div className="flex flex-wrap gap-2">{exportsList.map((item, index) => {
      const download = reportDownload(item);
      return download ? <a key={`${download.format}-${index}`} href={download.href} download={download.filename} aria-label={`下载 ${download.filename}`} className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:border-slate-400 hover:bg-slate-50"><Download className="size-3.5" />下载 {download.format.toUpperCase()}</a> : <span key={String(item.format ?? index)} className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-2.5 py-1.5 text-xs text-slate-400">导出文件暂不可用</span>;
    })}</div></div>);
  }
  if (kind === "project_documents") {
    const items = Array.isArray(payload.items) ? payload.items as Array<Record<string, unknown>> : [];
    const projectId = text(payload.projectID, text(project.projectID, ""));
    const canSync = text(payload.role, text(project.role, "")) === "admin" && /^\d+$/.test(projectId);
    const sync = async () => {
      if (!canSync || syncing) return;
      setSyncing(true);
      setSyncMessage("");
      try {
        const response = await fetch(`/api/project-documents/${encodeURIComponent(projectId)}/sync`, { method: "POST" });
        const body = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(text(body.error, "资料同步失败"));
        setSyncMessage(`已提交同步：扫描 ${number(body.scanned)} 个文件`);
      } catch (error) {
        setSyncMessage(error instanceof Error ? error.message : "资料同步失败");
      } finally {
        setSyncing(false);
      }
    };
    return shell(`${projectName} · 项目资料`, <FileText className="size-4 text-slate-500" />, <div><div className="mb-2 flex items-center justify-between gap-2 text-[11px] text-slate-500"><span>项目资料目录 · {items.length} 个文件</span>{canSync && <button type="button" onClick={() => void sync()} disabled={syncing} className="inline-flex items-center gap-1 rounded border border-slate-200 px-2 py-1 text-[11px] font-medium text-slate-600 hover:border-slate-400 disabled:cursor-not-allowed disabled:opacity-50"><RefreshCw className={`size-3 ${syncing ? "animate-spin" : ""}`} />{syncing ? "同步中" : "立即同步"}</button>}</div><div className="divide-y divide-slate-100 text-xs">{items.length ? items.map((item, index) => <div key={String(item.fileID ?? index)} className="flex items-center justify-between gap-3 py-1.5"><span className="truncate text-slate-700">{text(item.name, "未命名资料")}</span><span className="shrink-0 text-[11px] text-slate-400">{item.supported === false ? "待处理" : "可检索"} · {text(item.version, text(item.contentHash))}</span></div>) : <div className="py-3 text-slate-500">项目资料目录为空或当前用户无权查看</div>}</div>{syncMessage && <div className="mt-2 text-[11px] text-slate-500">{syncMessage}</div>}</div>);
  }
  if (kind === "project_tasks") {
    const items = Array.isArray(payload.tasks) ? payload.tasks as Array<Record<string, unknown>> : [];
    return shell(`${projectName} · 任务进度`, <ListChecks className="size-4 text-slate-500" />, <div><div className="mb-2 grid grid-cols-2 gap-1.5 sm:grid-cols-4">{kpi("有效任务", number((payload.summary as Record<string, unknown> | undefined)?.total))}{kpi("已完成", number((payload.summary as Record<string, unknown> | undefined)?.completed))}{kpi("逾期", number((payload.summary as Record<string, unknown> | undefined)?.overdue))}{kpi("无负责人", number((payload.summary as Record<string, unknown> | undefined)?.withoutOwner))}</div><div className="text-xs text-slate-500">当前返回 {items.length} 条任务，具体可见范围由项目插件权限规则确定。</div></div>);
  }
  if (kind === "project_activity") {
    const items = Array.isArray(payload.items) ? payload.items as Array<Record<string, unknown>> : [];
    return shell(`${projectName} · 近期动态`, <CheckCircle2 className="size-4 text-slate-500" />, <div className="divide-y divide-slate-100 text-xs">{items.slice(0, 12).map((item, index) => <div key={String(item.id ?? index)} className="py-1.5"><div className="text-slate-700">{text(item.description, "项目活动")}</div><div className="mt-0.5 text-[11px] text-slate-400">{text(item.createdAt)} · 任务 {text(item.taskID, "项目级")}</div></div>)}{!items.length && <div className="py-3 text-slate-500">近期开没有可见活动</div>}</div>);
  }
  return shell(projectName, <Users className="size-4 text-slate-500" />, <div className="grid grid-cols-2 gap-1.5">{kpi("有效任务", number(kpis.total))}{kpi("已完成", number(kpis.completed))}{kpi("逾期", number(kpis.overdue))}{kpi("无负责人", number(kpis.withoutOwner))}<div className="col-span-2 text-xs text-slate-500">项目角色：{text(project.role)} · 数据时间：{text(payload.asOf)}</div></div>);
}
