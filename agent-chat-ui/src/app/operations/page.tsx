"use client";

/**
 * Agent 管理员运行台。
 *
 * 本页只面向具有 agent:analytics:read 权限的管理员，展示全院 Agent 的真实运行事实：
 * agent_run 是一次运行的终态，agent_run_event 是阶段事件。页面不读取聊天正文、Prompt、
 * 模型隐藏推理或完整工具返回体；单次失败只能在右侧安全追踪中查看脱敏后的阶段摘要。
 *
 * 页面结构：概览指标 -> 可交互执行拓扑 -> 趋势与漏斗 -> 优化信号/工具健康 -> 运行表 -> 安全追踪抽屉。
 *
 * 执行拓扑只消费后端按 agent_run / agent_run_event 聚合出的统计事实，节点不是执行入口，
 * 也不显示 Prompt、完整工具返回值或模型推理。管理员可以缩放、平移和拖动节点查看各分支，
 * 鼠标悬停节点可检查该统计节点的事件口径和错误率。
 */
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node as ReactFlowNode,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  Activity,
  ArrowLeft,
  Bot,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  Clock3,
  Copy,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Tooltip as DetailTooltip,
  TooltipContent as DetailTooltipContent,
  TooltipTrigger as DetailTooltipTrigger,
} from "@/components/ui/tooltip";

type Numeric = number | string | null | undefined;
type Summary = {
  total_runs?: Numeric;
  totalRuns?: Numeric;
  completed_runs?: Numeric;
  completedRuns?: Numeric;
  failed_runs?: Numeric;
  failedRuns?: Numeric;
  cancelled_runs?: Numeric;
  cancelledRuns?: Numeric;
  waiting_approval_runs?: Numeric;
  waitingApprovalRuns?: Numeric;
  active_runs?: Numeric;
  activeRuns?: Numeric;
  avg_duration_ms?: Numeric;
  avgDurationMs?: Numeric;
  p95_duration_ms?: Numeric;
  p95DurationMs?: Numeric;
};
type Trend = {
  bucket?: string;
  day?: string;
  total?: Numeric;
  completed?: Numeric;
  failed?: Numeric;
  waiting_approval?: Numeric;
  waitingApproval?: Numeric;
};
type CountRow = {
  code?: string;
  domain?: string;
  status?: string;
  signal?: string;
  stage?: string;
  tool_name?: string;
  toolName?: string;
  count?: Numeric;
  runs?: Numeric;
  events?: Numeric;
  started?: Numeric;
  completed?: Numeric;
  failed?: Numeric;
  avg_duration_ms?: Numeric;
  avgDurationMs?: Numeric;
};
type ExecutionNode = {
  id: string;
  label: string;
  group?: string;
  description?: string;
  eventTypes?: string[];
  event_types?: string[];
  executions?: Numeric;
  runCount?: Numeric;
  run_count?: Numeric;
  failures?: Numeric;
  failureRate?: Numeric;
  failure_rate?: Numeric;
  rateAvailable?: boolean;
  rate_available?: boolean;
  metricLabel?: string;
  metric_label?: string;
};
type ExecutionEdge = {
  id: string;
  source: string;
  target: string;
  label?: string;
  kind?: string;
};
type ExecutionGraph = {
  version?: Numeric;
  nodes?: ExecutionNode[];
  edges?: ExecutionEdge[];
};
type CoordinationStep = {
  step_id?: string;
  stepId?: string;
  domain?: string;
  action_id?: string;
  actionId?: string;
  status?: string;
  error_code?: string | null;
  errorCode?: string | null;
};
type CoordinationBatch = {
  batch_id?: string;
  batchId?: string;
  status?: string;
  updated_at?: string;
  updatedAt?: string;
  steps?: CoordinationStep[];
};
type Analytics = {
  scope?: string;
  days?: number;
  granularity?: "hour" | "day";
  summary?: Summary;
  trend?: Trend[];
  failures?: CountRow[];
  domains?: CountRow[];
  funnel?: CountRow[];
  tools?: CountRow[];
  executionGraph?: ExecutionNode[] | ExecutionGraph;
  execution_graph?: ExecutionNode[] | ExecutionGraph;
  qualitySignals?: CountRow[];
  quality_signals?: CountRow[];
  coordination?: CountRow[];
  coordinationBatches?: CoordinationBatch[];
  coordination_batches?: CoordinationBatch[];
  modelTelemetry?: { available?: boolean; message?: string };
  model_telemetry?: { available?: boolean; message?: string };
};
type RunRow = {
  runId: string;
  status: string;
  startedAt: string;
  completedAt?: string | null;
  durationMs?: Numeric;
  errorCode?: string | null;
  errorMessage?: string | null;
  domain?: string | null;
  actionId?: string | null;
  lastStage?: string | null;
  failedTools?: Numeric;
};
type TraceEvent = {
  sequence: number;
  type: string;
  time: string;
  domain?: string;
  actionId?: string;
  toolName?: string;
  subagentName?: string;
  success?: boolean;
  status?: string;
  durationMs?: Numeric;
  errorCode?: string;
  errorMessage?: string;
  text?: string;
};
type RunTrace = {
  traceId: string;
  run: RunRow;
  events: TraceEvent[];
};

type RunPage = {
  items?: RunRow[];
  pageNo?: Numeric;
  pageSize?: Numeric;
  total?: Numeric;
};

const DAY_OPTIONS = [1, 7, 30] as const;
const STATUS_OPTIONS = [
  ["ALL", "全部状态"],
  ["RUNNING", "运行中"],
  ["PAUSED", "等待确认"],
  ["COMPLETED", "已完成"],
  ["FAILED", "失败"],
  ["CANCELLED", "已取消"],
] as const;

