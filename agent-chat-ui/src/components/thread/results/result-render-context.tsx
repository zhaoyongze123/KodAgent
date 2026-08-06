"use client";

import { createContext, useContext, useMemo, useRef, type ReactNode } from "react";

type ResultRenderContextValue = {
  primaryMessageBySourceId?: ReadonlyMap<string, string>;
  claimedMessageBySourceId: Map<string, string>;
  claimedMessageByResultGroup: Map<string, string>;
};

const ResultRenderContext = createContext<ResultRenderContextValue | null>(null);

export function ResultRenderScope({
  children,
  primaryMessageBySourceId,
}: {
  children: ReactNode;
  primaryMessageBySourceId?: ReadonlyMap<string, string>;
}) {
  const claimedMessageBySourceId = useRef(new Map<string, string>()).current;
  const claimedMessageByResultGroup = useRef(new Map<string, string>()).current;
  const value = useMemo(
    () => ({ primaryMessageBySourceId, claimedMessageBySourceId, claimedMessageByResultGroup }),
    [primaryMessageBySourceId, claimedMessageBySourceId, claimedMessageByResultGroup],
  );
  return <ResultRenderContext.Provider value={value}>{children}</ResultRenderContext.Provider>;
}

/** Return false for a duplicate result, while keeping a legacy no-provider path. */
export function useClaimResultSource(sourceId: string | undefined, messageId?: string): boolean {
  const context = useContext(ResultRenderContext);
  if (!sourceId) return true;
  if (!context) return true;
  const primaryMessageId = context.primaryMessageBySourceId?.get(sourceId);
  if (primaryMessageId && primaryMessageId !== messageId) return false;
  const claimedMessageId = context.claimedMessageBySourceId.get(sourceId);
  if (claimedMessageId && claimedMessageId !== messageId) return false;
  context.claimedMessageBySourceId.set(sourceId, messageId ?? "");
  return true;
}

export function useClaimResultGroup(groupId: string | undefined, messageId?: string): boolean {
  const context = useContext(ResultRenderContext);
  if (!groupId) return true;
  if (!context) return true;
  const claimedMessageId = context.claimedMessageByResultGroup.get(groupId);
  if (claimedMessageId && claimedMessageId !== messageId) return false;
  context.claimedMessageByResultGroup.set(groupId, messageId ?? "");
  return true;
}
