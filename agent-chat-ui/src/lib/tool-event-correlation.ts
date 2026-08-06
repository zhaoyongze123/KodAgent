export type CorrelatableToolEvent = {
  toolCallId?: string;
  type?: string;
  data?: {
    toolName?: string;
    text?: unknown;
    errorCode?: unknown;
  };
};

const TERMINAL_TOOL_EVENTS = new Set(["tool.completed", "tool.failed"]);

/**
 * Correlate a ToolMessage with its own durable lifecycle event.
 *
 * Tool names are not unique across a thread, so an ID-less lookup is unsafe.
 * The caller must provide the ToolMessage call ID and the event must carry the
 * same ID and tool name. Reverse order selects the latest terminal event for
 * this exact invocation without consulting another turn.
 */
export function findLatestCorrelatedToolEvent(
  events: readonly (CorrelatableToolEvent | undefined)[],
  toolCallId: string | null | undefined,
  toolName: string | null | undefined,
): CorrelatableToolEvent | undefined {
  if (!toolCallId || !toolName) return undefined;

  return [...events]
    .reverse()
    .find(
      (event) =>
        event?.toolCallId === toolCallId &&
        event.data?.toolName === toolName &&
        event.type != null &&
        TERMINAL_TOOL_EVENTS.has(event.type),
    );
}
