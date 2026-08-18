import { AIMessage, ToolMessage } from "@langchain/langgraph-sdk";
import { useState } from "react";
import {
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Wrench,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { MarkdownText } from "../markdown-text";
import { useStreamContext } from "@/providers/Stream";
import { AgentBlockRenderer } from "./agent-block-renderer";
import {
  agentBlockFromToolResult,
  type AgentErrorCode,
} from "@/types/agent-block";
import {
  isApprovalCardProjection,
  isApprovalControlFlow,
} from "@/lib/approval-tool-result";
import { findLatestCorrelatedToolEvent } from "@/lib/tool-event-correlation";
import { toolLabel } from "../tool-labels";
import { isProcessOnlyToolName } from "./message-visibility";

function stringify(value: unknown) {
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

// Only ever surface clean, structured detail to the end user. A tool result may
// arrive as an opaque Python repr string (e.g. "ok=True data={...}") which is a
// debug artifact, not product content — in that case we render nothing rather
// than leak it.
function detailContent(content: unknown): string | undefined {
  const response = parseStructuredToolResponse(content);
  if (response) {
    const body = response.ok ? response.data : response.error;
    if (body == null) return undefined;
    const pretty = stringify(body);
    return pretty.trim() ? pretty : undefined;
  }
  if (typeof content === "string") {
    if (/^\s*ok=(True|False)\b/.test(content)) return undefined;
    return content.trim() ? content : undefined;
  }
  if (content == null) return undefined;
  return stringify(content);
}

type StructuredToolResponse = {
  ok?: boolean;
  data?: unknown;
  error?: { code?: string; message?: string } | null;
};

const SAFE_ERROR_MESSAGES: Record<AgentErrorCode, string> = {
  SESSION_EXPIRED: "登录状态已失效，请重新登录后再试。",
  PERMISSION_DENIED: "当前账号没有执行该操作的权限。",
  EMPTY_RESULT: "没有找到相关数据。",
  UPSTREAM_TIMEOUT: "业务系统暂时没有响应，请稍后再试。",
  UPSTREAM_BAD_REQUEST: "模型请求参数不兼容，请切换模型后再试。",
  MODEL_NOT_SUPPORTED: "当前模型不支持 Agent 工具调用，请切换模型后再试。",
  MODEL_OUTPUT_INVALID: "当前模型未能生成可展示的回复，请重试或切换模型。",
  CONVERSATION_HISTORY_INVALID: "当前对话记录异常，请新建对话后重新发起请求。",
  CLIPBOARD_UNAVAILABLE: "当前环境不允许复制到剪贴板，请手动复制。",
  VALIDATION_FAILED: "请求信息不完整或不合法，请检查后再试。",
  UNKNOWN: "处理请求时发生异常，请稍后再试。",
};

function parseStructuredToolResponse(
  content: unknown,
): StructuredToolResponse | undefined {
  if (content && typeof content === "object") {
    const value = content as StructuredToolResponse;
    if (typeof value.ok === "boolean") return value;
  }
  if (typeof content !== "string") return undefined;
  try {
    const parsed = JSON.parse(content) as StructuredToolResponse;
    return typeof parsed?.ok === "boolean" ? parsed : undefined;
  } catch {
    return undefined;
  }
}

function resultSummary(
  content: unknown,
  name: string | null | undefined,
  event?: ReturnType<typeof findLatestCorrelatedToolEvent>,
) {
  if (name === "report_progress") {
    return "已播报当前执行进度";
  }
  const response = parseStructuredToolResponse(content);
  if (response?.ok === false) {
    return (
      response.error?.message ||
      String(event?.data?.text ?? "") ||
      `${toolLabel(name)}执行失败`
    );
  }
  if (event?.type === "tool.failed") {
    return String(event.data?.text ?? `${toolLabel(name)}执行失败`);
  }
  if (event?.type === "tool.completed") {
    return String(event.data?.text ?? `${toolLabel(name)}已完成`);
  }
  return response?.ok === true ? `${toolLabel(name)}已完成` : "工具已返回结果";
}

function normalizeErrorCode(value: unknown): AgentErrorCode {
  const code = String(value ?? "UNKNOWN");
  if (code === "IDENTITY_UNAVAILABLE") return "SESSION_EXPIRED";
  if (code.includes("FACADE") || code.includes("TIMEOUT")) {
    return "UPSTREAM_TIMEOUT";
  }
  if (code.includes("PERMISSION")) return "PERMISSION_DENIED";
  if (code.includes("INVALID") || code.includes("VALIDATION")) {
    return "VALIDATION_FAILED";
  }
  if (
    [
      "SESSION_EXPIRED",
      "PERMISSION_DENIED",
      "EMPTY_RESULT",
      "UPSTREAM_TIMEOUT",
      "VALIDATION_FAILED",
      "UPSTREAM_BAD_REQUEST",
      "MODEL_NOT_SUPPORTED",
      "CLIPBOARD_UNAVAILABLE",
    ].includes(code)
  ) {
    return code as AgentErrorCode;
  }
  return "UNKNOWN";
}

function ToolCard({
  name,
  children,
  status,
}: {
  name?: string | null;
  children?: React.ReactNode;
  status: "running" | "completed" | "failed";
}) {
  const Icon =
    status === "failed"
      ? CircleAlert
      : status === "completed"
        ? CheckCircle2
        : Wrench;
  const statusText =
    status === "failed"
      ? "执行失败"
      : status === "completed"
        ? "已完成"
        : "正在调用";

  return (
    <details className="border-border/70 bg-card mx-auto w-full max-w-3xl rounded-xl border shadow-sm">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 [&::-webkit-details-marker]:hidden">
        <Icon
          aria-hidden="true"
          className={cn(
            "size-4 shrink-0",
            status === "failed"
              ? "text-destructive"
              : status === "completed"
                ? "text-emerald-600"
                : "text-muted-foreground",
          )}
        />
        <span className="text-foreground text-sm font-medium">
          {toolLabel(name)}
        </span>
        <span className="text-muted-foreground ml-auto text-xs">
          {statusText}
        </span>
        <ChevronDown
          aria-hidden="true"
          className="text-muted-foreground size-4 shrink-0 transition-transform [[open]>&]:rotate-180"
        />
      </summary>
      {children}
    </details>
  );
}

export function ToolCalls({
  toolCalls,
}: {
  toolCalls: AIMessage["tool_calls"];
}) {
  if (!toolCalls?.length) return null;

  const processCalls = toolCalls.filter(
    (toolCall) => toolCall.name === "report_progress",
  );
  const visibleToolCalls = toolCalls.filter(
    (toolCall) => !isProcessOnlyToolName(toolCall.name),
  );

  return (
    <div className="mx-auto grid w-full max-w-3xl gap-2">
      {processCalls.map((toolCall, index) => {
        const args = (toolCall.args ?? {}) as Record<string, unknown>;
        const message = typeof args.message === "string" ? args.message : "";
        const stage = typeof args.stage === "string" ? args.stage : "";
        if (!message) return null;
        return (
          <details
            key={toolCall.id || "process-" + index}
            className="text-foreground mx-auto w-full max-w-3xl px-1 py-1 text-sm"
          >
            <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium [&::-webkit-details-marker]:hidden">
              <ChevronDown
                aria-hidden="true"
                className="text-muted-foreground size-4 shrink-0 transition-transform [[open]>&]:rotate-180"
              />
              <span className="truncate">{message}</span>
              {stage && (
                <span className="text-muted-foreground ml-auto shrink-0 text-xs font-normal">
                  {stage}
                </span>
              )}
            </summary>
            <div className="border-border mt-2 border-l-2 pl-6 text-sm">
              <MarkdownText>{message}</MarkdownText>
            </div>
          </details>
        );
      })}
      {visibleToolCalls.map((toolCall, index) => {
        const args = (toolCall.args ?? {}) as Record<string, unknown>;
        const hasArgs = Object.keys(args).length > 0;
        return (
          <ToolCard
            key={toolCall.id || toolCall.name + "-" + index}
            name={toolCall.name}
            status="running"
          >
            {hasArgs && (
              <details className="border-border/60 text-muted-foreground border-t px-4 py-2 text-xs">
                <summary className="cursor-pointer select-none">
                  查看输入参数
                </summary>
                <pre className="bg-muted/60 mt-2 max-h-48 overflow-auto rounded-md p-3 font-mono text-[11px] leading-5 whitespace-pre-wrap">
                  {stringify(args)}
                </pre>
              </details>
            )}
          </ToolCard>
        );
      })}
    </div>
  );
}

export function ToolResult({
  message,
  onRetry,
}: {
  message: ToolMessage;
  onRetry?: () => void;
}) {
  const thread = useStreamContext();
  const [isExpanded, setIsExpanded] = useState(false);
  if (isProcessOnlyToolName(message.name)) return null;

  const detail = detailContent(message.content);
  const event = findLatestCorrelatedToolEvent(
    thread.processEvents.map((item) => item.event),
    message.tool_call_id,
    message.name,
  );
  const response = parseStructuredToolResponse(message.content);
  // Approval rejection/expiry is a normal HITL outcome. The assistant's
  // structured/narrated result remains visible; the low-level ToolMessage
  // must not add a generic red failure card on top of it.
  if (isApprovalControlFlow(message) || isApprovalCardProjection(message)) {
    return null;
  }
  const failed =
    message.status === "error" ||
    response?.ok === false ||
    event?.type === "tool.failed";

  if (failed) {
    const code = normalizeErrorCode(
      response?.error?.code ?? event?.data?.errorCode,
    );
    // Retrying re-runs the whole turn, so only offer it for transient failures.
    // Auth/permission/validation errors would just fail again with the same input.
    const retryable =
      onRetry != null && (code === "UPSTREAM_TIMEOUT" || code === "UNKNOWN");
    return (
      <AgentBlockRenderer
        block={{
          kind: "error",
          error: {
            code,
            // Do not render raw upstream exception text. The code is the stable
            // user-facing contract; detailed diagnostics remain in audit logs.
            message: SAFE_ERROR_MESSAGES[code],
            retryable,
            ...(retryable
              ? { action: { type: "retry" as const, label: "重试" } }
              : {}),
          },
        }}
        onErrorAction={(action) => {
          if (action.type === "retry") onRetry?.();
        }}
      />
    );
  }

  const normalizedBlock = agentBlockFromToolResult(
    message.name,
    message.content,
    message.id,
  );
  if (normalizedBlock?.kind === "card" || normalizedBlock?.kind === "result") {
    return <AgentBlockRenderer block={normalizedBlock} />;
  }

  return (
    <ToolCard
      name={message.name}
      status={failed ? "failed" : "completed"}
    >
      <div className="border-border/60 border-t px-4 py-3">
        <div
          className={cn(
            "text-foreground text-sm",
            failed && "text-destructive",
          )}
        >
          {resultSummary(message.content, message.name, event)}
        </div>
        {detail && (
          <>
            <button
              type="button"
              aria-expanded={isExpanded}
              aria-label={
                (isExpanded ? "收起" : "展开") +
                toolLabel(message.name) +
                "详细结果"
              }
              onClick={() => setIsExpanded((expanded) => !expanded)}
              className="text-muted-foreground hover:text-foreground mt-2 inline-flex items-center gap-1 text-xs underline-offset-4 hover:underline"
            >
              {isExpanded ? "收起详细结果" : "查看详细结果"}
              {isExpanded ? (
                <ChevronUp
                  aria-hidden="true"
                  className="size-3.5"
                />
              ) : (
                <ChevronDown
                  aria-hidden="true"
                  className="size-3.5"
                />
              )}
            </button>
            {isExpanded && (
              <pre className="bg-muted/60 text-muted-foreground mt-3 max-h-64 overflow-auto rounded-md p-3 font-mono text-[11px] leading-5 whitespace-pre-wrap">
                {detail}
              </pre>
            )}
          </>
        )}
      </div>
    </ToolCard>
  );
}
