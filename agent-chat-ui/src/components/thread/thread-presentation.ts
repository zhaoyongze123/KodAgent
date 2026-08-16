import { useCallback, useMemo } from "react";
import { Message } from "@langchain/langgraph-sdk";
import {
  isCommittedFinalAssistantMessage,
  isInternalAssistantMessage,
  isRenderableAssistantMessage,
} from "./messages/ai";
import { rawAssistantMessagePresentation } from "../../lib/assistant-message-presentation.ts";
import { DO_NOT_RENDER_ID_PREFIX } from "@/lib/ensure-tool-responses";
import { getContentString } from "./utils";
import { resultEnvelopeFromToolResult } from "@/types/agent-block";
import {
  buildProcessRunTurnMap,
  reduceProcessEvents,
  type ProcessEvent,
  type PersistedRunFailure,
  type ProcessRun,
} from "./process-events";

export type { ProcessRun } from "./process-events";

export type ProcessPresentation = {
  events: ProcessEvent[];
  isRunning: boolean;
  elapsedSeconds: number;
  failure?: PersistedRunFailure;
};

type Options = {
  messages: Message[];
  persistedProcessRuns: ProcessRun[];
  customProcessEvents: ProcessEvent[];
  currentTurnMessageId?: string;
  currentInterrupt: unknown;
  isLoading: boolean;
  processElapsedSeconds: number;
  processStartedAt: number | null;
};

