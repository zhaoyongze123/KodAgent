import {
  readDurableCursor,
  reduceProcessEvents,
  type ProcessEvent,
} from "../components/thread/process-events.ts";
import type { ProcessRun } from "../components/thread/thread-presentation.ts";

function numericValue(value: unknown): number | undefined {
  if (typeof value !== "number" || !Number.isFinite(value)) return undefined;
  return value;
}

/** Read the highest Java cursor from a raw event response, including events
 * that are intentionally hidden from the process timeline (run.started, for
 * example). The next delta request must advance past those rows as well.
 */
export function maxDurableEventCursor(value: unknown): number | undefined {
  if (!Array.isArray(value)) return undefined;
  let maximum: number | undefined;
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const event = item as Record<string, unknown>;
    const cursor =
      readDurableCursor(event.eventCursor) ??
      numericValue(event.sequence) ??
      numericValue(event.runSequence);
    if (cursor !== undefined && (maximum === undefined || cursor > maximum)) {
      maximum = cursor;
    }
  }
  return maximum;
}

function firstCursor(run: ProcessRun): number {
  return run.events.reduce(
    (minimum, event) =>
      typeof event.cursorId === "number"
        ? Math.min(minimum, event.cursorId)
        : minimum,
    Number.MAX_SAFE_INTEGER,
  );
}

function firstTimestamp(run: ProcessRun): number {
  return run.events.reduce((minimum, event) => {
    const timestamp = event.timestamp ? Date.parse(event.timestamp) : NaN;
    return Number.isFinite(timestamp) ? Math.min(minimum, timestamp) : minimum;
  }, Number.MAX_SAFE_INTEGER);
}

/** Merge a cursor response without making the browser a second event store.
 * The durable event identity/revision reducer remains the only de-duplication
 * rule; this function only joins Run projections from two server responses.
 */
export function mergePersistedProcessRuns(
  current: readonly ProcessRun[],
  incoming: readonly ProcessRun[],
): ProcessRun[] {
  const byRunId = new Map<string, ProcessRun>();
  for (const run of [...current, ...incoming]) {
    const previous = byRunId.get(run.runId);
    if (!previous) {
      byRunId.set(run.runId, run);
      continue;
    }
    const events: ProcessEvent[] = reduceProcessEvents([
      ...previous.events,
      ...run.events,
    ]);
    byRunId.set(run.runId, {
      runId: run.runId,
      messageId: previous.messageId ?? run.messageId,
      events,
      elapsedSeconds: Math.max(previous.elapsedSeconds, run.elapsedSeconds),
    });
  }

  return [...byRunId.values()].sort((left, right) => {
    const cursorDelta = firstCursor(left) - firstCursor(right);
    if (cursorDelta !== 0) return cursorDelta;
    return firstTimestamp(left) - firstTimestamp(right);
  });
}
