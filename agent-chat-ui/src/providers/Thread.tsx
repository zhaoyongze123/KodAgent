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
import {
  mergeThreadHistoryPages,
  withThreadHistoryTimeout,
} from "@/lib/thread-history";

/** 历史侧栏每次只读取一页标题摘要，不读取完整对话状态。 */
const THREAD_HISTORY_PAGE_SIZE = 30;

interface ThreadContextType {
  getThreads: () => Promise<Thread[]>;
  deleteThread: (threadId: string) => Promise<void>;
  threads: Thread[];
  setThreads: Dispatch<SetStateAction<Thread[]>>;
  threadsLoading: boolean;
  setThreadsLoading: Dispatch<SetStateAction<boolean>>;
  threadsError: string | null;
  reloadThreads: () => Promise<Thread[]>;
  /** 是否仍有未加载的历史标题页。 */
  threadsHasMore: boolean;
  /** 加载较早标题时的独立状态，不遮住已显示的历史记录。 */
  threadsLoadingMore: boolean;
  threadsLoadMoreError: string | null;
  /** 继续读取下一页标题摘要；完整消息仍仅在用户点进 Thread 后加载。 */
  loadMoreThreads: () => Promise<Thread[]>;
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
  const [threadsHasMore, setThreadsHasMore] = useState(false);
  const [threadsLoadingMore, setThreadsLoadingMore] = useState(false);
  const [threadsLoadMoreError, setThreadsLoadMoreError] = useState<
    string | null
  >(null);

  /** 只查询历史侧栏需要的 Thread 标识、时间和首条消息标题。 */
  const searchThreadTitles = useCallback(
    async (offset: number): Promise<Thread[]> => {
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
        limit: THREAD_HISTORY_PAGE_SIZE,
        offset,
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
    },
    [apiUrl, assistantId, authScheme, envAssistantId],
  );

  /** 兼容现有调用方：默认只读取最新的一页标题。 */
  const getThreads = useCallback(
    () => searchThreadTitles(0),
    [searchThreadTitles],
  );

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
      setThreadsHasMore(result.length === THREAD_HISTORY_PAGE_SIZE);
      setThreadsLoadMoreError(null);
      return result;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "历史记录加载失败，请稍后重试。";
      setThreadsError(message);
      throw error;
    } finally {
      setThreadsLoading(false);
    }
  }, [getThreads]);

  /**
   * 追加读取更早的标题页。offset 只以当前已展示数量计算；服务端出现页面重叠时由
   * mergeThreadHistoryPages 按 thread_id 去重，确保列表不会重复。
   */
  const loadMoreThreads = useCallback(async (): Promise<Thread[]> => {
    if (!threadsHasMore || threadsLoadingMore) return threads;
    setThreadsLoadingMore(true);
    setThreadsLoadMoreError(null);
    try {
      const result = await withThreadHistoryTimeout(
        searchThreadTitles(threads.length),
      );
      const merged = mergeThreadHistoryPages(threads, result);
      setThreads(merged);
      // 只有完整页面才可能还有下一页；最后一页不足 page size 时终止加载。
      setThreadsHasMore(result.length === THREAD_HISTORY_PAGE_SIZE);
      return merged;
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "更多历史记录加载失败，请稍后重试。";
      setThreadsLoadMoreError(message);
      throw error;
    } finally {
      setThreadsLoadingMore(false);
    }
  }, [searchThreadTitles, threads, threadsHasMore, threadsLoadingMore]);

  const value = {
    getThreads,
    deleteThread,
    threads,
    setThreads,
    threadsLoading,
    setThreadsLoading,
    threadsError,
    reloadThreads,
    threadsHasMore,
    threadsLoadingMore,
    threadsLoadMoreError,
    loadMoreThreads,
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
