export type AgentEventEnvelope = {
  eventId?: string;
  runId?: string;
  messageId?: string;
  toolCallId?: string;
  sourceScope?: "main" | "subgraph";
  sourceNamespace?: string[];
  type?: string;
  schemaVersion?: number;
  entryId?: string;
  revision?: number;
  actor?: "main_agent" | "sub_agent" | "tool" | "system";
  actorName?: string;
  category?: "plan" | "progress" | "result" | "warning" | "confirmation";
  status?: "streaming" | "completed" | "failed";
  text?: string;
  sequence?: number;
  timestamp?: string;
  eventCursor?: {
    cursor?: number;
    databaseId?: number;
    eventId?: string | number;
    eventTime?: string;
  };
  data?: Record<string, unknown>;
};

export type AgentCustomEvent = {
  type: "agent_event";
  event?: AgentEventEnvelope;
  text?: string;
  /** Client-side arrival order used only as a stable live-stream tie breaker. */
  receivedOrder?: number;
  /** LangGraph namespace that produced this custom event. */
  sourceNamespace: string[];
  sourceScope: "main" | "subgraph";
  [key: string]: unknown;
};

/**
 * 主 Agent 收尾回答的临时流事件。
 *
 * 它不属于过程事件，也不会持久化到 LangGraph 历史。浏览器只用它在正式
 * ``AIMessage`` 到达前显示正在生成的 Markdown，正式消息到达或 Run 结束后
 * 必须移除，避免把半段内容误当作历史事实。
 */
export type AgentFinalAnswerStreamEvent = {
  type: "agent.final_answer.upsert";
  runId: string;
  threadId: string;
  entryId: string;
  revision: number;
  status: "streaming" | "completed";
  text: string;
};

/** 当前连接可见的一次临时最终回答，不写入对话消息或过程时间线。 */
export type StreamedAnswer = Omit<AgentFinalAnswerStreamEvent, "type">;

export type ActiveStreamIdentity = {
  runId: string | null;
  threadId: string | null;
};

/**
 * Decide whether a streamed final answer may be removed after a checkpoint
 * update. Identity is supplied by the server contract; text is never used as
 * a de-duplication key because valid answers can share identical wording.
 */
export function isStreamedAnswerCommitted(
  answer: Pick<StreamedAnswer, "entryId"> | null,
  committedFinalEntryIds: ReadonlySet<string>,
): boolean {
  return !!answer && committedFinalEntryIds.has(answer.entryId);
}

/**
 * 从顶层 LangGraph custom 事件中提取最终回答流。
 *
 * 子图的命名空间永远不能产出用户最终回答；即使出现同名事件也直接忽略，避免
 * 子 Agent 的自由文本越过主 Agent 汇总边界。
 */
export function parseFinalAnswerStreamEvent(
  value: unknown,
  transportNamespace: readonly string[] | undefined,
): AgentFinalAnswerStreamEvent | null {
  if (normalizeSourceNamespace(transportNamespace).length > 0) return null;
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  if (candidate.type !== "agent.final_answer.upsert") return null;
  if (candidate.sourceScope && candidate.sourceScope !== "main") return null;

  const runId = typeof candidate.runId === "string" ? candidate.runId : "";
  const threadId =
    typeof candidate.threadId === "string" ? candidate.threadId : "";
  const entryId =
    typeof candidate.entryId === "string" ? candidate.entryId : "";
  const revision = candidate.revision;
  const status = candidate.status;
  const text = typeof candidate.text === "string" ? candidate.text : "";
  if (
    !runId ||
    !threadId ||
    !entryId ||
    typeof revision !== "number" ||
    !Number.isSafeInteger(revision) ||
    revision < 1 ||
    (status !== "streaming" && status !== "completed")
  ) {
    return null;
  }
  return {
    type: "agent.final_answer.upsert",
    runId,
    threadId,
    entryId,
    revision,
    status,
    text,
  };
}