/** 将 JDBC 数值、JSON 字符串等统一为可计算的数字。 */
function numberOf(input: Numeric): number {
  const parsed = Number(input ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** 兼容 SQL 下划线字段与 Java 手工组装的驼峰字段。 */
function field(
  summary: Summary,
  snake: keyof Summary,
  camel: keyof Summary,
): number {
  return numberOf(summary[snake] ?? summary[camel]);
}

/** 将毫秒转为管理员便于扫描的时长文本。 */
function formatDuration(milliseconds: Numeric): string {
  const total = numberOf(milliseconds);
  if (total >= 60_000) return `${(total / 60_000).toFixed(1)} 分钟`;
  if (total >= 1_000) return `${(total / 1_000).toFixed(1)} 秒`;
  return `${Math.round(total)} 毫秒`;
}

function formatTime(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString("zh-CN", { hour12: false });
}

function statusMeta(status?: string | null) {
  const normalized = (status ?? "").toUpperCase();
  if (normalized === "COMPLETED")
    return {
      label: "已完成",
      className: "bg-emerald-50 text-emerald-700 ring-emerald-200",
    };
  if (normalized === "FAILED")
    return {
      label: "失败",
      className: "bg-rose-50 text-rose-700 ring-rose-200",
    };
  if (normalized === "PAUSED")
    return {
      label: "等待确认",
      className: "bg-amber-50 text-amber-700 ring-amber-200",
    };
  if (normalized === "RUNNING")
    return {
      label: "运行中",
      className: "bg-sky-50 text-sky-700 ring-sky-200",
    };
  if (normalized === "CANCELLED")
    return {
      label: "已取消",
      className: "bg-slate-100 text-slate-600 ring-slate-200",
    };
  return {
    label: status || "未知",
    className: "bg-slate-100 text-slate-600 ring-slate-200",
  };
}

function statusBadge(status?: string | null) {
  const meta = statusMeta(status);
  return (
    <span
      className={`inline-flex rounded-sm px-2 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset ${meta.className}`}
    >
      {meta.label}
    </span>
  );
}

async function requestJson<T>(url: string): Promise<T> {
  const response = await fetch(url, { cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || (typeof body?.code === "number" && body.code !== 0)) {
    throw new Error(
      body?.msg ?? body?.message ?? body?.error ?? "统计服务暂时不可用",
    );
  }
  return (body?.data ?? body) as T;
}

/** 读取当前筛选条件下的管理概览。 */
function loadAnalytics(days: number, granularity: string) {
  return requestJson<Analytics>(
    `/api/agent-analytics/overview?days=${days}&granularity=${granularity}`,
  );
}

/** 读取管理运行表，所有筛选项由后端再次校验。 */
function loadRuns(
  days: number,
  status: string,
  domain: string,
  pageNo: number,
) {
  const params = new URLSearchParams({
    days: String(days),
    pageNo: String(pageNo),
    pageSize: "20",
  });
  if (status !== "ALL") params.set("status", status);
  if (domain !== "ALL") params.set("domain", domain);
  return requestJson<RunPage>(`/api/agent-analytics/runs?${params}`);
}

/** 管理员打开追踪时才请求该 Run 的安全事件时间线。 */
function loadTrace(runId: string) {
  return requestJson<RunTrace>(
    `/api/agent-analytics/runs/${encodeURIComponent(runId)}`,
  );
}

/**
 * 全院 Agent 运行统计页面。
 *
 * 参数来自页面状态：days 决定回看窗口，granularity 决定趋势桶，status/domain 筛选运行表；
 * 它们只影响展示，真实授权范围始终由 Java 根据当前管理员身份确定。
 */
export default function OperationsPage() {
  const [days, setDays] = useState<(typeof DAY_OPTIONS)[number]>(7);
  const [granularity, setGranularity] = useState<"hour" | "day">("hour");
  const [data, setData] = useState<Analytics | null>(null);
  const [runs, setRuns] = useState<RunRow[]>([]);
  const [status, setStatus] = useState("ALL");
  const [domain, setDomain] = useState("ALL");
  const [pageNo, setPageNo] = useState(1);
  const [totalRuns, setTotalRuns] = useState(0);
  const [loading, setLoading] = useState(true);
  const [runsLoading, setRunsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [trace, setTrace] = useState<RunTrace | null>(null);
  const [traceLoading, setTraceLoading] = useState(false);
  const [traceError, setTraceError] = useState<string | null>(null);

  const refreshOverview = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await loadAnalytics(days, granularity));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "统计加载失败");
    } finally {
      setLoading(false);
    }
  }, [days, granularity]);

  const refreshRuns = useCallback(async () => {
    setRunsLoading(true);
    try {
      const result = await loadRuns(days, status, domain, pageNo);
      setRuns(result.items ?? []);
      setTotalRuns(numberOf(result.total));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "运行记录加载失败");
    } finally {
      setRunsLoading(false);
    }
  }, [days, domain, pageNo, status]);

  useEffect(() => {
    void refreshOverview();
  }, [refreshOverview]);

  useEffect(() => {
    void refreshRuns();
  }, [refreshRuns]);

  const summary = data?.summary ?? {};
  const total = field(summary, "total_runs", "totalRuns");
  const completed = field(summary, "completed_runs", "completedRuns");
  const failed = field(summary, "failed_runs", "failedRuns");
  const waiting = field(
    summary,
    "waiting_approval_runs",
    "waitingApprovalRuns",
  );
  const active = field(summary, "active_runs", "activeRuns");
  const successRate = total === 0 ? 0 : Math.round((completed / total) * 100);
  const trend = useMemo(
    () =>
      (data?.trend ?? []).map((row) => ({
        bucket: row.bucket ?? row.day ?? "-",
        total: numberOf(row.total),
        completed: numberOf(row.completed),
        failed: numberOf(row.failed),
        waiting: numberOf(row.waiting_approval ?? row.waitingApproval),
      })),
    [data?.trend],
  );
  const funnel = useMemo(() => {
    const labels: Record<string, string> = {
      routed: "已路由",
      compiled: "已编译",
      delegated: "已委派",
      completed: "已完成",
    };
    const indexed = new Map(
      (data?.funnel ?? []).map((item) => [item.stage, numberOf(item.count)]),
    );
    return Object.entries(labels).map(([stage, label]) => ({
      stage: label,
      count: indexed.get(stage) ?? 0,
    }));
  }, [data?.funnel]);
  const qualitySignals = data?.qualitySignals ?? data?.quality_signals ?? [];
  const executionGraph = data?.executionGraph ?? data?.execution_graph ?? [];
  const coordinationBatches =
    data?.coordinationBatches ?? data?.coordination_batches ?? [];
  const domainOptions = useMemo(
    () =>
      Array.from(
        new Set(
          (data?.domains ?? []).map((item) => item.domain).filter(Boolean),
        ),
      ) as string[],
    [data?.domains],
  );
  const totalPages = Math.max(1, Math.ceil(totalRuns / 20));

  async function openTrace(runId: string) {
    setTrace(null);
    setTraceError(null);
    setTraceLoading(true);
    try {
      setTrace(await loadTrace(runId));
    } catch (reason) {
      setTraceError(reason instanceof Error ? reason.message : "追踪加载失败");
    } finally {
      setTraceLoading(false);
    }
  }

  async function copyTraceId() {
    if (trace?.traceId && navigator.clipboard)
      await navigator.clipboard.writeText(trace.traceId);
  }

  function setWindow(windowDays: (typeof DAY_OPTIONS)[number]) {
    setDays(windowDays);
    setGranularity(windowDays <= 7 ? "hour" : "day");
    setPageNo(1);
  }

  return (
    <main className="min-h-screen bg-white text-slate-900">
      <div className="mx-auto max-w-[1440px] px-4 py-4 sm:px-5 lg:px-6">
        <header className="flex flex-col gap-3 border-b border-slate-200 pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-2">
            <Button
              variant="ghost"
              size="icon"
              asChild
              aria-label="返回智能助手"
              className="mt-0.5 shrink-0"
            >
              <Link href="/">
                <ArrowLeft className="size-4" />
              </Link>
            </Button>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold tracking-normal">
                  Agent 运行台
                </h1>
                <span className="inline-flex items-center gap-1 rounded-sm bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                  <ShieldCheck className="size-3.5" />
                  管理员
                </span>
              </div>
              <p className="mt-0.5 text-[13px] text-slate-500">
                全院运行事实、失败定位与 Agent 质量信号
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-md border border-slate-200 bg-slate-50 p-0.5">
              {DAY_OPTIONS.map((item) => (
                <Button
                  key={item}
                  size="sm"
                  variant={days === item ? "default" : "ghost"}
                  onClick={() => setWindow(item)}
                >
                  {item === 1 ? "24 小时" : `${item} 天`}
                </Button>
              ))}
            </div>
            <label
              className="sr-only"
              htmlFor="trend-granularity"
            >
              趋势颗粒度
            </label>
            <select
              id="trend-granularity"
              value={granularity}
              onChange={(event) =>
                setGranularity(event.target.value as "hour" | "day")
              }
              disabled={days > 7}
              className="h-9 rounded-md border border-slate-200 bg-white px-2 text-sm outline-none focus:border-sky-500 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-400"
            >
              <option value="hour">按小时</option>
              <option value="day">按天</option>
            </select>
            <Button
              size="icon"
              variant="outline"
              onClick={() => {
                void refreshOverview();
                void refreshRuns();
              }}
              disabled={loading || runsLoading}
              aria-label="刷新运行台"
            >
              <RefreshCw
                className={`size-4 ${loading || runsLoading ? "animate-spin" : ""}`}
              />
            </Button>
          </div>
        </header>

        {error ? (
          <div
            role="alert"
            className="mt-3 flex items-center gap-2 border border-rose-200 bg-rose-50 px-2.5 py-2 text-xs text-rose-700"
          >
            <CircleAlert className="size-4 shrink-0" />
            {error}
          </div>
        ) : null}

        <section className="mt-3 grid grid-cols-2 gap-2 xl:grid-cols-5">
          <Metric
            title="运行次数"
            value={total}
            hint={`${days === 1 ? "近 24 小时" : `近 ${days} 天`}真实 Run`}
            icon={<Activity className="size-4" />}
          />
          <Metric
            title="有效完成率"
            value={`${successRate}%`}
            hint={`完成 ${completed} / ${total}`}
            icon={<CheckCircle2 className="size-4 text-emerald-600" />}
          />
          <Metric
            title="P95 耗时"
            value={formatDuration(
              field(summary, "p95_duration_ms", "p95DurationMs"),
            )}
            hint={`平均 ${formatDuration(field(summary, "avg_duration_ms", "avgDurationMs"))}`}
            icon={<Clock3 className="size-4 text-sky-600" />}
          />
          <Metric
            title="等待确认"
            value={waiting}
            hint="HITL 卡片尚未处理"
            icon={<CircleAlert className="size-4 text-amber-600" />}
          />
          <Metric
            title="失败运行"
            value={failed}
            hint={`进行中 ${active} 次`}
            icon={<XCircle className="size-4 text-rose-600" />}
          />
        </section>

        <section className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.7fr)_minmax(320px,0.8fr)]">
          <Panel
            title="运行趋势"
            description="按真实 Run 的开始时间聚合"
          >
            {loading ? (
              <ChartLoading />
            ) : trend.length ? (
              <div className="h-[220px]">
                <ResponsiveContainer
                  width="100%"
                  height="100%"
                >
                  <LineChart
                    data={trend}
                    margin={{ top: 10, right: 8, left: -20, bottom: 0 }}
                  >
                    <CartesianGrid
                      stroke="#e2e8f0"
                      strokeDasharray="3 3"
                      vertical={false}
                    />
                    <XAxis
                      dataKey="bucket"
                      tick={{ fill: "#64748b", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      allowDecimals={false}
                      tick={{ fill: "#64748b", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        borderRadius: 6,
                        borderColor: "#cbd5e1",
                        fontSize: 12,
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line
                      type="monotone"
                      dataKey="total"
                      name="总数"
                      stroke="#2563eb"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="completed"
                      name="完成"
                      stroke="#059669"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="failed"
                      name="失败"
                      stroke="#e11d48"
                      strokeWidth={2}
                      dot={false}
                    />
                    <Line
                      type="monotone"
                      dataKey="waiting"
                      name="待确认"
                      stroke="#d97706"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            ) : (
              <Empty text="当前时间窗口没有运行记录" />
            )}
          </Panel>
          <Panel
            title="执行漏斗"
            description="路由到完成的关键阶段覆盖"
          >
            {loading ? (
              <ChartLoading />
            ) : (
              <div className="h-[220px]">
                <ResponsiveContainer
                  width="100%"
                  height="100%"
                >
                  <BarChart
                    data={funnel}
                    layout="vertical"
                    margin={{ top: 8, right: 16, left: 10, bottom: 0 }}
                  >
                    <CartesianGrid
                      stroke="#e2e8f0"
                      horizontal={false}
                    />
                    <XAxis
                      type="number"
                      allowDecimals={false}
                      tick={{ fill: "#64748b", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="stage"
                      width={52}
                      tick={{ fill: "#475569", fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip
                      cursor={{ fill: "#f8fafc" }}
                      contentStyle={{
                        borderRadius: 6,
                        borderColor: "#cbd5e1",
                        fontSize: 12,
                      }}
                    />
                    <Bar
                      dataKey="count"
                      name="运行数"
                      fill="#2563eb"
                      radius={[2, 2, 2, 2]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </Panel>
        </section>

        <section className="mt-3">
          <Panel
            title="动态执行链路"
            description="次数来自阶段事件，错误率只在对应失败事件已持久化时计算"
          >
            {loading ? (
              <div className="h-28 animate-pulse bg-slate-100" />
            ) : (
              <ExecutionFlow
                graph={executionGraph}
                days={days}
              />
            )}
          </Panel>
        </section>

        <section className="mt-3 grid gap-3 xl:grid-cols-2">
          <Panel
            title="失败原因与优化信号"
            description="点击失败码可筛选底部运行表"
          >
            <div className="grid gap-3 md:grid-cols-2">
              <div>
                <h3 className="mb-2 text-xs font-medium text-slate-500">
                  失败原因
                </h3>
                {data?.failures?.length ? (
                  <div className="space-y-1">
                    {data.failures.map((item) => (
                      <button
                        key={item.code}
                        type="button"
                        onClick={() => {
                          setStatus("FAILED");
                          setPageNo(1);
                        }}
                        className="flex w-full items-center justify-between rounded-sm px-2 py-2 text-left text-sm hover:bg-rose-50"
                      >
                        <span className="flex min-w-0 items-center gap-2 truncate">
                          <XCircle className="size-3.5 shrink-0 text-rose-500" />
                          {item.code ?? "UNKNOWN"}
                        </span>
                        <span className="font-medium tabular-nums">
                          {numberOf(item.count)}
                        </span>
                      </button>
                    ))}
                  </div>
                ) : (
                  <Empty
                    text="没有失败运行"
                    compact
                  />
                )}
              </div>
              <div>
                <h3 className="mb-2 text-xs font-medium text-slate-500">
                  可优化信号
                </h3>
                {qualitySignals.length ? (
                  <div className="space-y-1">
                    {qualitySignals.map((item) => (
                      <SignalLine
                        key={item.signal}
                        label={item.signal ?? "未标记"}
                        count={numberOf(item.count)}
                      />
                    ))}
                  </div>
                ) : (
                  <Empty
                    text="当前没有需关注的信号"
                    compact
                  />
                )}
              </div>
            </div>
            <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
              <Bot className="mr-1 inline size-3.5" />
              {(data?.modelTelemetry ?? data?.model_telemetry)?.message ??
                "模型可观测数据尚未接入。"}
            </div>
          </Panel>
          <Panel
            title="领域与跨领域协作"
            description="只统计已经写入 Runtime 的协作批次"
          >
            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <h3 className="mb-2 text-xs font-medium text-slate-500">
                  领域运行
                </h3>
                {data?.domains?.length ? (
                  <div className="space-y-1">
                    {data.domains.slice(0, 5).map((item) => (
                      <SignalLine
                        key={item.domain}
                        label={item.domain ?? "未标记"}
                        count={numberOf(item.runs)}
                      />
                    ))}
                  </div>
                ) : (
                  <Empty
                    text="暂无带领域标记的事件"
                    compact
                  />
                )}
              </div>
              <div>
                <h3 className="mb-2 text-xs font-medium text-slate-500">
                  协作状态
                </h3>
                {data?.coordination?.length ? (
                  <div className="space-y-1">
                    {data.coordination.map((item) => (
                      <div
                        key={item.status}
                        className="flex items-center justify-between px-2 py-2 text-sm"
                      >
                        {statusBadge(item.status)}
                        <span className="font-medium tabular-nums">
                          {numberOf(item.count)}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <Empty
                    text="当前窗口没有协作批次"
                    compact
                  />
                )}
              </div>
            </div>
          </Panel>
        </section>

        <section className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.5fr)_minmax(320px,0.9fr)]">
          <Panel
            title="工具健康"
            description="工具事件的启动、完成、失败与平均耗时"
          >
            {data?.tools?.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[620px] text-left text-xs">
                  <thead className="border-b border-slate-200 text-[11px] text-slate-500">
                    <tr>
                      <th className="pb-2 font-medium">工具</th>
                      <th className="pb-2 text-right font-medium">完成</th>
                      <th className="pb-2 text-right font-medium">失败</th>
                      <th className="pb-2 text-right font-medium">失败率</th>
                      <th className="pb-2 text-right font-medium">平均耗时</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.tools.map((item) => {
                      const done = numberOf(item.completed);
                      const toolFailed = numberOf(item.failed);
                      const attempts = Math.max(
                        numberOf(item.started),
                        done + toolFailed,
                      );
                      const rate = attempts
                        ? Math.round((toolFailed / attempts) * 100)
                        : 0;
                      return (
                        <tr
                          key={item.tool_name ?? item.toolName}
                          className="border-b border-slate-100 last:border-0"
                        >
                          <td className="max-w-[250px] truncate py-2 font-mono text-[11px] text-slate-700">
                            {item.tool_name ?? item.toolName ?? "未标记工具"}
                          </td>
                          <td className="py-2.5 text-right tabular-nums">
                            {done}
                          </td>
                          <td
                            className={`py-2.5 text-right tabular-nums ${toolFailed ? "text-rose-600" : ""}`}
                          >
                            {toolFailed}
                          </td>
                          <td
                            className={`py-2.5 text-right tabular-nums ${rate ? "text-rose-600" : ""}`}
                          >
                            {rate}%
                          </td>
                          <td className="py-2.5 text-right text-slate-600 tabular-nums">
                            {formatDuration(
                              item.avg_duration_ms ?? item.avgDurationMs,
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty text="当前时间窗口没有工具事件" />
            )}
          </Panel>
          <Panel
            title="最近协作批次"
            description="跨领域任务的结构化状态"
          >
            {coordinationBatches.length ? (
              <div className="max-h-[240px] divide-y divide-slate-100 overflow-y-auto">
                {coordinationBatches.map((batch) => (
                  <div
                    key={batch.batch_id ?? batch.batchId}
                    className="py-3 first:pt-0"
                  >
                    <div className="flex items-center justify-between gap-2">
                      {statusBadge(batch.status)}
                      <time className="text-xs text-slate-400">
                        {formatTime(batch.updated_at ?? batch.updatedAt)}
                      </time>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {(batch.steps ?? []).map((step) => (
                        <span
                          key={step.step_id ?? step.stepId}
                          className="rounded-sm bg-slate-100 px-1.5 py-1 text-xs text-slate-600"
                        >
                          {step.domain ?? "业务"}{" "}
                          {(step.action_id ?? step.actionId)
                            ? `· ${step.action_id ?? step.actionId}`
                            : ""}{" "}
                          {(step.error_code ?? step.errorCode)
                            ? `· ${step.error_code ?? step.errorCode}`
                            : ""}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty text="当前窗口没有协作批次" />
            )}
          </Panel>
        </section>

        <section className="mt-3 pb-6">
          <Card className="rounded-md border-slate-200 shadow-none">
            <CardHeader className="flex flex-col gap-2 border-b border-slate-100 px-3 pt-3 pb-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <CardTitle className="text-base">最近运行</CardTitle>
                <p className="mt-0.5 text-xs text-slate-500">
                  失败、暂停和运行中的 Run 可打开安全追踪定位阶段。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <select
                  value={status}
                  onChange={(event) => {
                    setStatus(event.target.value);
                    setPageNo(1);
                  }}
                  className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:border-sky-500"
                >
                  {STATUS_OPTIONS.map(([value, label]) => (
                    <option
                      key={value}
                      value={value}
                    >
                      {label}
                    </option>
                  ))}
                </select>
                <select
                  value={domain}
                  onChange={(event) => {
                    setDomain(event.target.value);
                    setPageNo(1);
                  }}
                  className="h-8 max-w-36 rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:border-sky-500"
                >
                  <option value="ALL">全部领域</option>
                  {domainOptions.map((item) => (
                    <option
                      key={item}
                      value={item}
                    >
                      {item}
                    </option>
                  ))}
                </select>
              </div>
            </CardHeader>
            <CardContent className="p-0">
              {runsLoading ? (
                <div className="space-y-1.5 p-3">
                  <div className="h-8 animate-pulse bg-slate-100" />
                  <div className="h-8 animate-pulse bg-slate-100" />
                  <div className="h-8 animate-pulse bg-slate-100" />
                </div>
              ) : runs.length ? (
                <>
                  <div className="overflow-x-auto">
                    <table className="w-full min-w-[900px] text-left text-xs">
                      <thead className="bg-slate-50 text-[11px] text-slate-500">
                        <tr>
                          <th className="px-3 py-2 font-medium">开始时间</th>
                          <th className="px-3 py-2 font-medium">状态</th>
                          <th className="px-3 py-2 font-medium">领域 / 动作</th>
                          <th className="px-3 py-2 font-medium">最后阶段</th>
                          <th className="px-3 py-2 text-right font-medium">
                            耗时
                          </th>
                          <th className="px-3 py-2 font-medium">异常摘要</th>
                          <th className="w-12 px-2 py-3" />
                        </tr>
                      </thead>
                      <tbody>
                        {runs.map((run) => (
                          <tr
                            key={run.runId}
                            onClick={() => void openTrace(run.runId)}
                            className="cursor-pointer border-t border-slate-100 hover:bg-sky-50/60"
                          >
                            <td className="px-3 py-2 whitespace-nowrap text-slate-600">
                              {formatTime(run.startedAt)}
                            </td>
                            <td className="px-3 py-2">
                              {statusBadge(run.status)}
                            </td>
                            <td className="max-w-[240px] px-3 py-2">
                              <div className="truncate font-medium text-slate-800">
                                {run.domain ?? "未标记"}
                              </div>
                              <div className="mt-0.5 truncate font-mono text-xs text-slate-500">
                                {run.actionId ?? "-"}
                              </div>
                            </td>
                            <td className="max-w-[150px] truncate px-3 py-2 font-mono text-[11px] text-slate-600">
                              {run.lastStage ?? "-"}
                            </td>
                            <td className="px-3 py-2 text-right whitespace-nowrap text-slate-600 tabular-nums">
                              {formatDuration(run.durationMs)}
                            </td>
                            <td className="max-w-[260px] truncate px-3 py-2 text-[11px] text-rose-600">
                              {run.errorCode
                                ? `${run.errorCode}${run.errorMessage ? `：${run.errorMessage}` : ""}`
                                : "-"}
                            </td>
                            <td className="px-2 py-3 text-slate-400">
                              <ChevronRight className="size-4" />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 px-3 py-2 text-xs text-slate-500">
                    <span>
                      共 {totalRuns} 条，第 {pageNo} / {totalPages} 页
                    </span>
                    <div className="flex items-center gap-1">
                      <Button
                        size="icon"
                        variant="outline"
                        aria-label="上一页"
                        onClick={() =>
                          setPageNo((current) => Math.max(1, current - 1))
                        }
                        disabled={pageNo <= 1}
                      >
                        <ChevronLeft className="size-4" />
                      </Button>
                      <Button
                        size="icon"
                        variant="outline"
                        aria-label="下一页"
                        onClick={() =>
                          setPageNo((current) =>
                            Math.min(totalPages, current + 1),
                          )
                        }
                        disabled={pageNo >= totalPages}
                      >
                        <ChevronRight className="size-4" />
                      </Button>
                    </div>
                  </div>
                </>
              ) : (
                <Empty text="当前筛选条件没有运行记录" />
              )}
            </CardContent>
          </Card>
        </section>
      </div>

      <Sheet
        open={Boolean(trace || traceLoading || traceError)}
        onOpenChange={(open) => {
          if (!open) {
            setTrace(null);
            setTraceError(null);
          }
        }}
      >
        <SheetContent
          side="right"
          className="w-full gap-0 overflow-y-auto p-0 sm:max-w-xl"
        >
          <SheetHeader className="border-b border-slate-200 pr-12">
            <SheetTitle>安全运行追踪</SheetTitle>
            <SheetDescription>
              只包含阶段、工具、状态、耗时和脱敏错误摘要，不展示
              Prompt、业务返回体或模型推理。
            </SheetDescription>
          </SheetHeader>
          {traceLoading ? (
            <div className="flex h-48 items-center justify-center gap-2 text-sm text-slate-500">
              <LoaderCircle className="size-4 animate-spin" />
              正在读取追踪
            </div>
          ) : traceError ? (
            <div className="m-4 border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              {traceError}
            </div>
          ) : trace ? (
            <div className="p-4">
              <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
                <div className="flex items-center justify-between gap-2">
                  {statusBadge(trace.run.status)}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void copyTraceId()}
                  >
                    <Copy className="mr-1 size-3.5" />
                    复制追踪编号
                  </Button>
                </div>
                <div className="mt-3 font-mono text-xs break-all text-slate-600">
                  {trace.traceId}
                </div>
                <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-slate-500">
                  <span>耗时：{formatDuration(trace.run.durationMs)}</span>
                  <span>事件：{trace.events.length} 条</span>
                  {trace.run.errorCode ? (
                    <span className="col-span-2 text-rose-700">
                      {trace.run.errorCode}
                      {trace.run.errorMessage
                        ? `：${trace.run.errorMessage}`
                        : ""}
                    </span>
                  ) : null}
                </div>
              </div>
              <ol className="mt-5 space-y-0">
                {trace.events.map((event, index) => (
                  <li
                    key={`${event.sequence}-${event.type}`}
                    className="relative flex gap-3 pb-5 last:pb-0"
                  >
                    <div className="relative z-10 mt-1 flex size-5 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white">
                      <span
                        className={`size-2 rounded-full ${event.success === false || event.type.includes("failed") ? "bg-rose-500" : event.type.includes("completed") ? "bg-emerald-500" : "bg-sky-500"}`}
                      />
                    </div>
                    {index < trace.events.length - 1 ? (
                      <span className="absolute top-6 bottom-0 left-[9px] w-px bg-slate-200" />
                    ) : null}
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1">
                        <span className="font-mono text-xs font-medium text-slate-800">
                          {event.type}
                        </span>
                        <time className="text-xs text-slate-400">
                          {formatTime(event.time)}
                        </time>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-2 gap-y-1 text-xs text-slate-500">
                        {event.domain ? <span>{event.domain}</span> : null}
                        {event.actionId ? (
                          <span className="font-mono">{event.actionId}</span>
                        ) : null}
                        {event.toolName ? (
                          <span className="font-mono">{event.toolName}</span>
                        ) : null}
                        {event.subagentName ? (
                          <span>{event.subagentName}</span>
                        ) : null}
                        {event.durationMs !== undefined ? (
                          <span>{formatDuration(event.durationMs)}</span>
                        ) : null}
                      </div>
                      {event.errorCode || event.errorMessage ? (
                        <p className="mt-1.5 text-xs break-words text-rose-700">
                          {event.errorCode}
                          {event.errorMessage ? `：${event.errorMessage}` : ""}
                        </p>
                      ) : event.text ? (
                        <p className="mt-1.5 text-xs break-words text-slate-600">
                          {event.text}
                        </p>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </SheetContent>
      </Sheet>
    </main>
  );
}

/** 顶部关键指标卡，固定尺寸避免动态数据造成布局跳动。 */
function Metric({
  title,
  value,
  hint,
  icon,
}: {
  title: string;
  value: string | number;
  hint: string;
  icon: ReactNode;
}) {
  return (
    <Card className="rounded-md border-slate-200 shadow-none">
      <CardContent className="p-3">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>{title}</span>
          {icon}
        </div>
        <div className="mt-2 text-xl font-semibold tracking-normal tabular-nums">
          {value}
        </div>
        <p className="mt-0.5 truncate text-[11px] text-slate-500">{hint}</p>
      </CardContent>
    </Card>
  );
}

/** 普通面板容器，保持白底和紧凑数据工具的视觉层级。 */
function Panel({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <Card className="rounded-md border-slate-200 shadow-none">
      <CardHeader className="border-b border-slate-100 px-3 pt-3 pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
        <p className="mt-0.5 text-[11px] text-slate-500">{description}</p>
      </CardHeader>
      <CardContent className="p-3">{children}</CardContent>
    </Card>
  );
}

/** 后端新旧图谱契约在浏览器中统一成的轻量数据结构。 */
type NormalizedExecutionGraph = {
  nodes: ExecutionNode[];
  edges: ExecutionEdge[];
};

/** React Flow 的两类节点：统计节点与只作视觉分组的职责泳道。 */
type DiagramNodeData =
  | { kind: "execution"; node: ExecutionNode; days: number }
  | { kind: "lane"; label: string; description: string };
type DiagramNode = ReactFlowNode<DiagramNodeData>;
type DiagramLayout = { nodes: DiagramNode[]; edges: Edge[] };

const LEGACY_FLOW_ORDER = [
  "run",
  "route",
  "compiler",
  "subagent",
  "tool",
  "completed",
];

/**
 * 将旧版的节点数组转换为最小可用拓扑。
 *
 * Java 正在升级为 { nodes, edges }；发布窗口内仍可能存在旧服务，前端保留这段适配，
 * 确保管理员不会因为前后端滚动发布而看见空白画布。
 */
function normalizeExecutionGraph(
  input: ExecutionNode[] | ExecutionGraph,
): NormalizedExecutionGraph {
  if (!Array.isArray(input)) {
    return {
      nodes: input.nodes ?? [],
      edges: input.edges ?? [],
    };
  }

  const ids = new Set(input.map((node) => node.id));
  const edges = LEGACY_FLOW_ORDER.slice(1)
    .map((target, index) => ({
      id: `legacy-${LEGACY_FLOW_ORDER[index]}-${target}`,
      source: LEGACY_FLOW_ORDER[index],
      target,
      label: "",
      kind: "main",
    }))
    .filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  if (ids.has("hitl") && ids.has("tool")) {
    edges.push({
      id: "legacy-tool-hitl",
      source: "tool",
      target: "hitl",
      label: "等待确认",
      kind: "hitl",
    });
  }
  return { nodes: input, edges };
}

/** 旧版节点没有职责分组时，根据可观测阶段补足稳定的泳道名称。 */
function executionGroup(node: ExecutionNode): string {
  if (node.group?.trim()) return node.group.trim();
  const id = node.id.toLowerCase();
  if (/(approval|hitl|draft)/.test(id)) return "人工确认与审批";
  if (/(workflow|operation)/.test(id)) return "业务工作流";
  if (/(coordination|batch|step)/.test(id)) return "跨领域协调";
  if (/(subagent|tool)/.test(id)) return "领域执行";
  return "主 Agent 编排";
}

/** 让常见职责泳道稳定排序，其余后端新分组仍能正常显示在后方。 */
function groupRank(group: string): number {
  const order = [
    "主 Agent 编排",
    "领域执行",
    "业务工作流",
    "工作流与业务状态",
    "人工确认与审批",
    "人工确认",
    "跨领域协调",
    "运行终态",
  ];
  const index = order.indexOf(group);
  return index === -1 ? order.length : index;
}

/** 读取兼容驼峰与下划线字段的错误率可用状态。 */
function rateAvailable(node: ExecutionNode): boolean {
  return node.rateAvailable ?? node.rate_available ?? false;
}

/** 读取兼容驼峰与下划线字段的错误率。 */
function failureRate(node: ExecutionNode): number {
  return numberOf(node.failureRate ?? node.failure_rate);
}

/** 根据后端声明的分支类型区分普通、并行、人工确认、失败和终态路径。 */
function edgeVisual(kind?: string) {
  if (kind === "failure") {
    return { stroke: "#e11d48", dash: "5 3", label: "#be123c" };
  }
  if (kind === "parallel") {
    return { stroke: "#2563eb", dash: "4 3", label: "#1d4ed8" };
  }
  if (kind === "branch" || kind === "hitl") {
    return { stroke: "#d97706", dash: "", label: "#a16207" };
  }
  if (kind === "terminal") {
    return { stroke: "#059669", dash: "", label: "#047857" };
  }
  return { stroke: "#94a3b8", dash: "", label: "#64748b" };
}

/** 将事件统计节点布局成横向执行步骤、纵向职责泳道，所有位置均可由用户再拖动调整。 */
function buildExecutionDiagram(
  graph: NormalizedExecutionGraph,
  days: number,
): DiagramLayout {
  const nodeIds = new Set(graph.nodes.map((node) => node.id));
  const usableEdges = graph.edges.filter(
    (edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target),
  );
  const incoming = new Map<string, string[]>();
  for (const edge of usableEdges) {
    const sources = incoming.get(edge.target) ?? [];
    sources.push(edge.source);
    incoming.set(edge.target, sources);
  }

  // 依据有向边计算层级。遇到异常环路时回落为首列，监控页面仍可完整呈现事实节点。
  const levels = new Map<string, number>();
  const visiting = new Set<string>();
  function levelOf(id: string): number {
    const existing = levels.get(id);
    if (existing !== undefined) return existing;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const sourceLevels = (incoming.get(id) ?? []).map(levelOf);
    visiting.delete(id);
    const level = sourceLevels.length ? Math.max(...sourceLevels) + 1 : 0;
    levels.set(id, level);
    return level;
  }
  graph.nodes.forEach((node) => levelOf(node.id));

  const groups = Array.from(new Set(graph.nodes.map(executionGroup))).sort(
    (left, right) => {
      const rankDifference = groupRank(left) - groupRank(right);
      return rankDifference || left.localeCompare(right, "zh-CN");
    },
  );
  const maxLevel = Math.max(0, ...Array.from(levels.values()));
  const laneWidth = Math.max(760, (maxLevel + 1) * 250 + 56);
  const diagramNodes: DiagramNode[] = [];
  let laneTop = 16;

  for (const group of groups) {
    const groupedNodes = graph.nodes.filter(
      (node) => executionGroup(node) === group,
    );
    const perLevel = new Map<number, ExecutionNode[]>();
    for (const node of groupedNodes) {
      const level = levels.get(node.id) ?? 0;
      const current = perLevel.get(level) ?? [];
      current.push(node);
      perLevel.set(level, current);
    }
    const stackedCount = Math.max(
      1,
      ...Array.from(perLevel.values()).map((items) => items.length),
    );
    const laneHeight = Math.max(132, 52 + stackedCount * 96);
    diagramNodes.push({
      id: `lane-${group}`,
      type: "lane",
      position: { x: 0, y: laneTop },
      data: {
        kind: "lane",
        label: group,
        description: "同一职责层的真实可观测阶段",
      },
      draggable: false,
      selectable: false,
      focusable: false,
      zIndex: 0,
      style: { width: laneWidth, height: laneHeight },
    });

    for (const [level, nodesAtLevel] of perLevel) {
      nodesAtLevel.forEach((node, index) => {
        diagramNodes.push({
          id: node.id,
          type: "execution",
          position: {
            x: 30 + level * 250,
            y: laneTop + 38 + index * 96,
          },
          data: { kind: "execution", node, days },
          zIndex: 1,
        });
      });
    }
    laneTop += laneHeight + 18;
  }

  return {
    nodes: diagramNodes,
    edges: usableEdges.map((edge) => {
      const visual = edgeVisual(edge.kind);
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
        type: "smoothstep",
        animated: false,
        style: {
          stroke: visual.stroke,
          strokeDasharray: visual.dash,
          strokeWidth: 1.25,
        },
        labelStyle: { fill: visual.label, fontSize: 10 },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.96 },
        labelBgPadding: [3, 2],
        labelBgBorderRadius: 2,
      };
    }),
  };
}

/**
 * 可交互的真实运行拓扑。
 *
 * 画布状态独立保存，管理员拖动节点后不会在同一次数据展示中被 React 重置；刷新统计时才按
 * 新事实重新布局。缩放、平移和缩略图均由 React Flow 提供，避免手写高风险的画布交互。
 */
function ExecutionFlow({
  graph,
  days,
}: {
  graph: ExecutionNode[] | ExecutionGraph;
  days: number;
}) {
  const normalized = useMemo(() => normalizeExecutionGraph(graph), [graph]);
  const layout = useMemo(
    () => buildExecutionDiagram(normalized, days),
    [days, normalized],
  );
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<DiagramNode>(
    layout.nodes,
  );
  const [flowEdges, setFlowEdges, onEdgesChange] = useEdgesState(layout.edges);

  useEffect(() => {
    setFlowNodes(layout.nodes);
    setFlowEdges(layout.edges);
  }, [layout, setFlowEdges, setFlowNodes]);

  if (!normalized.nodes.length) {
    return (
      <Empty
        text="当前窗口没有可绘制的执行事件"
        compact
      />
    );
  }

  return (
    <div className="h-[430px] overflow-hidden border border-slate-200 bg-slate-50 sm:h-[500px]">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={EXECUTION_FLOW_NODE_TYPES}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.3}
        maxZoom={1.6}
        panOnDrag
        zoomOnScroll
        nodesConnectable={false}
        nodesDraggable
        elementsSelectable={false}
        proOptions={{ hideAttribution: true }}
        defaultEdgeOptions={{ type: "smoothstep" }}
      >
        <Controls
          position="bottom-right"
          showInteractive={false}
        />
        <MiniMap
          position="bottom-left"
          pannable
          zoomable
          nodeColor={(node) => (node.type === "lane" ? "#e2e8f0" : "#2563eb")}
          maskColor="rgb(248 250 252 / 72%)"
        />
      </ReactFlow>
    </div>
  );
}

/** 自定义职责泳道，仅辅助阅读，不代表新的业务状态或数据来源。 */
function ExecutionLane({ data }: NodeProps<DiagramNode>) {
  if (data.kind !== "lane") return null;
  return (
    <div className="size-full border border-slate-200 bg-white/70 px-3 py-2">
      <p className="text-[11px] font-semibold text-slate-600">{data.label}</p>
      <p className="mt-0.5 text-[10px] text-slate-400">{data.description}</p>
    </div>
  );
}

/** 单个事实节点：画布上只展示摘要，完整统计口径通过悬停提示呈现。 */
function ExecutionDiagramNode({ data }: NodeProps<DiagramNode>) {
  if (data.kind !== "execution") return null;
  const { node, days } = data;
  const executions = numberOf(node.executions);
  const rawRunCount = node.runCount ?? node.run_count;
  const runCount = numberOf(rawRunCount);
  const failures = numberOf(node.failures);
  const rate = failureRate(node);
  const available = rateAvailable(node);
  const rateText = available
    ? `${(rate * 100).toFixed(rate > 0 && rate < 0.01 ? 1 : 0)}%`
    : "未记录";
  const rateTone = !available
    ? "text-slate-500"
    : failures > 0
      ? "text-rose-700"
      : "text-emerald-700";
  const metricLabel = node.metricLabel ?? node.metric_label ?? "错误率";
  const eventTypes = node.eventTypes ?? node.event_types ?? [];
  const rangeText = days === 1 ? "近 24 小时" : `近 ${days} 天`;

  return (
    <DetailTooltip>
      <DetailTooltipTrigger asChild>
        <div
          tabIndex={0}
          aria-label={`${node.label}，执行 ${executions} 次，${metricLabel} ${rateText}`}
          className="min-w-[204px] border border-slate-300 bg-white px-2.5 py-2 shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        >
          <Handle
            type="target"
            position={Position.Left}
            className="!size-1.5 !border-0 !bg-slate-400"
          />
          <div className="flex items-start justify-between gap-2">
            <p className="line-clamp-2 min-w-0 text-xs leading-4 font-semibold text-slate-800">
              {node.label}
            </p>
            <span className="shrink-0 text-xs font-semibold text-slate-700 tabular-nums">
              {executions.toLocaleString("zh-CN")}
            </span>
          </div>
          <div className="mt-1.5 flex items-baseline justify-between gap-2 border-t border-slate-100 pt-1.5">
            <span className="truncate text-[10px] text-slate-500">
              {metricLabel}
            </span>
            <span className={`text-xs font-semibold tabular-nums ${rateTone}`}>
              {rateText}
            </span>
          </div>
          <Handle
            type="source"
            position={Position.Right}
            className="!size-1.5 !border-0 !bg-slate-400"
          />
        </div>
      </DetailTooltipTrigger>
      <DetailTooltipContent
        side="top"
        sideOffset={8}
        className="z-50 max-w-[300px] rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-left text-xs text-slate-100 shadow-md"
      >
        <p className="font-semibold text-white">{node.label}</p>
        {node.description ? (
          <p className="mt-1 leading-5 text-pretty text-slate-300">
            {node.description}
          </p>
        ) : null}
        <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[11px] leading-4">
          <dt className="text-slate-400">职责层</dt>
          <dd>{executionGroup(node)}</dd>
          <dt className="text-slate-400">统计窗口</dt>
          <dd>{rangeText}</dd>
          <dt className="text-slate-400">执行次数</dt>
          <dd className="tabular-nums">{executions.toLocaleString("zh-CN")}</dd>
          <dt className="text-slate-400">关联 Run</dt>
          <dd className="tabular-nums">
            {rawRunCount === null || rawRunCount === undefined
              ? "未记录"
              : runCount.toLocaleString("zh-CN")}
          </dd>
          <dt className="text-slate-400">失败次数</dt>
          <dd className="tabular-nums">{failures.toLocaleString("zh-CN")}</dd>
          <dt className="text-slate-400">{metricLabel}</dt>
          <dd className="tabular-nums">{rateText}</dd>
          <dt className="text-slate-400">事件口径</dt>
          <dd className="break-words text-slate-200">
            {eventTypes.length ? eventTypes.join("、") : "后端暂未记录"}
          </dd>
        </dl>
      </DetailTooltipContent>
    </DetailTooltip>
  );
}

const EXECUTION_FLOW_NODE_TYPES = {
  execution: ExecutionDiagramNode,
  lane: ExecutionLane,
};

function SignalLine({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center justify-between rounded-sm px-1.5 py-1.5 text-xs hover:bg-slate-50">
      <span className="min-w-0 truncate text-slate-600">{label}</span>
      <span className="font-medium text-slate-900 tabular-nums">{count}</span>
    </div>
  );
}

function ChartLoading() {
  return <div className="h-[220px] animate-pulse bg-slate-100" />;
}

function Empty({ text, compact = false }: { text: string; compact?: boolean }) {
  return (
    <div
      className={`${compact ? "py-2" : "py-7"} text-center text-xs text-slate-500`}
    >
      {text}
    </div>
  );
}
