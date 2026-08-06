const DEFAULT_THREAD_HISTORY_TIMEOUT_MS = 12_000;

/**
 * The LangGraph SDK does not expose an AbortSignal for `threads.search`.
 * Race it against a bounded timer so a dead upstream can never leave the
 * sidebar in a permanent loading state. The original request may finish in
 * the background, but its result is deliberately ignored after the timeout.
 */
export function withThreadHistoryTimeout<T>(
  operation: Promise<T>,
  timeoutMs = DEFAULT_THREAD_HISTORY_TIMEOUT_MS,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error("历史记录服务暂时不可用，请检查 Agent 服务后重试。")),
      timeoutMs,
    );
    operation.then(
      (value) => {
        clearTimeout(timeout);
        resolve(value);
      },
      (error) => {
        clearTimeout(timeout);
        reject(error);
      },
    );
  });
}
