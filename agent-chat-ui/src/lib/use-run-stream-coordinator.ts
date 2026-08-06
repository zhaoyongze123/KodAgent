import { useEffect, useRef, useState } from "react";
import {
  acquireDurableRunReconciliation,
  reconcileDurableRun,
} from "@/lib/run-stream-coordinator";
import { createAgentJoinStreamOptions } from "@/lib/agent-stream-options";
import { readLiveRunId } from "@/lib/run-stream-attachment";

type CoordinatorStream = {
  client: {
    runs: {
      get: (threadId: string, runId: string) => Promise<{ status?: unknown }>;
    };
  };
  error: unknown;
  joinStream: (
    runId: string,
    lastEventId?: string,
    options?: { streamMode?: import("@langchain/langgraph-sdk").StreamMode[] },
  ) => Promise<void>;
};

export function useRunStreamCoordinator({
  threadId,
  stream,
  isLoading,
  recoveryRunId,
  clearRecoveryRun,
}: {
  threadId: string | null;
  stream: CoordinatorStream;
  isLoading: boolean;
  recoveryRunId: string | null;
  clearRecoveryRun: (runId: string) => void;
}): { recoveringRunId: string | null } {
  const [persistedLiveRunId, setPersistedLiveRunId] = useState<string | null>(
    null,
  );
  const [recoveringRunId, setRecoveringRunId] = useState<string | null>(null);
  const attemptsRef = useRef(new Map<string, number>());
  const streamRef = useRef(stream);
  const clearRecoveryRunRef = useRef(clearRecoveryRun);
  streamRef.current = stream;
  clearRecoveryRunRef.current = clearRecoveryRun;

  useEffect(() => {
    if (typeof window === "undefined" || !threadId) {
      setPersistedLiveRunId(null);
      return;
    }
    setPersistedLiveRunId(readLiveRunId(window.sessionStorage, threadId));
  }, [threadId]);

  useEffect(() => {
    const runId = recoveryRunId ?? persistedLiveRunId;
    if (!runId || !threadId || isLoading) {
      if (!recoveryRunId && !persistedLiveRunId) setRecoveringRunId(null);
      return;
    }

    const attempts = attemptsRef.current.get(runId) ?? 0;
    attemptsRef.current.set(runId, attempts + 1);
    let disposed = false;
    setRecoveringRunId(runId);

    const recover = async () => {
      try {
        const attachment = acquireDurableRunReconciliation(runId, () =>
          reconcileDurableRun({
            threadId,
            runId,
            attempts,
            storage:
              typeof window === "undefined" ? null : window.sessionStorage,
            getStatus: () => streamRef.current.client.runs.get(threadId, runId),
            joinStream: () =>
              streamRef.current.joinStream(
                runId,
                undefined,
                createAgentJoinStreamOptions(),
              ),
          }),
        );
        const result = await attachment.promise;
        if (disposed) return;

        if (result === "terminal") {
          setPersistedLiveRunId(null);
          if (!streamRef.current.error) clearRecoveryRunRef.current(runId);
        }
      } catch {
        // Keep the durable marker and the error state for the next bounded
        // recovery or a page refresh. No second attachment is created here.
      } finally {
        if (!disposed) setRecoveringRunId(null);
      }
    };

    void recover();
    return () => {
      disposed = true;
    };
  }, [isLoading, persistedLiveRunId, recoveryRunId, threadId]);

  return { recoveringRunId };
}
