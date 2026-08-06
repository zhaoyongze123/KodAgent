import React, {
  createContext,
  useContext,
  ReactNode,
  useState,
  useEffect,
  useMemo,
} from "react";
import {
  useStream,
  type UseStreamOptions,
} from "@langchain/langgraph-sdk/react";
import { type Message } from "@langchain/langgraph-sdk";
import {
  uiMessageReducer,
  isUIMessage,
  isRemoveUIMessage,
  type UIMessage,
  type RemoveUIMessage,
} from "@langchain/langgraph-sdk/react-ui";
import { useQueryState } from "nuqs";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { LangGraphLogoSVG } from "@/components/icons/langgraph";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ArrowRight } from "lucide-react";
import { PasswordInput } from "@/components/ui/password-input";
import { getApiKey } from "@/lib/api-key";
import { useThreads } from "./Thread";
import { toast } from "sonner";
import { AGENT_SUBAGENT_STREAM_OPTIONS } from "@/lib/agent-stream-options";
import { clearLiveRunId, storeLiveRunId } from "@/lib/run-stream-attachment";
import { useRunStreamCoordinator } from "@/lib/use-run-stream-coordinator";
import {
  adaptAgentCustomEvent,
  type AgentCustomEvent,
} from "@/lib/agent-event-adapter";

export type StateType = { messages: Message[]; ui?: UIMessage[] };

const useTypedStream = useStream<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
      context?: Record<string, unknown>;
    };
    CustomEventType: UIMessage | RemoveUIMessage | AgentCustomEvent;
  }
>;

// The backend streams DeepAgent-style `task` subgraphs, while this frontend
// intentionally keeps a raw graph state type. These options are supported at
// runtime by the SDK even though the generated graph type cannot infer them.
type StreamOptions = UseStreamOptions<
  StateType,
  {
    UpdateType: {
      messages?: Message[] | Message | string;
      ui?: (UIMessage | RemoveUIMessage)[] | UIMessage | RemoveUIMessage;
      context?: Record<string, unknown>;
    };
    CustomEventType: UIMessage | RemoveUIMessage | AgentCustomEvent;
  }
> & {
  fetchStateHistory?: boolean | { limit: number };
  reconnectOnMount?: boolean;
  subagentToolNames?: string[];
  filterSubagentMessages?: boolean;
};

type StreamContextType = ReturnType<typeof useTypedStream>;
type StreamContextValue = StreamContextType & {
  processEvents: AgentCustomEvent[];
  /** Current Run identity shared by transient and durable process entries. */
  currentRunId: string | null;
  setTraceId: (traceId: string | null) => void;
  recoveringRunId: string | null;
  /** Run whose transport failed; used to resume a still-running durable run. */
  streamErrorRunId: string | null;
};
const StreamContext = createContext<StreamContextValue | undefined>(undefined);

async function sleep(ms = 4000) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function checkGraphStatus(
  apiUrl: string,
  apiKey: string | null,
  authScheme?: string,
): Promise<boolean> {
  try {
    const headers = new Headers();
    if (apiKey) headers.set("X-Api-Key", apiKey);
    if (authScheme) headers.set("X-Auth-Scheme", authScheme);

    const res = await fetch(`${apiUrl}/info`, {
      headers,
    });

    return res.ok;
  } catch (e) {
    console.error(e);
    return false;
  }
}

