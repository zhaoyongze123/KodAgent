import { type AgentCustomEvent } from "../../lib/agent-event-adapter.ts";
import { inferToolName, toolLabel } from "./tool-labels.ts";

export type ProcessEvent = {
  id: string;
  type: "message" | "tool";
  text: string;
  timestamp?: string;
  sequence?: number;
  cursorId?: number;
  sourceOrder?: number;
  source?: "persisted" | "custom";
  messageId?: string;
  toolCallId?: string;
  eventType?: string;
  status?: "started" | "completed" | "failed";
  card?: unknown;
  runId?: string;
  /** Stable server-issued identity for a user-visible narration row. */
  entryId?: string;
  revision?: number;
  narrationStatus?: "streaming" | "completed" | "failed";
  actor?: "main_agent" | "sub_agent" | "tool" | "system";
  actorName?: string;
  category?: "plan" | "progress" | "result" | "warning" | "confirmation";
};

/** 一次后端 Run 归并后的用户回合过程记录。 */
export type ProcessRun = {
  runId: string;
  messageId?: string;
  events: ProcessEvent[];
  elapsedSeconds: number;
  /** Durable terminal failure from the backend, never inferred from text. */
  failure?: PersistedRunFailure;
};

export type PersistedRunFailure = {
  code: string;
  message: string;
};

export type ProcessEntryIdentity = string;

/**
 * Return the identity of one rendered process entry.
 *
 * Narration identity is issued by the backend.  The browser never derives an
 * identity from model chunks, tool call IDs, or LangGraph namespaces.
 */
export function processEntryIdentity(
  event: ProcessEvent,
): ProcessEntryIdentity {
  if (event.entryId) return `narration:${event.entryId}`;
  return `event:${event.id}`;
}

export type ProcessRunReference = {
  runId: string;
  messageId?: string;
};

/**
 * Return the only text that is allowed to occupy a process row.
 *
 * Process events can arrive from three different transports. During a
 * streaming tool call some of them contain only whitespace, line breaks, or
 * zero-width characters while the model is still assembling its payload.
 * ReactMarkdown renders those values as an empty, but non-zero-height,
 * container. Normalizing at the event boundary keeps that transport detail
 * out of the view layer.
 */
export function normalizeProcessText(value: unknown): string {
  if (typeof value !== "string") return "";
  return value
    .replace(/[\u200B-\u200D\uFEFF]/g, "")
    .replace(/\r\n?/g, "\n")
    .trim();
}

export function firstVisibleProcessText(...values: unknown[]): string {
  for (const value of values) {
    const text = normalizeProcessText(value);
    if (text) return text;
  }
  return "";
}

/**
 * Build the durable ownership index used by the thread renderer.
 *
 * A Run is the execution boundary. Event-level message IDs are not stable
 * across sub-agents and resume runs, so live events without a durable mapping
 * are attached to the user turn that is currently executing. Persisted
 * run-to-turn links always win and prevent an old run from drifting into a
 * newer turn.
 */
export function buildProcessRunTurnMap(
  persistedRuns: readonly ProcessRunReference[],
  liveEvents: readonly Pick<ProcessEvent, "runId">[],
  currentMessageId?: string,
): Map<string, string> {
  const runTurnMap = new Map<string, string>();

  for (const run of persistedRuns) {
    if (run.runId && run.messageId) {
      runTurnMap.set(run.runId, run.messageId);
    }
  }

  if (currentMessageId) {
    for (const event of liveEvents) {
      if (event.runId && !runTurnMap.has(event.runId)) {
        runTurnMap.set(event.runId, currentMessageId);
      }
    }
  }

  return runTurnMap;
}

/** Read the durable Java event cursor across current and legacy contracts. */
export function readDurableCursor(value: unknown): number | undefined {
  if (!value || typeof value !== "object") return undefined;
  const cursor = value as Record<string, unknown>;
  for (const key of ["cursor", "databaseId", "eventId"]) {
    const candidate = cursor[key];
    if (typeof candidate === "number" && Number.isFinite(candidate)) {
      return candidate;
    }
  }
  return undefined;
}

function sourceRank(event: ProcessEvent): number {
  return event.source === "persisted" ? 2 : 1;
}

