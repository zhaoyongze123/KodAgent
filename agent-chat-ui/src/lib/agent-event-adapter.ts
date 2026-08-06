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