const StreamSession = ({
  children,
  apiKey,
  apiUrl,
  assistantId,
  authScheme,
}: {
  children: ReactNode;
  apiKey: string | null;
  apiUrl: string;
  assistantId: string;
  authScheme?: string;
}) => {
  const [threadId, setThreadId] = useQueryState("threadId");
  const { getThreads, setThreads } = useThreads();
  const [processEvents, setProcessEvents] = useState<AgentCustomEvent[]>([]);
  const [currentRunId, setCurrentRunId] = useState<string | null>(null);
  const [streamErrorRunId, setStreamErrorRunId] = useState<string | null>(null);
  const processEventOrder = React.useRef(0);
  const traceIdRef = React.useRef<string | null>(null);
  const traceStartedAtRef = React.useRef<number | null>(null);
  const firstUpdateLoggedRef = React.useRef(false);
  const firstCustomLoggedRef = React.useRef(false);
  const activeRunIdRef = React.useRef<string | null>(null);
  const activeRunThreadIdRef = React.useRef<string | null>(null);
  const failedRunIdsRef = React.useRef(new Set<string>());
  const metricSentRef = React.useRef(new Set<string>());
  const recordMetric = React.useCallback(
    (metric: string, value: number) => {
      const runId = activeRunIdRef.current;
      if (
        !runId ||
        !threadId ||
        metricSentRef.current.has(`${runId}:${metric}`)
      )
        return;
      metricSentRef.current.add(`${runId}:${metric}`);
      void fetch(`/api/agent-runs/${encodeURIComponent(runId)}/metrics`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threadId, metric, value }),
        keepalive: true,
      }).catch(() => undefined);
    },
    [threadId],
  );
  useEffect(() => {
    setProcessEvents([]);
    setCurrentRunId(null);
    setStreamErrorRunId(null);
  }, [threadId]);
  const streamOptions = {
    apiUrl,
    apiKey: apiKey ?? undefined,
    assistantId,
    ...(authScheme && {
      defaultHeaders: {
        "X-Auth-Scheme": authScheme,
      },
    }),
    threadId: threadId ?? null,
    // 只恢复当前 Thread 的最新 PostgreSQL Checkpoint，避免请求整段历史
    // 和子 Agent 的内部 checkpoint；过程正文仍由 Java/PostgreSQL 事件恢复。
    // SDK 中 false 的语义是 getState（不是禁用恢复）。
    fetchStateHistory: false,
    // Recovery is owned by Thread's single attachment coordinator. Leaving
    // the SDK reconnectOnMount enabled would create a second join on refresh
    // while the business recovery effect is also joining the same run.
    reconnectOnMount: false,
    // Never put the task subgraph's full state/message history into the main
    // conversation. User-visible sub-agent summaries and tool audit rows come
    // from Python's durable custom events instead.
    ...AGENT_SUBAGENT_STREAM_OPTIONS,
    callerOptions: useMemo(
      () => ({
        fetch: async (input: RequestInfo | URL, init?: RequestInit) => {
          const traceId = traceIdRef.current;
          const dispatchStartedAt = performance.now();
          const headers = new Headers(init?.headers);
          if (traceId) headers.set("X-KodAgent-Trace-Id", traceId);
          if (traceId) {
            console.info(
              JSON.stringify({
                source: "kodagent.ui",
                traceId,
                phase: "request.dispatch",
                elapsedMs: traceStartedAtRef.current
                  ? Math.round(dispatchStartedAt - traceStartedAtRef.current)
                  : 0,
              }),
            );
          }
          const response = await globalThis.fetch(input, {
            ...init,
            headers,
          });
          if (traceId) {
            console.info(
              JSON.stringify({
                source: "kodagent.ui",
                traceId,
                phase: "request.response-headers",
                elapsedMs: traceStartedAtRef.current
                  ? Math.round(performance.now() - traceStartedAtRef.current)
                  : 0,
                requestMs: Math.round(performance.now() - dispatchStartedAt),
                status: response.status,
              }),
            );
          }
          return response;
        },
      }),
      [],
    ),
    onCreated: (run) => {
      activeRunIdRef.current = run.run_id;
      setCurrentRunId(run.run_id);
      activeRunThreadIdRef.current = run.thread_id ?? threadId;
      failedRunIdsRef.current.delete(run.run_id);
      if (typeof window !== "undefined") {
        storeLiveRunId(
          window.sessionStorage,
          activeRunThreadIdRef.current,
          run.run_id,
        );
      }
      setStreamErrorRunId(null);
      metricSentRef.current = new Set();
      setProcessEvents([]);
      processEventOrder.current = 0;
      firstUpdateLoggedRef.current = false;
      firstCustomLoggedRef.current = false;
      const traceId = traceIdRef.current;
      if (traceId) {
        console.info(
          JSON.stringify({
            source: "kodagent.ui",
            traceId,
            phase: "run.created",
            runId: run.run_id,
            threadId: run.thread_id,
            elapsedMs: traceStartedAtRef.current
              ? Math.round(performance.now() - traceStartedAtRef.current)
              : 0,
          }),
        );
      }
    },
    onUpdateEvent: () => {
      const traceId = traceIdRef.current;
      if (!traceId || firstUpdateLoggedRef.current) return;
      firstUpdateLoggedRef.current = true;
      recordMetric(
        "first_update_ms",
        traceStartedAtRef.current
          ? Math.round(performance.now() - traceStartedAtRef.current)
          : 0,
      );
      console.info(
        JSON.stringify({
          source: "kodagent.ui",
          traceId,
          phase: "stream.first-update",
          elapsedMs: traceStartedAtRef.current
            ? Math.round(performance.now() - traceStartedAtRef.current)
            : 0,
        }),
      );
    },
    onFinish: (_state, run) => {
      const runId = run?.run_id ?? activeRunIdRef.current;
      const traceId = traceIdRef.current;
      if (traceId) {
        const elapsedMs = traceStartedAtRef.current
          ? Math.round(performance.now() - traceStartedAtRef.current)
          : 0;
        recordMetric("run_duration_ms", elapsedMs);
        console.info(
          JSON.stringify({
            source: "kodagent.ui",
            traceId,
            // This callback only describes the browser transport. The durable
            // run terminal state is emitted by LangGraph/backend, never by
            // the browser.
            phase: "stream.transport-finished",
            runId: run?.run_id,
            elapsedMs,
          }),
        );
      }
      traceIdRef.current = null;
      traceStartedAtRef.current = null;
      // Transport completion is not durable Run completion. The
      // RunStreamCoordinator owns the status reconciliation and keeps this
      // marker/identity when the backend still says pending or running.
      if (runId) setStreamErrorRunId(runId);
    },
    onError: (error, run) => {
      const runId = run?.run_id ?? activeRunIdRef.current;
      if (runId) failedRunIdsRef.current.add(runId);
      setStreamErrorRunId(runId);
      const traceId = traceIdRef.current;
      if (traceId) {
        console.info(
          JSON.stringify({
            source: "kodagent.ui",
            traceId,
            // A stream error is not proof that the durable run failed: the
            // run may still be RUNNING and can be rejoined below.
            phase: "stream.transport-error",
            runId: run?.run_id,
            elapsedMs: traceStartedAtRef.current
              ? Math.round(performance.now() - traceStartedAtRef.current)
              : 0,
            error: error instanceof Error ? error.message : String(error),
          }),
        );
      }
      // The SDK owns the stream lifecycle. Do not rethrow here: Thread renders
      // stream.error as a user-facing ErrorCard, while diagnostics stay in the
      // trace log instead of reaching the Next.js development overlay.
    },
    onStop: () => {
      const runId = activeRunIdRef.current;
      if (!runId || !threadId) return;
      void fetch(`/api/agent-runs/${encodeURIComponent(runId)}/cancel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ threadId }),
        keepalive: true,
      }).catch(() => undefined);
      failedRunIdsRef.current.delete(runId);
      if (typeof window !== "undefined") {
        clearLiveRunId(window.sessionStorage, threadId, runId);
      }
      activeRunIdRef.current = null;
      activeRunThreadIdRef.current = null;
      setCurrentRunId(null);
    },
    onCustomEvent: (event, options) => {
      const traceId = traceIdRef.current;
      if (traceId && !firstCustomLoggedRef.current) {
        firstCustomLoggedRef.current = true;
        recordMetric(
          "first_custom_event_ms",
          traceStartedAtRef.current
            ? Math.round(performance.now() - traceStartedAtRef.current)
            : 0,
        );
        console.info(
          JSON.stringify({
            source: "kodagent.ui",
            traceId,
            phase: "stream.first-custom-event",
            eventType:
              typeof event === "object" && event !== null && "type" in event
                ? (event as { type?: string }).type
                : typeof event,
            elapsedMs: traceStartedAtRef.current
              ? Math.round(performance.now() - traceStartedAtRef.current)
              : 0,
          }),
        );
      }
      if (isUIMessage(event) || isRemoveUIMessage(event)) {
        options.mutate((prev) => {
          const ui = uiMessageReducer(prev.ui ?? [], event);
          return { ...prev, ui };
        });
        return;
      }

      const agentEvent = adaptAgentCustomEvent(event, {
        namespace: options.namespace,
        receivedOrder: processEventOrder.current++,
      });
      if (!agentEvent) return;
      const eventId = agentEvent.event?.eventId;
      setProcessEvents((current) => {
        const entryId = agentEvent.event?.entryId;
        if (entryId) {
          const incomingRevision = agentEvent.event?.revision ?? 1;
          const existingIndex = current.findIndex(
            (item) => item.event?.entryId === entryId,
          );
          if (existingIndex >= 0) {
            const existing = current[existingIndex];
            const existingRevision = existing.event?.revision ?? 1;
            if (incomingRevision <= existingRevision) return current;
            return current.map((item, index) =>
              index === existingIndex ? agentEvent : item,
            );
          }
        }
        if (
          eventId &&
          current.some((item) => item.event?.eventId === eventId)
        ) {
          return current;
        }
        return [...current, agentEvent];
      });
    },
    onThreadId: (id) => {
      setThreadId(id);
      setStreamErrorRunId(null);
      // Refetch threads list when thread ID changes.
      // Wait for some seconds before fetching so we're able to get the new thread that was created.
      sleep().then(() => getThreads().then(setThreads).catch(console.error));
    },
  } satisfies StreamOptions;
  const streamValue = useTypedStream(streamOptions);

  const clearStreamRecoveryRun = React.useCallback((runId: string) => {
    failedRunIdsRef.current.delete(runId);
    if (activeRunIdRef.current === runId) {
      activeRunIdRef.current = null;
      activeRunThreadIdRef.current = null;
      setCurrentRunId(null);
    }
    setStreamErrorRunId((current) => (current === runId ? null : current));
  }, []);
  const runCoordinator = useRunStreamCoordinator({
    threadId,
    stream: streamValue,
    isLoading: streamValue.isLoading,
    recoveryRunId: streamErrorRunId,
    clearRecoveryRun: clearStreamRecoveryRun,
  });

  useEffect(() => {
    checkGraphStatus(apiUrl, apiKey, authScheme).then((ok) => {
      if (!ok) {
        toast.error("Failed to connect to LangGraph server", {
          description: () => (
            <p>
              Please ensure your graph is running at <code>{apiUrl}</code> and
              your API key is correctly set (if connecting to a deployed graph).
            </p>
          ),
          duration: 10000,
          richColors: true,
          closeButton: true,
        });
      }
    });
  }, [apiKey, apiUrl, authScheme]);

  const contextValue = useMemo(() => {
    // useStream exposes several getter-backed properties. Object spreading
    // them eagerly accesses toolProgress and registers the unsupported
    // `tools` stream mode against the local LangGraph Server.
    const value = Object.create(streamValue) as StreamContextValue;
    value.processEvents = processEvents;
    value.currentRunId = currentRunId;
    value.streamErrorRunId = streamErrorRunId;
    value.recoveringRunId = runCoordinator.recoveringRunId;
    value.setTraceId = (traceId: string | null) => {
      traceIdRef.current = traceId;
      traceStartedAtRef.current = traceId ? performance.now() : null;
    };
    return value;
  }, [
    streamValue,
    processEvents,
    currentRunId,
    streamErrorRunId,
    runCoordinator.recoveringRunId,
  ]);

  return (
    <StreamContext.Provider value={contextValue}>
      {children}
    </StreamContext.Provider>
  );
};

// Default values for the form
const DEFAULT_API_URL = "http://localhost:2024";
const DEFAULT_ASSISTANT_ID = "agent";
const AGENT_BUILDER_AUTH_SCHEME = "langsmith-api-key";

export const StreamProvider: React.FC<{ children: ReactNode }> = ({
  children,
}) => {
  // Get environment variables
  const envApiUrl: string | undefined = process.env.NEXT_PUBLIC_API_URL;
  const envAssistantId: string | undefined =
    process.env.NEXT_PUBLIC_ASSISTANT_ID;
  const envAuthScheme: string | undefined = process.env.NEXT_PUBLIC_AUTH_SCHEME;

  // Use URL params with env var fallbacks
  const [apiUrl, setApiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });
  const [assistantId, setAssistantId] = useQueryState("assistantId", {
    defaultValue: envAssistantId || "",
  });
  const [authScheme, setAuthScheme] = useQueryState("authScheme", {
    defaultValue: envAuthScheme || "",
  });
  const [isAgentBuilder, setIsAgentBuilder] = useState(
    () =>
      (authScheme || envAuthScheme || "").toLowerCase() ===
      AGENT_BUILDER_AUTH_SCHEME,
  );

  // For API key, use localStorage with env var fallback
  const [apiKey, _setApiKey] = useState(() => {
    const storedKey = getApiKey();
    return storedKey || "";
  });

  const setApiKey = (key: string) => {
    window.localStorage.setItem("lg:chat:apiKey", key);
    _setApiKey(key);
  };

  // Determine final values to use, prioritizing URL params then env vars
  const finalApiUrl = apiUrl || envApiUrl;
  const finalAssistantId = assistantId || envAssistantId;
  const finalAuthScheme = authScheme || envAuthScheme || "";

  // Show the form if we: don't have an API URL, or don't have an assistant ID
  if (!finalApiUrl || !finalAssistantId) {
    return (
      <div className="flex min-h-screen w-full items-center justify-center p-4">
        <div className="animate-in fade-in-0 zoom-in-95 bg-background flex max-w-3xl flex-col rounded-lg border shadow-lg">
          <div className="mt-14 flex flex-col gap-2 border-b p-6">
            <div className="flex flex-col items-start gap-2">
              <LangGraphLogoSVG className="h-7" />
              <h1 className="text-xl font-semibold tracking-tight">
                Agent Chat
              </h1>
            </div>
            <p className="text-muted-foreground">
              Welcome to Agent Chat! Before you get started, you need to enter
              the URL of the deployment and the assistant / graph ID.
            </p>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();

              const form = e.target as HTMLFormElement;
              const formData = new FormData(form);
              const apiUrl = formData.get("apiUrl") as string;
              const assistantId = formData.get("assistantId") as string;
              const apiKey = formData.get("apiKey") as string;

              setApiUrl(apiUrl);
              setApiKey(apiKey);
              setAssistantId(assistantId);
              setAuthScheme(isAgentBuilder ? AGENT_BUILDER_AUTH_SCHEME : "");

              form.reset();
            }}
            className="bg-muted/50 flex flex-col gap-6 p-6"
          >
            <div className="flex flex-col gap-2">
              <Label htmlFor="apiUrl">
                Deployment URL<span className="text-rose-500">*</span>
              </Label>
              <p className="text-muted-foreground text-sm">
                This is the URL of your LangGraph deployment. Can be a local, or
                production deployment.
              </p>
              <Input
                id="apiUrl"
                name="apiUrl"
                className="bg-background"
                defaultValue={apiUrl || DEFAULT_API_URL}
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="assistantId">
                Assistant / Graph ID<span className="text-rose-500">*</span>
              </Label>
              <p className="text-muted-foreground text-sm">
                This is the ID of the graph (can be the graph name), or
                assistant to fetch threads from, and invoke when actions are
                taken.
              </p>
              <Input
                id="assistantId"
                name="assistantId"
                className="bg-background"
                defaultValue={assistantId || DEFAULT_ASSISTANT_ID}
                required
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="apiKey">LangSmith API Key</Label>
              <p className="text-muted-foreground text-sm">
                This is <strong>NOT</strong> required if using a local LangGraph
                server. This value is stored in your browser's local storage and
                is only used to authenticate requests sent to your LangGraph
                server.
              </p>
              <PasswordInput
                id="apiKey"
                name="apiKey"
                defaultValue={apiKey ?? ""}
                className="bg-background"
                placeholder="lsv2_pt_..."
              />
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between gap-4">
                <div className="flex flex-col gap-1">
                  <Label htmlFor="agentBuilderEnabled">
                    Built with Agent Builder
                  </Label>
                  <p className="text-muted-foreground text-sm">
                    Enable this for Agent Builder deployments.
                  </p>
                </div>
                <Switch
                  id="agentBuilderEnabled"
                  checked={isAgentBuilder}
                  onCheckedChange={setIsAgentBuilder}
                />
              </div>
            </div>

            <div className="mt-2 flex justify-end">
              <Button
                type="submit"
                size="lg"
              >
                Continue
                <ArrowRight className="size-5" />
              </Button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <StreamSession
      apiKey={apiKey}
      apiUrl={finalApiUrl}
      assistantId={finalAssistantId}
      authScheme={finalAuthScheme || undefined}
    >
      {children}
    </StreamSession>
  );
};

// Create a custom hook to use the context
export const useStreamContext = (): StreamContextValue => {
  const context = useContext(StreamContext);
  if (context === undefined) {
    throw new Error("useStreamContext must be used within a StreamProvider");
  }
  return context;
};

export default StreamContext;
