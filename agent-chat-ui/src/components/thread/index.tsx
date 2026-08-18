import { v4 as uuidv4 } from "uuid";
import { Fragment, ReactNode, useCallback, useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { type StateType, useStreamContext } from "@/providers/Stream";
import { useState, FormEvent } from "react";
import { Button } from "../ui/button";
import { Checkpoint, Message } from "@langchain/langgraph-sdk";
import {
  AssistantMessage,
  InterruptSlot,
  StreamingAssistantMessage,
} from "./messages/ai";
import { HumanMessage } from "./messages/human";
import { ensureToolCallsHaveResponses } from "@/lib/ensure-tool-responses";
import { TooltipIconButton } from "./tooltip-icon-button";
import {
  ArrowDown,
  ArrowUp,
  BrainCircuit,
  Check,
  ChevronDown,
  LoaderCircle,
  PanelRightOpen,
  PanelRightClose,
  SquarePen,
  XIcon,
  Plus,
  ChevronRight,
  Building2,
  CalendarDays,
  ClipboardList,
  Cloud,
  FileText,
  RefreshCw,
  type LucideIcon,
} from "lucide-react";
import { useQueryState, parseAsBoolean, parseAsString } from "nuqs";
import { StickToBottom, useStickToBottomContext } from "use-stick-to-bottom";
import ThreadHistory from "./history";
import { toast } from "sonner";
import { ErrorCard } from "./cards/ErrorCard";
import {
  normalizeAgentError,
  normalizePersistedRunFailure,
} from "@/lib/agent-error";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { Label } from "../ui/label";
import { Switch } from "../ui/switch";
import { SUPPORTED_FILE_TYPES, useFileUpload } from "@/hooks/use-file-upload";
import { ContentBlocksPreview } from "./ContentBlocksPreview";
import {
  useArtifactOpen,
  ArtifactContent,
  ArtifactTitle,
  useArtifactContext,
} from "./artifact";
import {
  collectCustomProcessEvents,
  reduceProcessEvents,
  type ProcessRun,
} from "./process-events";
import {
  maxDurableEventCursor,
  mergePersistedProcessRuns,
} from "@/lib/persisted-event-recovery";
import { useThreadPresentation } from "./thread-presentation";
import {
  hasPersistedRunTerminalEvent,
  parsePersistedProcessRuns,
} from "@/lib/persisted-process-runs";
import { createAgentStreamOptions } from "@/lib/agent-stream-options";
import { ResultRenderScope } from "./results/result-render-context";
import { modelSupportsAgentTools } from "@/lib/model-capabilities";
import { RunActivity } from "./run-activity";

function StickyToBottomContent(props: {
  content: ReactNode;
  footer?: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  const context = useStickToBottomContext();
  return (
    <div
      ref={context.scrollRef}
      style={{ width: "100%", height: "100%" }}
      className={props.className}
    >
      <div
        ref={context.contentRef}
        className={props.contentClassName}
      >
        {props.content}
      </div>

      {props.footer}
    </div>
  );
}

function ScrollToBottom(props: { className?: string }) {
  const { isAtBottom, scrollToBottom } = useStickToBottomContext();

  if (isAtBottom) return null;
  return (
    <Button
      variant="outline"
      className={props.className}
      onClick={() => scrollToBottom()}
    >
      <ArrowDown className="h-4 w-4" />
      <span>Scroll to bottom</span>
    </Button>
  );
}

const welcomeShortcuts: Array<{
  icon: LucideIcon;
  title: string;
  prompt: string;
  iconClassName: string;
}> = [
  {
    icon: ClipboardList,
    title: "查询我的待办审批",
    prompt: "查询我的待办审批",
    iconClassName: "text-blue-600",
  },
  {
    icon: CalendarDays,
    title: "查看我明天的日程",
    prompt: "查看我明天的日程",
    iconClassName: "text-violet-600",
  },
  {
    icon: Building2,
    title: "帮我预约一个会议室",
    prompt: "帮我预约明天下午 3 点到 5 点的会议室",
    iconClassName: "text-emerald-600",
  },
  {
    icon: FileText,
    title: "搜索党务文件",
    prompt: "帮我搜索党务文件",
    iconClassName: "text-orange-600",
  },
];

const reasoningOptions = [
  { value: "auto", label: "自动", description: "由模型自行决定" },
  { value: "low", label: "低", description: "更快，适合简单查询" },
  { value: "medium", label: "中", description: "速度与分析的平衡" },
  { value: "high", label: "高", description: "适合复杂业务任务" },
] as const;

type ReasoningEffort = (typeof reasoningOptions)[number]["value"];

type SelectableModel = {
  id: number;
  model_name: string;
  display_name?: string;
  provider_name?: string;
  capabilities?: Record<string, boolean> | string;
};

function modelSupportsTools(model: SelectableModel): boolean {
  return modelSupportsAgentTools(model.capabilities);
}

function ConnectionStatus({
  error,
  onRetry,
}: {
  error: ReturnType<typeof normalizeAgentError>;
  onRetry: () => void;
}) {
  const isConnectionFailure = ["UPSTREAM_TIMEOUT", "UNKNOWN"].includes(
    error.code,
  );
  if (!isConnectionFailure) return null;

  return (
    <div
      className="border-border bg-muted/40 text-muted-foreground mx-auto flex w-full max-w-3xl items-center gap-3 rounded-lg border px-3 py-2 text-xs"
      role="status"
      aria-live="polite"
    >
      <span className="size-2 shrink-0 rounded-full bg-amber-500" />
      <span className="min-w-0 flex-1 text-pretty">
        连接已中断，已保留当前执行过程。可以重试本轮，或稍后继续。
      </span>
      <button
        type="button"
        onClick={onRetry}
        className="text-foreground hover:bg-muted inline-flex shrink-0 items-center gap-1 rounded-md border bg-white px-2 py-1 font-medium"
      >
        <RefreshCw
          aria-hidden="true"
          className="size-3"
        />
        重试
      </button>
    </div>
  );
}

export function Thread() {
  const [artifactContext, setArtifactContext] = useArtifactContext();
  const [artifactOpen, closeArtifact] = useArtifactOpen();

  const [threadId, _setThreadId] = useQueryState("threadId");
  const [modelId, setModelId] = useQueryState("modelId");
  const [reasoningEffortRaw, setReasoningEffort] = useQueryState(
    "reasoningEffort",
    parseAsString.withDefault("auto"),
  );
  const [modelMenuSection, setModelMenuSection] = useState<
    "model" | "reasoning" | null
  >(null);
  const [availableModels, setAvailableModels] = useState<SelectableModel[]>([]);
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );
  const [hideToolCalls, setHideToolCalls] = useQueryState(
    "hideToolCalls",
    parseAsBoolean.withDefault(false),
  );
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const {
    contentBlocks,
    setContentBlocks,
    handleFileUpload,
    dropRef,
    removeBlock,
    resetBlocks: _resetBlocks,
    dragOver,
    handlePaste,
  } = useFileUpload();
  const processStartedAt = useRef<number | null>(null);
  const [processElapsedSeconds, setProcessElapsedSeconds] = useState(0);
  const [persistedProcessRuns, setPersistedProcessRuns] = useState<
    ProcessRun[]
  >([]);
  const [persistedProcessError, setPersistedProcessError] = useState<
    string | undefined
  >();
  const [persistedInterrupt, setPersistedInterrupt] = useState<unknown>();
  const persistedEventCursorRef = useRef<number | undefined>(undefined);
  const recoveredRunRef = useRef<string | null>(null);
  const lastObservedRunIdRef = useRef<string | null>(null);
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");

  const stream = useStreamContext();
  const messages = stream.messages;
  const isLoading = stream.isLoading;
  const customProcessEvents = collectCustomProcessEvents(stream.processEvents);
  const recoveringRunId = stream.recoveringRunId;
  const currentTurnMessageId = (() => {
    const human = messages.filter((message) => message.type === "human");
    return human.at(-1)?.id;
  })();

  useEffect(() => {
    if (stream.currentRunId) {
      lastObservedRunIdRef.current = stream.currentRunId;
    }
  }, [stream.currentRunId]);
  const presentation = useThreadPresentation({
    messages,
    persistedProcessRuns,
    customProcessEvents,
    currentTurnMessageId,
    currentInterrupt: stream.interrupt ?? persistedInterrupt,
    isLoading,
    processElapsedSeconds,
    processStartedAt: processStartedAt.current,
  });

  const selectedModel = availableModels.find(
    (model) => String(model.id) === modelId,
  );
  const selectedReasoning =
    reasoningOptions.find((option) => option.value === reasoningEffortRaw) ??
    reasoningOptions[0];
  const reasoningEffort: ReasoningEffort = selectedReasoning.value;
  const modelLabel = selectedModel?.model_name ?? "默认模型";

  useEffect(() => {
    fetch("/api/agent-models", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : []))
      .then((models) => setAvailableModels(Array.isArray(models) ? models : []))
      .catch(() => setAvailableModels([]));
  }, []);

  const loadPersistedProcessRuns = useCallback(
    async (
      signal?: AbortSignal,
      mode: "snapshot" | "cursor" = "snapshot",
      terminalRunId?: string,
    ): Promise<boolean> => {
      if (!threadId) return false;
      try {
        const afterCursor =
          mode === "cursor" ? persistedEventCursorRef.current : undefined;
        const query =
          afterCursor === undefined
            ? ""
            : `?afterCursor=${encodeURIComponent(String(afterCursor))}`;
        const response = await fetch(
          `/api/agent-events/${encodeURIComponent(threadId)}${query}`,
          { signal, cache: "no-store" },
        );
        if (!response.ok) {
          setPersistedProcessError(`过程事件服务返回 ${response.status}`);
          return false;
        }
        const payload = await response.json();
        setPersistedProcessError(undefined);
        const parsed = parsePersistedProcessRuns(payload);
        const nextCursor = maxDurableEventCursor(payload);
        if (mode === "snapshot") {
          persistedEventCursorRef.current = nextCursor;
          setPersistedProcessRuns(parsed);
          return hasPersistedRunTerminalEvent(payload, terminalRunId ?? "");
        }
        if (
          nextCursor !== undefined &&
          (persistedEventCursorRef.current === undefined ||
            nextCursor > persistedEventCursorRef.current)
        ) {
          persistedEventCursorRef.current = nextCursor;
        }
        if (parsed.length) {
          setPersistedProcessRuns((current) =>
            mergePersistedProcessRuns(current, parsed),
          );
        }
        return hasPersistedRunTerminalEvent(payload, terminalRunId ?? "");
      } catch (error: unknown) {
        if ((error as { name?: string })?.name !== "AbortError") {
          setPersistedProcessError("过程事件服务暂时不可用");
          console.warn("读取 Agent 过程事件失败", error);
        }
        return false;
      }
    },
    [threadId],
  );

  const loadPersistedState = useCallback(
    async (signal?: AbortSignal) => {
      if (!threadId) return;
      try {
        const response = await fetch(
          `/api/agent-state/${encodeURIComponent(threadId)}`,
          { signal, cache: "no-store" },
        );
        if (!response.ok) return;
        const payload = await response.json();
        const interrupts = Array.isArray(payload?.interrupts)
          ? payload.interrupts
          : [];
        setPersistedInterrupt(interrupts.length > 0 ? interrupts : undefined);
      } catch (error: unknown) {
        if ((error as { name?: string })?.name !== "AbortError") {
          console.warn("读取 LangGraph 中断状态失败", error);
        }
      }
    },
    [threadId],
  );

  useEffect(() => {
    setPersistedProcessRuns([]);
    setPersistedProcessError(undefined);
    setPersistedInterrupt(undefined);
    persistedEventCursorRef.current = undefined;
    recoveredRunRef.current = null;
    lastObservedRunIdRef.current = null;
    if (!threadId) return;

    const controller = new AbortController();
    void loadPersistedProcessRuns(controller.signal);
    void loadPersistedState(controller.signal);

    return () => controller.abort();
  }, [loadPersistedProcessRuns, loadPersistedState, threadId]);

  useEffect(() => {
    if (!threadId) return;
    const refresh = () => void loadPersistedState();
    if (!isLoading) return;
    const timer = window.setInterval(() => {
      refresh();
      void loadPersistedProcessRuns(undefined, "cursor");
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isLoading, loadPersistedProcessRuns, loadPersistedState, threadId]);

  useEffect(() => {
    if (!recoveringRunId) {
      recoveredRunRef.current = null;
      return;
    }
    if (recoveredRunRef.current === recoveringRunId) return;
    recoveredRunRef.current = recoveringRunId;
    const controller = new AbortController();
    // A transport recovery is a Snapshot boundary. It catches an updated
    // narration whose event identity/cursor was retained by Java's upsert
    // contract, while the following stream/poll continues from the cursor.
    void loadPersistedProcessRuns(controller.signal, "snapshot");
    return () => controller.abort();
  }, [loadPersistedProcessRuns, recoveringRunId]);

  const wasLoading = useRef(false);
  useEffect(() => {
    const finishedRun = wasLoading.current && !isLoading;
    wasLoading.current = isLoading;
    const completedRunId = lastObservedRunIdRef.current;
    if (!finishedRun || !threadId || !completedRunId) {
      return;
    }

    // Python writes process facts to its durable Outbox and the Java event
    // service receives them asynchronously. A single 300ms refresh races the
    // normal two-second publisher interval. Keep reading the cursor for one
    // bounded hand-off window, and stop as soon as Java has the terminal Run
    // fact. The browser never fabricates completion or stores event history.
    let disposed = false;
    const catchUp = async () => {
      for (let attempt = 0; attempt < 7 && !disposed; attempt += 1) {
        const terminal = await loadPersistedProcessRuns(
          undefined,
          attempt === 0 ? "snapshot" : "cursor",
          completedRunId,
        );
        if (terminal || disposed) return;
        await new Promise((resolve) => window.setTimeout(resolve, 500));
      }
    };
    void catchUp();
    return () => {
      disposed = true;
    };
  }, [
    isLoading,
    loadPersistedProcessRuns,
    threadId,
  ]);

  useEffect(() => {
    if (isLoading && processStartedAt.current === null) {
      processStartedAt.current = Date.now();
    }
    if (processStartedAt.current === null) return;

    const updateElapsed = () => {
      setProcessElapsedSeconds(
        Math.floor((Date.now() - processStartedAt.current!) / 1000),
      );
    };
    updateElapsed();
    if (!isLoading) return;

    const timer = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(timer);
  }, [isLoading]);

  const lastError = useRef<string | undefined>(undefined);

  const setThreadId = (id: string | null) => {
    _setThreadId(id);

    processStartedAt.current = null;
    setProcessElapsedSeconds(0);
    setPersistedProcessRuns([]);
    persistedEventCursorRef.current = undefined;
    recoveredRunRef.current = null;
    // close artifact and reset artifact context
    closeArtifact();
    setArtifactContext({});
  };

  useEffect(() => {
    if (!stream.error) {
      lastError.current = undefined;
      return;
    }
    try {
      const message = (stream.error as any).message;
      if (!message || lastError.current === message) {
        // Message has already been logged. do not modify ref, return early.
        return;
      }

      // Message is defined, and it has not been logged yet. Save it, and send the error
      lastError.current = message;
      const normalized = normalizeAgentError(stream.error);
      toast.error(normalized.message, {
        description: normalized.detail,
        richColors: true,
        closeButton: true,
      });
    } catch {
      // no-op
    }
  }, [stream.error]);

  const normalizedStreamError = stream.error
    ? normalizeAgentError(stream.error)
    : undefined;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if ((input.trim().length === 0 && contentBlocks.length === 0) || isLoading)
      return;
    if (selectedModel && !modelSupportsTools(selectedModel)) {
      toast.error("当前模型不支持 Agent 工具调用", {
        description:
          "请切换到支持 Function Calling / Tool Calling 的模型后再发送。",
        closeButton: true,
      });
      setModelMenuSection("model");
      return;
    }
    processStartedAt.current = Date.now();
    setProcessElapsedSeconds(0);
    const traceId = crypto.randomUUID();
    stream.setTraceId(traceId);
    console.info(
      JSON.stringify({
        source: "kodagent.ui",
        traceId,
        phase: "user.submit",
        elapsedMs: 0,
      }),
    );

    const newHumanMessage: Message = {
      id: uuidv4(),
      type: "human",
      content: [
        ...(input.trim().length > 0 ? [{ type: "text", text: input }] : []),
        ...contentBlocks,
      ] as Message["content"],
    };

    const toolMessages = ensureToolCallsHaveResponses(stream.messages);

    const context =
      Object.keys(artifactContext).length > 0 ? artifactContext : undefined;

    stream.submit(
      { messages: [...toolMessages, newHumanMessage], context },
      createAgentStreamOptions({
        metadata: {
          messageId: newHumanMessage.id,
          traceId,
          ...(modelId ? { modelId } : {}),
          reasoningEffort: reasoningEffort ?? "auto",
        },
        optimisticValues: (prev: StateType) => ({
          ...prev,
          context,
          messages: [
            ...(prev.messages ?? []),
            ...toolMessages,
            newHumanMessage,
          ],
        }),
      }),
    );

    setInput("");
    setContentBlocks([]);
  };

  const handleRegenerate = (
    parentCheckpoint: Checkpoint | null | undefined,
  ) => {
    const traceId = crypto.randomUUID();
    stream.setTraceId(traceId);
    console.info(
      JSON.stringify({
        source: "kodagent.ui",
        traceId,
        phase: "user.regenerate",
        elapsedMs: 0,
      }),
    );
    const currentMessageId = [...messages]
      .reverse()
      .find((message) => message.type === "human")?.id;
    stream.submit(
      undefined,
      createAgentStreamOptions({
        checkpoint: parentCheckpoint,
        ...(currentMessageId && {
          metadata: {
            messageId: currentMessageId,
            traceId,
            ...(modelId ? { modelId } : {}),
            reasoningEffort: reasoningEffort ?? "auto",
          },
        }),
      }),
    );
  };

  const chatStarted = !!threadId || !!messages.length;

  return (
    <div className="flex h-dvh w-full overflow-hidden">
      <div className="relative hidden lg:flex">
        <motion.div
          className="absolute z-20 h-full overflow-hidden border-r bg-white"
          style={{ width: 300 }}
          animate={
            isLargeScreen
              ? { x: chatHistoryOpen ? 0 : -300 }
              : { x: chatHistoryOpen ? 0 : -300 }
          }
          initial={{ x: -300 }}
          transition={
            isLargeScreen
              ? { type: "spring", stiffness: 300, damping: 30 }
              : { duration: 0 }
          }
        >
          <div
            className="relative h-full"
            style={{ width: 300 }}
          >
            <ThreadHistory />
          </div>
        </motion.div>
      </div>

      <div
        className={cn(
          "grid w-full grid-cols-[1fr_0fr] transition-all duration-500",
          artifactOpen && "grid-cols-[3fr_2fr]",
        )}
      >
        <motion.div
          className={cn(
            "relative flex min-w-0 flex-1 flex-col overflow-hidden",
            !chatStarted && "grid-rows-[1fr]",
          )}
          layout={isLargeScreen}
          animate={{
            marginLeft: chatHistoryOpen ? (isLargeScreen ? 300 : 0) : 0,
            width: chatHistoryOpen
              ? isLargeScreen
                ? "calc(100% - 300px)"
                : "100%"
              : "100%",
          }}
          transition={
            isLargeScreen
              ? { type: "spring", stiffness: 300, damping: 30 }
              : { duration: 0 }
          }
        >
          {!chatStarted && (
            <div className="absolute top-0 left-0 z-10 flex w-full items-center justify-between gap-3 p-2 pl-4">
              <div>
                {(!chatHistoryOpen || !isLargeScreen) && (
                  <Button
                    className="hover:bg-gray-100"
                    variant="ghost"
                    onClick={() => setChatHistoryOpen((p) => !p)}
                  >
                    {chatHistoryOpen ? (
                      <PanelRightOpen className="size-5" />
                    ) : (
                      <PanelRightClose className="size-5" />
                    )}
                  </Button>
                )}
              </div>
            </div>
          )}
          {chatStarted && (
            <div className="relative z-10 flex items-center justify-between gap-3 p-2">
              <div className="relative flex items-center justify-start gap-2">
                <div className="absolute left-0 z-10">
                  {(!chatHistoryOpen || !isLargeScreen) && (
                    <Button
                      className="hover:bg-gray-100"
                      variant="ghost"
                      onClick={() => setChatHistoryOpen((p) => !p)}
                    >
                      {chatHistoryOpen ? (
                        <PanelRightOpen className="size-5" />
                      ) : (
                        <PanelRightClose className="size-5" />
                      )}
                    </Button>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-4">
                <TooltipIconButton
                  size="lg"
                  className="p-4"
                  tooltip="New thread"
                  variant="ghost"
                  onClick={() => setThreadId(null)}
                >
                  <SquarePen className="size-5" />
                </TooltipIconButton>
              </div>

              <div className="from-background to-background/0 absolute inset-x-0 top-full h-5 bg-gradient-to-b" />
            </div>
          )}

          <StickToBottom className="relative flex-1 overflow-hidden">
            <StickyToBottomContent
              className={cn(
                "absolute inset-0 overflow-y-scroll px-4 [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent",
                !chatStarted && "mt-[25vh] flex flex-col items-stretch",
                chatStarted && "grid grid-rows-[1fr_auto]",
              )}
              contentClassName="pt-8 pb-16 max-w-3xl mx-auto flex flex-col gap-4 w-full"
              content={
                <>
                  {!chatStarted && (
                    <section className="kodagent-welcome mx-auto flex w-full max-w-5xl flex-col items-center px-2 pt-10 pb-8 text-center">
                      <Cloud className="mb-5 size-10 stroke-[1.5] text-slate-400" />
                      <h1 className="text-3xl font-light tracking-[-0.02em] text-balance text-slate-900 sm:text-4xl">
                        你想让 KodAgent 帮你做什么？
                      </h1>
                      <div className="mt-10 grid w-full max-w-4xl grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
                        {welcomeShortcuts.map((shortcut) => {
                          const Icon = shortcut.icon;
                          return (
                            <button
                              key={shortcut.title}
                              type="button"
                              className={cn(
                                "group flex h-40 flex-col items-start justify-between rounded-xl border border-slate-200 bg-white p-5 text-left transition-colors hover:border-slate-300 hover:bg-slate-50 focus-visible:border-slate-400 focus-visible:ring-2 focus-visible:ring-slate-300 focus-visible:outline-none",
                              )}
                              onClick={() => {
                                setInput(shortcut.prompt);
                                requestAnimationFrame(() =>
                                  inputRef.current?.focus(),
                                );
                              }}
                            >
                              <Icon
                                className={cn("size-6", shortcut.iconClassName)}
                              />
                              <span className="text-base leading-6 font-normal text-pretty text-slate-900">
                                {shortcut.title}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </section>
                  )}
                  {(() => {
                    const {
                      visibleMessages,
                      currentTurnStart,
                      currentTurnHasCommittedFinal,
                      currentInterrupt,
                      primaryResultMessageBySourceId,
                      processForTurn,
                    } = presentation;

                    return (
                      <ResultRenderScope
                        primaryMessageBySourceId={
                          primaryResultMessageBySourceId
                        }
                      >
                        {visibleMessages.map((message, index) => (
                          <Fragment
                            key={message.id || `${message.type}-${index}`}
                          >
                            {message.type === "human" ? (
                              <>
                                <HumanMessage
                                  message={message}
                                  isLoading={isLoading}
                                />
                                {(() => {
                                  const process = processForTurn(message);
                                  return (
                                    <>
                                      {(process ||
                                        (message.id ===
                                          messages[currentTurnStart]?.id &&
                                          isLoading)) && (
                                        <RunActivity
                                          events={process?.events ?? []}
                                          elapsedSeconds={
                                            process?.elapsedSeconds ??
                                            processElapsedSeconds
                                          }
                                          isRunning={
                                            process?.isRunning ?? isLoading
                                          }
                                          syncError={persistedProcessError}
                                          hidden={hideToolCalls ?? false}
                                        />
                                      )}
                                      {process?.failure && (
                                        <ErrorCard
                                          error={normalizePersistedRunFailure(
                                            process.failure,
                                          )}
                                          onAction={(action) => {
                                            if (action.type === "retry") {
                                              handleRegenerate(null);
                                            }
                                          }}
                                        />
                                      )}
                                      {message.id ===
                                        messages[currentTurnStart]?.id &&
                                        currentInterrupt && (
                                          <InterruptSlot
                                            interrupt={currentInterrupt}
                                          />
                                        )}
                                    </>
                                  );
                                })()}
                              </>
                            ) : (
                              <AssistantMessage
                                message={message}
                                isLoading={isLoading}
                                handleRegenerate={handleRegenerate}
                              />
                            )}
                          </Fragment>
                        ))}
                        {isLoading &&
                          !currentTurnHasCommittedFinal &&
                          stream.streamedAnswer && (
                            <StreamingAssistantMessage
                              markdown={stream.streamedAnswer.text}
                            />
                          )}
                        {isLoading &&
                          !currentTurnHasCommittedFinal &&
                          currentTurnStart < 0 && (
                            <RunActivity
                              events={reduceProcessEvents(customProcessEvents)}
                              elapsedSeconds={processElapsedSeconds}
                              isRunning={isLoading}
                              syncError={persistedProcessError}
                              hidden={hideToolCalls ?? false}
                            />
                          )}
                        {currentTurnStart < 0 && Boolean(currentInterrupt) && (
                          <InterruptSlot interrupt={currentInterrupt} />
                        )}
                      </ResultRenderScope>
                    );
                  })()}
                  {recoveringRunId && (
                    <div
                      className="text-muted-foreground mx-auto flex w-full max-w-3xl items-center gap-2 px-1 py-2 text-xs"
                      role="status"
                      aria-live="polite"
                    >
                      <LoaderCircle className="size-3 animate-spin" />
                      <span>连接暂时中断，正在恢复当前执行过程…</span>
                    </div>
                  )}
                  {normalizedStreamError &&
                    !recoveringRunId &&
                    (["UPSTREAM_TIMEOUT", "UNKNOWN"].includes(
                      normalizedStreamError.code,
                    ) ? (
                      // A transport failure gets one reconnect/retry status
                      // row. Do not render the same failure again as a second
                      // generic ErrorCard.
                      <ConnectionStatus
                        error={normalizedStreamError}
                        onRetry={() => handleRegenerate(null)}
                      />
                    ) : (
                      <ErrorCard
                        error={normalizedStreamError}
                        onAction={(action) => {
                          if (action.type === "retry") {
                            handleRegenerate(null);
                          }
                        }}
                      />
                    ))}
                </>
              }
              footer={
                <div className="sticky bottom-0 flex flex-col items-center gap-8 bg-white">
                  <ScrollToBottom className="animate-in fade-in-0 zoom-in-95 absolute bottom-full left-1/2 mb-4 -translate-x-1/2" />

                  <div
                    ref={dropRef}
                    className={cn(
                      "bg-muted relative z-10 mx-auto mb-8 w-full max-w-3xl rounded-2xl shadow-xs transition-all",
                      dragOver
                        ? "border-primary border-2 border-dotted"
                        : "border border-solid",
                    )}
                  >
                    <form
                      onSubmit={handleSubmit}
                      className="mx-auto grid max-w-3xl grid-rows-[1fr_auto] gap-2"
                    >
                      <ContentBlocksPreview
                        blocks={contentBlocks}
                        onRemove={removeBlock}
                      />
                      <textarea
                        ref={inputRef}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onPaste={handlePaste}
                        onKeyDown={(e) => {
                          if (
                            e.key === "Enter" &&
                            !e.shiftKey &&
                            !e.metaKey &&
                            !e.nativeEvent.isComposing
                          ) {
                            e.preventDefault();
                            const el = e.target as HTMLElement | undefined;
                            const form = el?.closest("form");
                            form?.requestSubmit();
                          }
                        }}
                        placeholder="Type your message..."
                        className="field-sizing-content resize-none border-none bg-transparent p-3.5 pb-0 shadow-none ring-0 outline-none focus:ring-0 focus:outline-none"
                      />

                      <div className="flex items-center gap-2 p-2 pt-3">
                        <div className="flex items-center gap-2">
                          <Switch
                            id="render-tool-calls"
                            checked={hideToolCalls ?? false}
                            onCheckedChange={setHideToolCalls}
                          />
                          <Label
                            htmlFor="render-tool-calls"
                            className="text-muted-foreground cursor-pointer text-xs"
                          >
                            隐藏工具过程
                          </Label>
                        </div>
                        <Label
                          htmlFor="file-input"
                          className="text-muted-foreground flex cursor-pointer items-center gap-1.5 text-xs"
                        >
                          <Plus className="size-4" />
                          <span>上传文件</span>
                        </Label>
                        <input
                          id="file-input"
                          type="file"
                          onChange={handleFileUpload}
                          multiple
                          accept={SUPPORTED_FILE_TYPES.join(",")}
                          className="hidden"
                        />

                        <div className="relative ml-auto">
                          <button
                            type="button"
                            aria-haspopup="menu"
                            aria-expanded={modelMenuSection !== null}
                            onClick={() =>
                              setModelMenuSection((current) =>
                                current === null ? "model" : null,
                              )
                            }
                            className="bg-background hover:bg-accent flex h-9 max-w-[min(46vw,280px)] items-center gap-2 rounded-full border px-3 text-sm shadow-xs transition-colors"
                          >
                            <span className="truncate font-medium">
                              {modelLabel}
                            </span>
                            <span className="text-muted-foreground shrink-0 text-xs">
                              {selectedReasoning.label}
                            </span>
                            <ChevronDown
                              className={cn(
                                "text-muted-foreground size-4 shrink-0 transition-transform",
                                modelMenuSection !== null && "rotate-180",
                              )}
                            />
                          </button>

                          {modelMenuSection !== null && (
                            <div
                              role="menu"
                              aria-label="模型与推理设置"
                              className="bg-background absolute right-0 bottom-full z-30 mb-2 w-80 rounded-xl border p-1.5 shadow-lg"
                            >
                              <button
                                type="button"
                                role="menuitem"
                                onClick={() => setModelMenuSection("model")}
                                className="hover:bg-accent flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left"
                              >
                                <span className="flex items-center gap-2 font-medium">
                                  <Cloud className="text-muted-foreground size-4" />
                                  模型
                                </span>
                                <span className="text-muted-foreground flex max-w-44 items-center gap-1 truncate text-sm">
                                  {modelLabel}
                                  <ChevronRight className="size-4 shrink-0" />
                                </span>
                              </button>

                              {modelMenuSection === "model" && (
                                <div className="border-border/70 mt-1 max-h-56 space-y-0.5 overflow-y-auto border-t pt-1">
                                  <button
                                    type="button"
                                    role="menuitemradio"
                                    aria-checked={!modelId}
                                    onClick={() => {
                                      setModelId(null);
                                      setModelMenuSection(null);
                                    }}
                                    className="hover:bg-accent flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm"
                                  >
                                    <span>默认模型</span>
                                    {!modelId && <Check className="size-4" />}
                                  </button>
                                  {availableModels.map((model) => {
                                    const isSelected =
                                      String(model.id) === modelId;
                                    const toolsSupported =
                                      modelSupportsTools(model);
                                    return (
                                      <button
                                        key={model.id}
                                        type="button"
                                        role="menuitemradio"
                                        aria-checked={isSelected}
                                        onClick={() => {
                                          if (!toolsSupported) {
                                            toast.error(
                                              "当前模型不支持 Agent 工具调用",
                                              {
                                                description:
                                                  "它只能进行普通对话，无法查询 OA 数据或执行会议室、待办等业务工具。请切换到支持 Function Calling 的模型。",
                                                closeButton: true,
                                              },
                                            );
                                            return;
                                          }
                                          setModelId(String(model.id));
                                          setModelMenuSection(null);
                                        }}
                                        className={cn(
                                          "hover:bg-accent flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm",
                                          !toolsSupported &&
                                            "text-muted-foreground",
                                        )}
                                      >
                                        <span className="min-w-0 truncate">
                                          {model.provider_name
                                            ? `${model.provider_name} / `
                                            : ""}
                                          {model.model_name}
                                          {!toolsSupported && (
                                            <span className="ml-2 text-xs">
                                              仅普通对话
                                            </span>
                                          )}
                                        </span>
                                        {isSelected && (
                                          <Check className="size-4 shrink-0" />
                                        )}
                                      </button>
                                    );
                                  })}
                                </div>
                              )}

                              <button
                                type="button"
                                role="menuitem"
                                onClick={() => setModelMenuSection("reasoning")}
                                className="hover:bg-accent flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left"
                              >
                                <span className="flex items-center gap-2 font-medium">
                                  <BrainCircuit className="text-muted-foreground size-4" />
                                  推理程度
                                </span>
                                <span className="text-muted-foreground flex items-center gap-1 text-sm">
                                  {selectedReasoning.label}
                                  <ChevronRight className="size-4" />
                                </span>
                              </button>

                              {modelMenuSection === "reasoning" && (
                                <div className="border-border/70 mt-1 space-y-0.5 border-t pt-1">
                                  {reasoningOptions.map((option) => (
                                    <button
                                      key={option.value}
                                      type="button"
                                      role="menuitemradio"
                                      aria-checked={
                                        option.value === reasoningEffort
                                      }
                                      onClick={() => {
                                        setReasoningEffort(option.value);
                                        setModelMenuSection(null);
                                      }}
                                      className="hover:bg-accent flex w-full items-center justify-between rounded-lg px-3 py-2 text-left"
                                    >
                                      <span>
                                        <span className="block text-sm">
                                          {option.label}
                                        </span>
                                        <span className="text-muted-foreground block text-xs">
                                          {option.description}
                                        </span>
                                      </span>
                                      {option.value === reasoningEffort && (
                                        <Check className="size-4" />
                                      )}
                                    </button>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                        {stream.isLoading ? (
                          <Button
                            key="stop"
                            onClick={() => stream.stop()}
                            className="ml-auto"
                          >
                            <LoaderCircle className="h-4 w-4 animate-spin" />
                            Cancel
                          </Button>
                        ) : (
                          <Button
                            type="submit"
                            size="icon"
                            aria-label="发送消息"
                            className="size-9 rounded-full shadow-md transition-all"
                            disabled={
                              isLoading ||
                              (!input.trim() && contentBlocks.length === 0)
                            }
                          >
                            <ArrowUp className="size-4" />
                          </Button>
                        )}
                      </div>
                    </form>
                  </div>
                </div>
              }
            />
          </StickToBottom>
        </motion.div>
        <div className="relative flex flex-col border-l">
          <div className="absolute inset-0 flex min-w-[30vw] flex-col">
            <div className="grid grid-cols-[1fr_auto] border-b p-4">
              <ArtifactTitle className="truncate overflow-hidden" />
              <button
                onClick={closeArtifact}
                className="cursor-pointer"
              >
                <XIcon className="size-5" />
              </button>
            </div>
            <ArtifactContent className="relative flex-grow" />
          </div>
        </div>
      </div>
    </div>
  );
}