function isNewer(left: ProcessEvent, right: ProcessEvent): boolean {
  if (left.entryId && left.entryId === right.entryId) {
    if (
      (left.narrationStatus === "completed" ||
        left.narrationStatus === "failed") &&
      right.narrationStatus === "streaming"
    ) {
      return false;
    }
    const leftRevision = left.revision ?? 0;
    const rightRevision = right.revision ?? 0;
    if (leftRevision !== rightRevision) return rightRevision > leftRevision;
    if (
      left.narrationStatus === "completed" ||
      left.narrationStatus === "failed"
    ) {
      return sourceRank(right) > sourceRank(left);
    }
  }
  if (sourceRank(left) !== sourceRank(right)) {
    return sourceRank(right) > sourceRank(left);
  }
  if (
    typeof left.cursorId === "number" &&
    typeof right.cursorId === "number" &&
    left.cursorId !== right.cursorId
  ) {
    return right.cursorId > left.cursorId;
  }
  const leftTimestamp = eventTimestamp(left);
  const rightTimestamp = eventTimestamp(right);
  if (
    leftTimestamp !== Number.MAX_SAFE_INTEGER &&
    rightTimestamp !== Number.MAX_SAFE_INTEGER &&
    leftTimestamp !== rightTimestamp
  ) {
    return rightTimestamp > leftTimestamp;
  }
  if (
    typeof left.sourceOrder === "number" &&
    typeof right.sourceOrder === "number" &&
    left.sourceOrder !== right.sourceOrder
  ) {
    return right.sourceOrder > left.sourceOrder;
  }
  if (
    typeof left.sequence === "number" &&
    typeof right.sequence === "number" &&
    left.sequence !== right.sequence
  ) {
    return right.sequence > left.sequence;
  }
  return false;
}

function eventTimestamp(event: ProcessEvent): number {
  const value = event.timestamp ? Date.parse(event.timestamp) : NaN;
  return Number.isFinite(value) ? value : Number.MAX_SAFE_INTEGER;
}

function mergeEvent(left: ProcessEvent, right: ProcessEvent): ProcessEvent {
  const preferred = isNewer(left, right) ? right : left;
  const fallback = preferred === left ? right : left;
  const text = firstVisibleProcessText(preferred.text, fallback.text) || "";
  return {
    ...fallback,
    ...preferred,
    text,
    source: preferred.source ?? fallback.source,
    timestamp: preferred.timestamp ?? fallback.timestamp,
    sequence: preferred.sequence ?? fallback.sequence,
    cursorId: preferred.cursorId ?? fallback.cursorId,
    sourceOrder: preferred.sourceOrder ?? fallback.sourceOrder,
    messageId: preferred.messageId ?? fallback.messageId,
    toolCallId: preferred.toolCallId ?? fallback.toolCallId,
    eventType: preferred.eventType ?? fallback.eventType,
    status: preferred.status ?? fallback.status,
    card: preferred.card ?? fallback.card,
    entryId: preferred.entryId ?? fallback.entryId,
    revision: preferred.revision ?? fallback.revision,
    narrationStatus: preferred.narrationStatus ?? fallback.narrationStatus,
    actor: preferred.actor ?? fallback.actor,
    actorName: preferred.actorName ?? fallback.actorName,
    category: preferred.category ?? fallback.category,
  };
}

/**
 * Normalize canonical narration and tool lifecycle events through one reducer.
 */
export function normalizeProcessEvents(events: ProcessEvent[]): ProcessEvent[] {
  const byIdentity = new Map<ProcessEntryIdentity, ProcessEvent>();
  for (const event of events) {
    const text = normalizeProcessText(event.text);
    if (!text) continue;
    const normalized = { ...event, text };
    const identity = processEntryIdentity(event);
    const current = byIdentity.get(identity);
    byIdentity.set(
      identity,
      current ? mergeEvent(current, normalized) : normalized,
    );
  }

  return [...byIdentity.values()]
    .map((event, index) => ({ event, index }))
    .sort((left, right) => {
      const a = left.event;
      const b = right.event;

      // Durable cursor is the only replay-stable ordering source. Python's
      // sequence may restart per parallel context, so it is only a final tie
      // breaker for events without cursor/timestamp information.
      if (
        typeof a.cursorId === "number" &&
        typeof b.cursorId === "number" &&
        a.cursorId !== b.cursorId
      ) {
        return a.cursorId - b.cursorId;
      }
      const timestampDelta = eventTimestamp(a) - eventTimestamp(b);
      if (timestampDelta !== 0 && timestampDelta !== Number.MAX_SAFE_INTEGER) {
        return timestampDelta;
      }
      if (
        typeof a.sourceOrder === "number" &&
        typeof b.sourceOrder === "number" &&
        a.sourceOrder !== b.sourceOrder
      ) {
        return a.sourceOrder - b.sourceOrder;
      }
      if (
        typeof a.sequence === "number" &&
        typeof b.sequence === "number" &&
        a.sequence !== b.sequence
      ) {
        return a.sequence - b.sequence;
      }
      return left.index - right.index;
    })
    .map(({ event }) => event);
}

