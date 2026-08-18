/**
 * 持久化运行事件到聊天回合过程记录的适配层。
 *
 * Java 是事件事实源。这里仅按 runId 归并、保留最早可获得的 user messageId，
 * 并投影可展示的播报与工具状态。特别注意：``run.started`` 虽不展示，仍可能是
 * 整个 Run 唯一携带 messageId 的事件，所以关联必须在展示过滤之前完成。一个
 * 已绑定用户消息的 Run 即使没有可展示事件也必须保留，它仍是聊天头部的时长事实源。
 */

import {
  firstVisibleProcessText,
  readDurableCursor,
  reduceProcessEvents,
  type ProcessEvent,
  type ProcessRun,
  type PersistedRunFailure,
} from "../components/thread/process-events.ts";
import { inferToolName, toolLabel } from "../components/thread/tool-labels.ts";

const TERMINAL_RUN_EVENT_TYPES = new Set([
  "run.completed",
  "run.failed",
  "run.cancelled",
]);

/**
 * Return whether the durable Java event stream has accepted the terminal fact
 * for one concrete Run. This is intentionally evaluated on the raw response:
 * terminal lifecycle events are audit facts, not rows rendered in the chat
 * process timeline.
 */
export function hasPersistedRunTerminalEvent(
  value: unknown,
  runId: string,
): boolean {
  if (!runId || !Array.isArray(value)) return false;
  return value.some(
    (item) =>
      !!item &&
      typeof item === "object" &&
      String((item as Record<string, unknown>).runId ?? "") === runId &&
      TERMINAL_RUN_EVENT_TYPES.has(
        String((item as Record<string, unknown>).type ?? ""),
      ),
  );
}

function eventToProcessEvent(
  value: Record<string, unknown>,
  index: number,
): ProcessEvent | undefined {
  const data = (value.data ?? {}) as Record<string, unknown>;
  const eventType = String(value.type ?? "");
  const entryId =
    typeof value.entryId === "string"
      ? value.entryId
      : typeof data.entryId === "string"
        ? data.entryId
        : undefined;
  const isNarration = eventType === "narration.upsert" && !!entryId;
  const isLegacyNarration = [
    "plan.created",
    "progress",
  ].includes(eventType);
  const isMessage = isNarration || isLegacyNarration;
  const isTool = ["tool.started", "tool.completed", "tool.failed"].includes(eventType);
  if (!isMessage && !isTool) return undefined;

  const eventText = firstVisibleProcessText(
    value.text,
    data.text,
    data.summary,
    data.content,
  );
  const text = isTool
    ? toolLabel(String(data.toolName ?? inferToolName(eventText)))
    : eventText;
  if (!text) return undefined;

  const legacyEntryId = `legacy:${String(value.eventId ?? `${eventType}-${index}`)}`;
  return {
    id: isNarration
      ? entryId
      : isLegacyNarration
        ? legacyEntryId
        : String(value.eventId ?? `${eventType}-${index}-${text}`),
    type: isMessage ? "message" : "tool",
    text,
    ...(isMessage && {
      entryId: isNarration ? entryId : legacyEntryId,
      revision:
        typeof value.revision === "number"
          ? value.revision
          : typeof data.revision === "number"
            ? data.revision
            : 1,
      narrationStatus:
        value.status === "streaming" ||
        value.status === "failed" ||
        value.status === "completed"
          ? value.status
          : "completed",
      actor:
        value.actor === "main_agent" ||
        value.actor === "sub_agent" ||
        value.actor === "tool" ||
        value.actor === "system"
          ? value.actor
          : undefined,
      actorName: typeof value.actorName === "string" ? value.actorName : undefined,
      category:
        value.category === "plan" ||
        value.category === "progress" ||
        value.category === "result" ||
        value.category === "warning" ||
        value.category === "confirmation"
          ? value.category
          : undefined,
    }),
    status: isTool
      ? eventType === "tool.failed"
        ? "failed"
        : eventType === "tool.completed"
          ? "completed"
          : "started"
      : undefined,
    timestamp: typeof value.timestamp === "string" ? value.timestamp : undefined,
    sequence: typeof value.sequence === "number" ? value.sequence : undefined,
    cursorId: readDurableCursor(value.eventCursor),
    source: "persisted",
    eventType,
    messageId: typeof value.messageId === "string" && value.messageId ? value.messageId : undefined,
    toolCallId:
      typeof value.toolCallId === "string"
        ? value.toolCallId
        : typeof data.toolCallId === "string"
          ? data.toolCallId
          : undefined,
    runId: typeof value.runId === "string" && value.runId ? value.runId : undefined,
  };
}

