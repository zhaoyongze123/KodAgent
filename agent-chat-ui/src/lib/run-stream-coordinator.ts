import {
  acquireRunStreamAttachment,
  clearLiveRunId,
  type RunStreamAttachmentToken,
} from "./run-stream-attachment.ts";
import {
  isDurableRunActive,
  isDurableRunTerminal,
  MAX_STREAM_RECOVERY_ATTEMPTS,
  streamRecoveryDelayMs,
} from "./stream-recovery.ts";

export type RunStatus = { status?: unknown };

export type ReconcileDurableRunOptions = {
  threadId: string;
  runId: string;
  attempts?: number;
  storage?:
    | (Pick<Storage, "getItem" | "removeItem"> &
        Partial<Pick<Storage, "setItem">>)
    | null;
  getStatus: () => Promise<RunStatus>;
  joinStream: () => Promise<unknown>;
  delay?: (milliseconds: number) => Promise<void>;
};

export type ReconcileDurableRunResult = "terminal" | "active" | "exhausted";

/**
 * Reconcile a browser transport with the durable LangGraph Run.
 *
 * A transport may finish before the backend Run reaches a terminal state. In
 * that case the marker is deliberately retained and the same Run is joined
 * again. The caller owns the outer per-run attachment lease, so concurrent
 * callers share one complete reconciliation rather than starting two loops.
 */
export async function reconcileDurableRun(
  options: ReconcileDurableRunOptions,
): Promise<ReconcileDurableRunResult> {
  const startingAttempt = options.attempts ?? 0;
  const delay = options.delay ?? defaultDelay;

  for (
    let attempt = startingAttempt;
    attempt < MAX_STREAM_RECOVERY_ATTEMPTS;
    attempt += 1
  ) {
    const beforeJoin = await options.getStatus();
    if (isDurableRunTerminal(beforeJoin.status)) {
      clearLiveRunId(options.storage, options.threadId, options.runId);
      return "terminal";
    }
    if (!isDurableRunActive(beforeJoin.status)) return "active";

    await delay(streamRecoveryDelayMs(attempt));
    await options.joinStream();

    const afterJoin = await options.getStatus();
    if (isDurableRunTerminal(afterJoin.status)) {
      clearLiveRunId(options.storage, options.threadId, options.runId);
      return "terminal";
    }
  }

  return "exhausted";
}

/**
 * The React-facing single-owner coordinator. It intentionally exposes only
 * the UI recovery state; transport and persistence mechanics stay here.
 */
export function acquireDurableRunReconciliation<T>(
  runId: string,
  reconcile: () => Promise<T>,
): {
  token: RunStreamAttachmentToken;
  promise: Promise<T>;
  reused: boolean;
} {
  return acquireRunStreamAttachment(runId, reconcile);
}

async function defaultDelay(milliseconds: number): Promise<void> {
  await new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}
