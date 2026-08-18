const DEFAULT_THREAD_HISTORY_TIMEOUT_MS = 12_000;

/**
 * 合并历史记录分页，并保留较新的已展示顺序。
 *
 * LangGraph 的 offset 分页在有新 Thread 写入时，前后页面可能短暂重叠。侧栏只展示
 * 标题摘要，因此在前端按 thread_id 去重即可，不能因为重复项造成“加载更多”出现同一会话。
 */
export function mergeThreadHistoryPages<T extends { thread_id: string }>(
  current: readonly T[],
  next: readonly T[],
): T[] {
  const seen = new Set(current.map((thread) => thread.thread_id));
  return [...current, ...next.filter((thread) => !seen.has(thread.thread_id))];
}

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
      () =>
        reject(new Error("历史记录服务暂时不可用，请检查 Agent 服务后重试。")),
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
