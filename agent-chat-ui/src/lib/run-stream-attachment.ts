/**
 * Coordinates live stream attachments by LangGraph run ID.
 *
 * The LangGraph React SDK serializes streams internally, but it does not know
 * that our mount recovery and transport-error recovery are the same logical
 * attachment. Keeping this small registry outside React makes concurrent
 * recovery requests share one join promise instead of queueing two joins for
 * the same run.
 */

export const LIVE_RUN_STORAGE_PREFIX = "lg:stream:";

export type RunStreamAttachmentToken = Readonly<{
  runId: string;
  generation: number;
}>;

type AttachmentEntry<T> = {
  token: RunStreamAttachmentToken;
  promise: Promise<T>;
};

const activeAttachments = new Map<string, AttachmentEntry<unknown>>();
let nextGeneration = 0;

export function liveRunStorageKey(threadId: string): string {
  return `${LIVE_RUN_STORAGE_PREFIX}${threadId}`;
}

export function readLiveRunId(
  storage: Pick<Storage, "getItem"> | null | undefined,
  threadId: string | null | undefined,
): string | null {
  if (!storage || !threadId) return null;
  const runId = storage.getItem(liveRunStorageKey(threadId));
  return runId?.trim() || null;
}

export function clearLiveRunId(
  storage:
    | (Pick<Storage, "removeItem"> & Partial<Pick<Storage, "getItem">>)
    | null
    | undefined,
  threadId: string | null | undefined,
  expectedRunId?: string,
): void {
  if (!storage || !threadId) return;
  if (
    expectedRunId &&
    storage.getItem &&
    storage.getItem(liveRunStorageKey(threadId)) !== expectedRunId
  ) {
    return;
  }
  storage.removeItem(liveRunStorageKey(threadId));
}

export function storeLiveRunId(
  storage: Pick<Storage, "setItem"> | null | undefined,
  threadId: string | null | undefined,
  runId: string,
): void {
  if (!storage || !threadId || !runId) return;
  storage.setItem(liveRunStorageKey(threadId), runId);
}

/**
 * Return the active attachment for a run, if any.
 * Primarily useful for diagnostics and deterministic tests.
 */
export function getRunStreamAttachment(
  runId: string,
): RunStreamAttachmentToken | null {
  return activeAttachments.get(runId)?.token ?? null;
}

/**
 * Start one attachment for a run, or share the already active attachment.
 */
export function acquireRunStreamAttachment<T>(
  runId: string,
  attach: () => Promise<T>,
): { token: RunStreamAttachmentToken; promise: Promise<T>; reused: boolean } {
  const current = activeAttachments.get(runId);
  if (current) {
    return {
      token: current.token,
      promise: current.promise as Promise<T>,
      reused: true,
    };
  }

  const token: RunStreamAttachmentToken = {
    runId,
    generation: ++nextGeneration,
  };

  const entry = {
    token,
    promise: undefined as unknown as Promise<T>,
  } satisfies AttachmentEntry<T>;
  const promise = Promise.resolve()
    .then(attach)
    .finally(() => {
      if (activeAttachments.get(runId) === entry) {
        activeAttachments.delete(runId);
      }
    });
  entry.promise = promise;
  activeAttachments.set(runId, entry);

  return { token, promise, reused: false };
}

/**
 * Release only the generation that acquired the attachment. A late cleanup
 * from an older recovery cannot release a newer attachment for the same run.
 */
export function releaseRunStreamAttachment(
  token: RunStreamAttachmentToken,
): boolean {
  const current = activeAttachments.get(token.runId);
  if (!current || current.token.generation !== token.generation) return false;
  activeAttachments.delete(token.runId);
  return true;
}

/** Test-only reset that does not leak state between unit tests. */
export function resetRunStreamAttachmentsForTests(): void {
  activeAttachments.clear();
  nextGeneration = 0;
}