/** Collapse started/completed/failed rows for the same tool call. */
export function mergeToolLifecycle(events: ProcessEvent[]): ProcessEvent[] {
  const result: ProcessEvent[] = [];
  const indexByToolCallId = new Map<string, number>();

  for (const event of events) {
    if (event.type !== "tool" || !event.toolCallId) {
      result.push(event);
      continue;
    }
    const lifecycleKey = `${event.runId ?? "run:unknown"}:${event.toolCallId}`;
    const previousIndex = indexByToolCallId.get(lifecycleKey);
    if (previousIndex === undefined) {
      indexByToolCallId.set(lifecycleKey, result.length);
      result.push(event);
      continue;
    }
    result[previousIndex] = {
      ...mergeEvent(result[previousIndex], event),
      status: event.status ?? result[previousIndex].status,
      eventType: event.eventType ?? result[previousIndex].eventType,
      card: event.card ?? result[previousIndex].card,
    };
  }
  return result;
}

export function reduceProcessEvents(events: ProcessEvent[]): ProcessEvent[] {
  return mergeToolLifecycle(normalizeProcessEvents(events));
}

/** Adapt normalized live Agent events into the process timeline domain. */
export function collectCustomProcessEvents(
  customEvents: AgentCustomEvent[],
): ProcessEvent[] {
  return customEvents.flatMap((customEvent, index): ProcessEvent[] => {
    const event = customEvent.event ?? {};
    const data = event.data ?? {};
    const eventType = String(event.type ?? "");
    const eventText = firstVisibleProcessText(data.text, customEvent.text);
    const sequence =
      typeof event.sequence === "number" ? event.sequence : undefined;
    const timestamp =
      typeof event.timestamp === "string" ? event.timestamp : undefined;
    const cursorId = readDurableCursor(event.eventCursor);
    const common = {
      runId: event.runId,
      messageId: event.messageId,
      toolCallId:
        typeof event.toolCallId === "string"
          ? event.toolCallId
          : typeof data.toolCallId === "string"
            ? data.toolCallId
            : undefined,
      eventType,
      sequence,
      timestamp,
      cursorId,
      sourceOrder: customEvent.receivedOrder ?? index,
      source: "custom" as const,
    };

    const entryId =
      typeof event.entryId === "string"
        ? event.entryId
        : typeof data.entryId === "string"
          ? data.entryId
          : undefined;
    if (eventType === "narration.upsert" && entryId) {
      if (!eventText) return [];
      return [
        {
          id: entryId,
          type: "message",
          text: eventText,
          entryId,
          revision:
            typeof event.revision === "number"
              ? event.revision
              : typeof data.revision === "number"
                ? data.revision
                : 1,
          narrationStatus:
            event.status === "streaming" ||
            event.status === "failed" ||
            event.status === "completed"
              ? event.status
              : "completed",
          actor:
            event.actor === "main_agent" ||
            event.actor === "sub_agent" ||
            event.actor === "tool" ||
            event.actor === "system"
              ? event.actor
              : undefined,
          actorName:
            typeof event.actorName === "string" ? event.actorName : undefined,
          category:
            event.category === "plan" ||
            event.category === "progress" ||
            event.category === "result" ||
            event.category === "warning" ||
            event.category === "confirmation"
              ? event.category
              : undefined,
          ...common,
        },
      ];
    }

    // Historical rows are projected at this boundary only.  Their event ID
    // is already durable, so no namespace/tool-call inference is reintroduced.
    if (
      eventType === "plan.created" ||
      eventType === "progress"
    ) {
      if (!eventText) return [];
      const legacyEntryId = `legacy:${String(event.eventId ?? `custom-${index}`)}`;
      return [
        {
          id: legacyEntryId,
          type: "message",
          text: eventText,
          entryId: legacyEntryId,
          revision: 1,
          narrationStatus: "completed",
          ...common,
        },
      ];
    }

    const isToolLifecycle = [
      "tool.started",
      "tool.completed",
      "tool.failed",
    ].includes(eventType);
    if (!isToolLifecycle) {
      if (!["draft.created", "approval.required"].includes(eventType)) {
        return [];
      }
      if (!eventText) return [];
      return [];
    }

    const toolName = toolLabel(
      String(data.toolName ?? inferToolName(eventText)),
    );
    if (!toolName) return [];
    return [
      {
        id: String(event.eventId ?? `custom-tool-${index}`),
        type: "tool",
        text: toolName,
        status:
          eventType === "tool.failed"
            ? "failed"
            : eventType === "tool.completed"
              ? "completed"
              : "started",
        ...common,
      },
    ];
  });
}