/** 将一个线程的耐久事件归并成可绑定到用户消息的 Run 列表。 */
export function parsePersistedProcessRuns(value: unknown): ProcessRun[] {
  if (!Array.isArray(value)) return [];
  const rawEvents = value.filter(
    (item): item is Record<string, unknown> => !!item && typeof item === "object",
  );
  const groups = new Map<
    string,
    { runId: string; messageId?: string; events: ProcessEvent[]; timestamps: number[] }
  >();

  rawEvents.forEach((rawEvent, index) => {
    const runId = String(rawEvent.runId ?? "thread-run");
    const messageId =
      typeof rawEvent.messageId === "string" && rawEvent.messageId
        ? rawEvent.messageId
        : undefined;
    const groupKey = `run:${runId}`;
    const group = groups.get(groupKey) ?? {
      runId,
      messageId,
      events: [],
      timestamps: [],
    };
    // 先持久化 Run 与用户消息的绑定，再筛选是否展示这条事件。
    if (!group.messageId && messageId) group.messageId = messageId;
    const timestamp = typeof rawEvent.timestamp === "string" ? Date.parse(rawEvent.timestamp) : NaN;
    if (Number.isFinite(timestamp)) group.timestamps.push(timestamp);
    const event = eventToProcessEvent(rawEvent, index);
    if (event) group.events.push(event);
    groups.set(groupKey, group);
  });

  return [...groups.values()]
    .sort(
      (left, right) =>
        Math.min(...left.timestamps, Number.MAX_SAFE_INTEGER) -
        Math.min(...right.timestamps, Number.MAX_SAFE_INTEGER),
    )
    .map((group) => {
      const lifecycleEvents = rawEvents.filter(
        (event) => String(event.runId ?? "thread-run") === group.runId,
      );
      const durationMs = lifecycleEvents
        .reduce((maximum, event) => {
          if (
            event.type !== "run.completed" &&
            event.type !== "run.failed" &&
            event.type !== "run.cancelled"
          ) {
            return maximum;
          }
          const data = (event.data ?? {}) as Record<string, unknown>;
          const duration =
            typeof event.durationMs === "number"
              ? event.durationMs
              : typeof data.durationMs === "number"
                ? data.durationMs
                : 0;
          return Math.max(maximum, duration);
        }, 0);
      const failed = lifecycleEvents.findLast(
        (event) => event.type === "run.failed",
      );
      const failureData = (failed?.data ?? {}) as Record<string, unknown>;
      const failureCode = String(failureData.code ?? "").trim();
      const failureMessage = String(failureData.message ?? "").trim();
      const failure: PersistedRunFailure | undefined = failed
        ? {
            code: failureCode || "INTERNAL_RUNTIME_ERROR",
            message: failureMessage || "本次请求未能完成，请重试。",
          }
        : undefined;
      return {
        runId: group.runId,
        messageId: group.messageId,
        events: reduceProcessEvents(group.events),
        elapsedSeconds:
          durationMs > 0
            ? Math.floor(durationMs / 1000)
            : group.timestamps.length > 1
              ? Math.floor((Math.max(...group.timestamps) - Math.min(...group.timestamps)) / 1000)
              : 0,
        ...(failure ? { failure } : {}),
      };
    })
    // 过程详情可以为空，但已经与用户消息绑定的 Run 仍需保留。运行头部和耗时
    // 依赖这个事实，不能因为模型没有调用工具或未播报摘要而在正文后消失。
    .filter((run) => Boolean(run.messageId) || run.events.length > 0);
}
