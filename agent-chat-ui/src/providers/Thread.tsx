import { validate } from "uuid";
import { getApiKey } from "@/lib/api-key";
import { Thread } from "@langchain/langgraph-sdk";
import { useQueryState } from "nuqs";
import {
  createContext,
  useContext,
  ReactNode,
  useCallback,
  useState,
  Dispatch,
  SetStateAction,
} from "react";
import { createClient } from "./client";
import { withThreadHistoryTimeout } from "@/lib/thread-history";

interface ThreadContextType {
  getThreads: () => Promise<Thread[]>;
  deleteThread: (threadId: string) => Promise<void>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
  threadsError: string | null;
  reloadThreads: () => Promise<Thread[]>;
}

const ThreadContext = createContext<ThreadContextType | undefined>(undefined);

function getThreadSearchMetadata(
  assistantId: string,
): { graph_id: string } | { assistant_id: string } {
  if (validate(assistantId)) {
    return { assistant_id: assistantId };
  } else {
    return { graph_id: assistantId };
  }
}

export function ThreadProvider({ children }: { children: ReactNode }) {
  const envApiUrl: string | undefined = process.env.NEXT_PUBLIC_API_URL;
  const envAssistantId: string | undefined =
    process.env.NEXT_PUBLIC_ASSISTANT_ID;
  const envAuthScheme: string | undefined = process.env.NEXT_PUBLIC_AUTH_SCHEME;

  const [apiUrl] = useQueryState("apiUrl", {
    defaultValue: envApiUrl || "",
  });
  const [assistantId] = useQueryState("assistantId");
  const [authScheme] = useQueryState("authScheme", {
    defaultValue: envAuthScheme || "",
  });
  const [threads, setThreads] = useState<Thread[]>([]);
  const [threadsLoading, setThreadsLoading] = useState(false);
  const [threadsError, setThreadsError] = useState<string | null>(null);

  const getThreads = useCallback(async (): Promise<Thread[]> => {
    const resolvedAssistantId = assistantId || envAssistantId;
    if (!apiUrl || !resolvedAssistantId) return [];
    const client = createClient(
      apiUrl,
      getApiKey() ?? undefined,
      authScheme || undefined,
    );

    const threads = await client.threads.search({
      metadata: {
        ...getThreadSearchMetadata(resolvedAssistantId),
      },
      // The history drawer is a summary list. Full state is loaded only after
      // the user selects a thread.
      limit: 20,
      sortBy: "updated_at",
      sortOrder: "desc",
      // `metadata` contains server-side ownership/run context. The history
      // list only needs identifiers and timestamps; requesting metadata would
      // unnecessarily send persisted internal context to the browser.
      select: ["thread_id", "created_at", "updated_at"],
      extract: {
        firstMessage: "values.messages[0].content",
      },
    });

    return threads;
  }, [apiUrl, assistantId, authScheme, envAssistantId]);

  const deleteThread = useCallback(
    async (threadId: string): Promise<void> => {
      const resolvedAssistantId = assistantId || envAssistantId;
      if (!apiUrl || !resolvedAssistantId) {
        throw new Error("Agent 服务配置不完整，无法删除对话");
      }
      const client = createClient(
        apiUrl,
        getApiKey() ?? undefined,
        authScheme || undefined,
      );
      await client.threads.delete(threadId);
    },
    [apiUrl, assistantId, authScheme, envAssistantId],
  );

  const reloadThreads = useCallback(async (): Promise<Thread[]> => {
    setThreadsLoading(true);
    setThreadsError(null);
    try {
      const result = await withThreadHistoryTimeout(getThreads());
      setThreads(result);
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : "历史记录加载失败，请稍后重试。";
      setThreadsError(message);
      throw error;
    } finally {
      setThreadsLoading(false);
    }
  }, [getThreads]);

  const value = {
    getThreads,
    deleteThread,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
    threadsError,
    reloadThreads,
  };

  return (
    <ThreadContext.Provider value={value}>{children}</ThreadContext.Provider>
  );
}

export function useThreads() {
  const context = useContext(ThreadContext);
  if (context === undefined) {
    throw new Error("useThreads must be used within a ThreadProvider");
  }
  return context;
}
