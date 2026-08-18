export const RESULT_KINDS = [
  "ranked_list",
  "record_list",
  "analysis",
  "workflow_draft",
  "comparison",
  "approval_check",
  "clarification",
  "error",
  "rich_text",
] as const;

export type ResultKind = (typeof RESULT_KINDS)[number];

export type ResultDisplayPolicy = {
  defaultExpanded?: boolean;
  showRawDetails?: boolean;
  allowLoadMore?: boolean;
};

/** Presentation metadata is UI policy, not business data. */
export type ResultPresentation = {
  resultKind: ResultKind | (string & {});
  sourceResultId?: string;
  resultGroupId?: string;
  title?: string;
  summary?: string | { headline?: string; [key: string]: unknown };
  headline?: string;
  displayPolicy?: ResultDisplayPolicy;
  primary?: boolean;
};

export type ResultEnvelope = {
  presentation: ResultPresentation;
  data: unknown;
  sourceResultId?: string;
  resultGroupId?: string;
  messageId?: string;
};

export function isResultKind(value: unknown): value is ResultKind {
  return typeof value === "string" && RESULT_KINDS.includes(value as ResultKind);
}

export function resultSourceId(result: ResultEnvelope): string | undefined {
  const value = result.sourceResultId ?? result.presentation.sourceResultId;
  return typeof value === "string" && value.trim() ? value.trim() : undefined;
}