/**
 * 仅合并属于当前 Run 与 Thread 的全量快照。revision 是同一次模型调用的
 * 单调版本号；完成态不可被后到的 streaming 快照回退。
 */
export function mergeStreamedAnswer(
  current: StreamedAnswer | null,
  incoming: AgentFinalAnswerStreamEvent,
  active: ActiveStreamIdentity,
): StreamedAnswer | null {
  if (
    !active.runId ||
    !active.threadId ||
    incoming.runId !== active.runId ||
    incoming.threadId !== active.threadId
  ) {
    return current;
  }

  const next: StreamedAnswer = {
    runId: incoming.runId,
    threadId: incoming.threadId,
    entryId: incoming.entryId,
    revision: incoming.revision,
    status: incoming.status,
    text: incoming.text,
  };
  if (
    !current ||
    current.runId !== next.runId ||
    current.threadId !== next.threadId ||
    current.entryId !== next.entryId
  ) {
    return next;
  }
  if (current.status === "completed") return current;
  return next.revision > current.revision ? next : current;
}

export type SourceIdentity = {
  sourceScope: "main" | "subgraph";
  sourceNamespace: string[];
};

export function normalizeSourceNamespace(
  namespace: readonly unknown[] | undefined,
): string[] {
  return (namespace ?? []).map((part) => String(part).trim()).filter(Boolean);
}

function normalizeSourceScope(
  value: unknown,
): SourceIdentity["sourceScope"] | undefined {
  return value === "main" || value === "subgraph" ? value : undefined;
}

function envelopeSourceIdentity(
  envelope: AgentEventEnvelope | undefined,
): SourceIdentity | undefined {
  if (!envelope || !Array.isArray(envelope.sourceNamespace)) return undefined;
  const sourceScope = normalizeSourceScope(envelope.sourceScope);
  if (!sourceScope) return undefined;
  const sourceNamespace = normalizeSourceNamespace(envelope.sourceNamespace);
  if (sourceScope === "main" && sourceNamespace.length > 0) return undefined;
  if (sourceScope === "subgraph" && sourceNamespace.length === 0)
    return undefined;
  return { sourceScope, sourceNamespace };
}

/**
 * Resolve the one source identity shared by durable envelopes and live SDK
 * transport. A complete Python envelope is authoritative; old envelopes fall
 * back to the SDK namespace for live-only rendering. The two representations
 * are expected to be equal after normalization, never compared by text.
 */
export function resolveSourceIdentity(
  envelope: AgentEventEnvelope | undefined,
  transportNamespace: readonly string[] | undefined,
): SourceIdentity {
  const durable = envelopeSourceIdentity(envelope);
  if (durable) return durable;

  const sourceNamespace = normalizeSourceNamespace(transportNamespace);
  return {
    sourceScope: sourceNamespace.length > 0 ? "subgraph" : "main",
    sourceNamespace,
  };
}

/**
 * Convert SDK custom callbacks from either the main graph or a subgraph into
 * one application event contract. UI messages are handled before this adapter.
 */
export function adaptAgentCustomEvent(
  value: unknown,
  options: {
    namespace?: readonly string[];
    receivedOrder: number;
  },
): AgentCustomEvent | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  if (candidate.type !== "agent_event") return null;

  const sourceIdentity = resolveSourceIdentity(
    candidate.event && typeof candidate.event === "object"
      ? (candidate.event as AgentEventEnvelope)
      : undefined,
    options.namespace,
  );
  const eventEnvelope =
    candidate.event && typeof candidate.event === "object"
      ? ({
          ...(candidate.event as AgentEventEnvelope),
          sourceScope: sourceIdentity.sourceScope,
          sourceNamespace: sourceIdentity.sourceNamespace,
        } satisfies AgentEventEnvelope)
      : undefined;
  return {
    ...candidate,
    type: "agent_event",
    event: eventEnvelope,
    receivedOrder: options.receivedOrder,
    sourceNamespace: sourceIdentity.sourceNamespace,
    sourceScope: sourceIdentity.sourceScope,
  };
}
