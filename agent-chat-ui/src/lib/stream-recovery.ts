export const ACTIVE_RUN_STATUSES = new Set(["pending", "queued", "running"]);
export const PAUSED_RUN_STATUSES = new Set([
  "interrupted",
  "paused",
  "waiting",
  "awaiting_approval",
]);
export const TERMINAL_RUN_STATUSES = new Set([
  "success",
  "error",
  "failed",
  "timeout",
  "timed_out",
  "cancelled",
  "canceled",
  "cancelled_by_user",
]);

export const MAX_STREAM_RECOVERY_ATTEMPTS = 3;

export function shouldRejoinDurableRun(
  status: unknown,
  attempts: number,
): boolean {
  return attempts < MAX_STREAM_RECOVERY_ATTEMPTS && isDurableRunActive(status);
}

export function isDurableRunActive(status: unknown): boolean {
  return ACTIVE_RUN_STATUSES.has(String(status ?? "").toLowerCase());
}

export function isDurableRunTerminal(status: unknown): boolean {
  return TERMINAL_RUN_STATUSES.has(String(status ?? "").toLowerCase());
}

export function isDurableRunPaused(status: unknown): boolean {
  return PAUSED_RUN_STATUSES.has(String(status ?? "").toLowerCase());
}

export function streamRecoveryDelayMs(attempt: number): number {
  return Math.min(1000 * 2 ** Math.max(0, attempt), 5000);
}
