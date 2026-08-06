import { useCallback, useMemo } from "react";
import { Message } from "@langchain/langgraph-sdk";
import { isRenderableAssistantMessage } from "./messages/ai";
import { DO_NOT_RENDER_ID_PREFIX } from "@/lib/ensure-tool-responses";
import { getContentString } from "./utils";
import { resultEnvelopeFromToolResult } from "@/types/agent-block";
import {
  buildProcessRunTurnMap,
  reduceProcessEvents,
  type ProcessEvent,
} from "./process-events";

export type ProcessRun = {
  runId: string;
  messageId?: string;
  events: ProcessEvent[];
  elapsedSeconds: number;
};

export type ProcessPresentation = {
  events: ProcessEvent[];
  isRunning: boolean;
  elapsedSeconds: number;
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
    const internalMessages = messages.filter(
      (message) =>
        message.type === "ai" &&
        "tool_calls" in message &&
        !!message.tool_calls?.length,
    );
    return messages.filter(
      (message) =>
        !message.id?.startsWith(DO_NOT_RENDER_ID_PREFIX) &&
        !internalMessages.includes(message) &&
        isRenderableAssistantMessage(message),
    );
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
  const currentTurnHasAssistant = useMemo(
    () =>
      visibleMessages.some((message) => {
        if (
          message.type !== "ai" ||
          getContentString(message.content).length === 0
        ) {
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
      const events =
        turnIndex === currentTurnIndex &&
        (isLoading || persistedRunsForTurn.length === 0)
          ? eventsForCurrentTurn.length > 0
            ? eventsForCurrentTurn
            : [
                {
                  id: `pending-${humanMessageId ?? "current"}`,
                  type: "message" as const,
                  text: "正在连接 Agent…",
                  source: "custom" as const,
                },
              ]
          : reduceProcessEvents(persistedEventsForTurn);
      if (!events.length) return null;
      return {
        events,
        isRunning: isLoading && turnIndex === humanMessageIndexes.length - 1,
        elapsedSeconds:
          turnIndex === humanMessageIndexes.length - 1 &&
          processStartedAt !== null
            ? processElapsedSeconds
            : persistedElapsedSeconds,
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
    currentTurnHasAssistant,
    currentInterrupt,
    primaryResultMessageBySourceId,
    processForTurn,
  };
}
