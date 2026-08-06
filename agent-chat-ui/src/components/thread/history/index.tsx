import { Button } from "@/components/ui/button";
import { useThreads } from "@/providers/Thread";
import { Thread } from "@langchain/langgraph-sdk";
import { useEffect, useRef, useState } from "react";

import { getContentString } from "../utils";
import type { Message } from "@langchain/langgraph-sdk";
import { useQueryState, parseAsBoolean } from "nuqs";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import {
  PanelRightOpen,
  PanelRightClose,
  Trash2,
  Settings,
} from "lucide-react";
import Link from "next/link";
import { useMediaQuery } from "@/hooks/useMediaQuery";

function ThreadList({
  threads,
  onThreadClick,
  onDeleteThread,
}: {
  threads: Thread[];
  onThreadClick?: (threadId: string) => void;
  onDeleteThread?: (threadId: string) => Promise<void>;
}) {
  const [threadId, setThreadId] = useQueryState("threadId");
  const [contextMenu, setContextMenu] = useState<{
    threadId: string;
    x: number;
    y: number;
  }>();
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    const closeMenu = () => setContextMenu(undefined);
    document.addEventListener("click", closeMenu);
    return () => document.removeEventListener("click", closeMenu);
  }, []);

  const deleteSelectedThread = async () => {
    if (!contextMenu || !onDeleteThread) return;
    const targetThreadId = contextMenu.threadId;
    setDeleting(true);
    try {
      await onDeleteThread(targetThreadId);
      if (targetThreadId === threadId) await setThreadId(null);
    } finally {
      setDeleting(false);
      setContextMenu(undefined);
    }
  };

  return (
    <>
      <div className="flex h-full w-full flex-col items-start justify-start gap-2 overflow-y-scroll [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
        {threads.map((t) => {
          const extractedMessage = t.extracted?.firstMessage;
          const metadataTitle =
            typeof t.metadata?.title === "string" ? t.metadata.title : "";
          const itemText =
            (extractedMessage != null
              ? getContentString(extractedMessage as Message["content"])
              : "") ||
            metadataTitle ||
            t.thread_id;
          return (
            <div
              key={t.thread_id}
              className="w-full px-1"
              onContextMenu={(event) => {
                event.preventDefault();
                setContextMenu({
                  threadId: t.thread_id,
                  x: event.clientX,
                  y: event.clientY,
                });
              }}
            >
              <Button
                variant="ghost"
                className="w-[280px] items-start justify-start text-left font-normal"
                onClick={(e) => {
                  e.preventDefault();
                  onThreadClick?.(t.thread_id);
                  if (t.thread_id === threadId) return;
                  setThreadId(t.thread_id);
                }}
              >
                <p className="truncate text-ellipsis">{itemText}</p>
              </Button>
            </div>
          );
        })}
      </div>
      {contextMenu && onDeleteThread && (
        <div
          className="bg-popover text-popover-foreground fixed z-50 min-w-36 rounded-md border p-1 shadow-md"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(event) => event.stopPropagation()}
          role="menu"
        >
          <Button
            className="w-full justify-start text-red-600 hover:bg-red-50 hover:text-red-700"
            variant="ghost"
            disabled={deleting}
            onClick={() => {
              if (window.confirm("确定删除这条聊天记录吗？删除后无法恢复。")) {
                void deleteSelectedThread();
              } else {
                setContextMenu(undefined);
              }
            }}
          >
            <Trash2 className="size-4" />
            删除聊天记录
          </Button>
        </div>
      )}
    </>
  );
}

function ThreadHistoryLoading() {
  return (
    <div className="flex h-full w-full flex-col items-start justify-start gap-2 overflow-y-scroll [&::-webkit-scrollbar]:w-1.5 [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-gray-300 [&::-webkit-scrollbar-track]:bg-transparent">
      {Array.from({ length: 30 }).map((_, i) => (
        <Skeleton
          key={`skeleton-${i}`}
          className="h-10 w-[280px]"
        />
      ))}
    </div>
  );
}

function ThreadHistoryFailure({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="mx-3 rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      <p className="font-medium">历史记录暂时无法加载</p>
      <p className="mt-1 text-xs leading-5 text-amber-800">{message}</p>
      <Button className="mt-3" size="sm" variant="outline" onClick={onRetry}>
        重试
      </Button>
    </div>
  );
}

export default function ThreadHistory() {
  const isLargeScreen = useMediaQuery("(min-width: 1024px)");
  const [chatHistoryOpen, setChatHistoryOpen] = useQueryState(
    "chatHistoryOpen",
    parseAsBoolean.withDefault(false),
  );

  const {
    getThreads,
    deleteThread,
    threads,
    setThreads,
    threadsLoading,
    threadsError,
    reloadThreads,
  } = useThreads();
  const initialLoadStarted = useRef(false);

  const handleDeleteThread = async (threadId: string) => {
    await deleteThread(threadId);
    const refreshedThreads = await getThreads();
    setThreads(refreshedThreads);
  };

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    reloadThreads().catch(console.error);
  }, [reloadThreads]);

  return (
    <>
      <div className="shadow-inner-right hidden h-dvh w-[300px] shrink-0 flex-col items-start justify-start gap-4 border-r-[1px] border-slate-300 lg:flex">
        <div className="flex w-full items-center justify-between px-4 pt-1.5">
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
          <h1 className="text-xl font-semibold tracking-tight">
            Thread History
          </h1>
        </div>
        <div className="min-h-0 w-full flex-1">
          {threadsLoading ? (
            <ThreadHistoryLoading />
          ) : threadsError ? (
            <ThreadHistoryFailure message={threadsError} onRetry={() => void reloadThreads().catch(console.error)} />
          ) : (
            <ThreadList
              threads={threads}
              onDeleteThread={handleDeleteThread}
            />
          )}
        </div>
        <div className="w-full border-t border-slate-200 p-3">
          <Button
            asChild
            variant="ghost"
            className="w-full justify-start gap-2 font-normal"
          >
            <Link
              href="/settings"
              aria-label="打开设置"
            >
              <Settings className="size-4" />
              设置
            </Link>
          </Button>
        </div>
      </div>
      <div className="lg:hidden">
        <Sheet
          open={!!chatHistoryOpen && !isLargeScreen}
          onOpenChange={(open) => {
            if (isLargeScreen) return;
            setChatHistoryOpen(open);
          }}
        >
          <SheetContent
            side="left"
            className="flex flex-col lg:hidden"
          >
            <SheetHeader>
              <SheetTitle>Thread History</SheetTitle>
            </SheetHeader>
            {threadsLoading ? (
              <ThreadHistoryLoading />
            ) : threadsError ? (
              <ThreadHistoryFailure message={threadsError} onRetry={() => void reloadThreads().catch(console.error)} />
            ) : (
              <ThreadList
                threads={threads}
                onThreadClick={() => setChatHistoryOpen((o) => !o)}
                onDeleteThread={handleDeleteThread}
              />
            )}
            <div className="mt-auto border-t border-slate-200 pt-3">
              <Button
                asChild
                variant="ghost"
                className="w-full justify-start gap-2 font-normal"
              >
                <Link
                  href="/settings"
                  aria-label="打开设置"
                  onClick={() => setChatHistoryOpen(false)}
                >
                  <Settings className="size-4" />
                  设置
                </Link>
              </Button>
            </div>
          </SheetContent>
        </Sheet>
      </div>
    </>
  );
}