/** Pure presentation model for transcript, process history and HITL slots. */
export function useThreadPresentation({
  messages,
  persistedProcessRuns,
  customProcessEvents,
  currentTurnMessageId,
  currentInterrupt,
  isLoading,
  processElapsedSeconds,
  processStartedAt,
}: Options) {
  const visibleMessages = useMemo(() => {
    const firstV2Presentation = messages.findIndex(
      (message) =>
        rawAssistantMessagePresentation(message)?.schemaVersion === 2,
    );

    return messages.filter((message, index) => {
      if (
        message.id?.startsWith(DO_NOT_RENDER_ID_PREFIX) ||
        isInternalAssistantMessage(message)
      ) {
        return false;
      }
      if (isRenderableAssistantMessage(message)) return true;

      // Threads written before this contract contain no presentation marker.
      // Keep that transcript readable, but only before the first v2 message.
      // New malformed messages after v2 still fail closed.
      return (
        message.type === "ai" &&
        (firstV2Presentation < 0 || index < firstV2Presentation) &&
        getContentString(message.content).trim().length > 0
      );
    });
  }, [messages]);

  const humanMessageIndexes = useMemo(
    () =>
      messages.reduce<number[]>((indexes, message, messageIndex) => {
        if (message.type === "human") indexes.push(messageIndex);
        return indexes;
      }, []),
    [messages],
  );
  const messageIndexById = useMemo(
    () =>
      new Map(
        messages.map((message, messageIndex) => [message.id, messageIndex]),
      ),
    [messages],
  );
  const currentTurnIndex = humanMessageIndexes.length - 1;
  const currentTurnStart =
    currentTurnIndex >= 0 ? humanMessageIndexes[currentTurnIndex] : -1;
  const currentTurnHasCommittedFinal = useMemo(
    () =>
      visibleMessages.some((message) => {
        if (!isCommittedFinalAssistantMessage(message)) {
          return false;
        }
        const messageIndex = message.id
          ? messageIndexById.get(message.id)
          : undefined;
        return messageIndex !== undefined && messageIndex > currentTurnStart;
      }),
    [currentTurnStart, messageIndexById, visibleMessages],
  );

  const processRunTurnMap = useMemo(
    () =>
      buildProcessRunTurnMap(
        persistedProcessRuns,
        customProcessEvents,
        currentTurnMessageId,
      ),
    [customProcessEvents, currentTurnMessageId, persistedProcessRuns],
  );

  const primaryResultMessageBySourceId = useMemo(() => {
    const result = new Map<string, string>();
    messages.forEach((candidate) => {
      if (candidate.type !== "tool" || !candidate.id) return;
      const envelope = resultEnvelopeFromToolResult(
        candidate.content,
        candidate.id,
      );
      if (envelope?.sourceResultId) {
        result.set(envelope.sourceResultId, candidate.id);
      }
    });
    return result;
  }, [messages]);

  const processForTurn = useCallback(
    (
      message: Message,
      allowWithoutAssistant = false,
    ): ProcessPresentation | null => {
      const fullIndex = message.id
        ? messageIndexById.get(message.id)
        : undefined;
      if (fullIndex === undefined) return null;
      const turnIndex = humanMessageIndexes.findLastIndex((humanIndex) =>
        message.type === "human"
          ? humanIndex <= fullIndex
          : humanIndex < fullIndex,
      );
      if (turnIndex < 0) return null;
      const turnStart = humanMessageIndexes[turnIndex];
      const turnEnd = humanMessageIndexes[turnIndex + 1] ?? messages.length;
      const nextVisibleAssistant = visibleMessages.find(
        (candidate, candidateIndex) => {
          if (candidateIndex <= visibleMessages.indexOf(message)) return false;
          const candidateIndexInMessages = candidate.id
            ? messageIndexById.get(candidate.id)
            : undefined;
          return (
            candidate.type === "ai" &&
            candidateIndexInMessages !== undefined &&
            candidateIndexInMessages > turnStart &&
            candidateIndexInMessages < turnEnd &&
            getContentString(candidate.content).length > 0
          );
        },
      );
      if (
        message.type !== "human" &&
        nextVisibleAssistant &&
        !allowWithoutAssistant
      ) {
        return null;
      }

      const humanMessageId = messages[turnStart]?.id;
      const allowSingleUnboundRunFallback =
        persistedProcessRuns.length === 1 && humanMessageIndexes.length === 1;
      const persistedRunsForTurn = persistedProcessRuns.filter(
        (run) =>
          (!!humanMessageId && run.messageId === humanMessageId) ||
          processRunTurnMap.get(run.runId) === humanMessageId ||
          (!run.messageId && allowSingleUnboundRunFallback),
      );
      const persistedEventsForTurn = reduceProcessEvents(
        persistedRunsForTurn.flatMap((run) => run.events),
      );
      const persistedElapsedSeconds = persistedRunsForTurn.reduce(
        (total, run) => total + run.elapsedSeconds,
        0,
      );
      const failure = persistedRunsForTurn.findLast((run) => run.failure)?.failure;
      const customEventsForCurrentTurn =
        turnIndex === currentTurnIndex
          ? customProcessEvents.filter(
              (event) =>
                !event.runId ||
                processRunTurnMap.get(event.runId) === humanMessageId,
            )
          : [];
      const eventsForCurrentTurn = reduceProcessEvents([
        ...persistedEventsForTurn,
        ...customEventsForCurrentTurn,
      ]);
      // 当前回合在流结束后仍保留实时事件，等待 Java 持久化回放追上来。
      // 两者会经过同一个 entryId/revision 归并器，因此不会重复，也不会因为
      // 持久化存在几百毫秒延迟而让模型摘要从页面上消失。
      const events =
        turnIndex === currentTurnIndex
          ? eventsForCurrentTurn
          : reduceProcessEvents(persistedEventsForTurn);
      // ProcessRun 是运行头部的事实源，events 只决定是否展示展开后的摘要和工具。
      // 因此一个纯正文回复在持久化后仍保留玻璃球和耗时，而不是随正文出现而消失。
      if (!events.length && persistedRunsForTurn.length === 0) return null;
      return {
        events,
        isRunning: isLoading && turnIndex === humanMessageIndexes.length - 1,
        elapsedSeconds:
          turnIndex === humanMessageIndexes.length - 1 &&
          processStartedAt !== null
            ? processElapsedSeconds
            : persistedElapsedSeconds,
        ...(failure ? { failure } : {}),
      };
    },
    [
      customProcessEvents,
      currentTurnIndex,
      humanMessageIndexes,
      isLoading,
      messageIndexById,
      messages,
      persistedProcessRuns,
      processElapsedSeconds,
      processRunTurnMap,
      processStartedAt,
      visibleMessages,
    ],
  );

  return {
    visibleMessages,
    currentTurnStart,
    currentTurnHasCommittedFinal,
    currentInterrupt,
    primaryResultMessageBySourceId,
    processForTurn,
  };
}
