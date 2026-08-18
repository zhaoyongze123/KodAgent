import type { Message } from "@langchain/langgraph-sdk";
import {
  isCardAssistantPresentation,
  isFinalAssistantPresentation,
  isInternalAssistantPresentation,
} from "../../../lib/assistant-message-presentation.ts";
import { getContentString } from "../utils.ts";
import { normalizeProcessText } from "../process-events.ts";

/**
 * These tools communicate process state through the structured process-event
 * timeline. Their native ToolMessage is an implementation detail and must not
 * create a second ordinary chat row.
 */
const PROCESS_ONLY_TOOL_NAMES = new Set([
  "report_progress",
  "task",
  "route_conversation",
  "create_document_artifact",
]);

/**
 * These tools are represented by the durable process-event timeline. Their
 * native AI tool-call and ToolMessage transport records are implementation
 * details, not additional user-facing tool cards.
 */
export function isProcessOnlyToolName(name: unknown): boolean {
  return PROCESS_ONLY_TOOL_NAMES.has(String(name ?? ""));
}

function hasToolCalls(message: Message): boolean {
  return (
    "tool_calls" in message &&
    Array.isArray(message.tool_calls) &&
    message.tool_calls.length > 0
  );
}

function hasAnthropicToolUse(message: Message): boolean {
  const content = message.content as unknown;
  if (!Array.isArray(content)) return false;
  return content.some(
    (block) =>
      !!block &&
      typeof block === "object" &&
      (block as { type?: unknown }).type === "tool_use" &&
      typeof (block as { id?: unknown }).id === "string" &&
      (block as { id: string }).id.length > 0,
  );
}

/** Tool-call AIMessage is an execution protocol carrier, never a chat row. */
export function isInternalAssistantMessage(message: Message): boolean {
  return (
    message.type === "ai" &&
    (isInternalAssistantPresentation(message) ||
      hasToolCalls(message) ||
      hasAnthropicToolUse(message))
  );
}

/** Only a v2 final message may complete the current live user turn. */
export function isCommittedFinalAssistantMessage(message: Message): boolean {
  return (
    message.type === "ai" &&
    isFinalAssistantPresentation(message) &&
    !isInternalAssistantMessage(message) &&
    normalizeProcessText(getContentString(message.content)).length > 0
  );
}

export function isProcessOnlyToolMessage(message: Message): boolean {
  return message.type === "tool" && isProcessOnlyToolName(message.name);
}

/**
 * Decide whether AssistantMessage may mount its outer layout node.
 *
 * This predicate intentionally runs before rendering ToolResult. Returning
 * null from ToolResult alone is too late: AssistantMessage's outer flex/grid
 * wrappers would already contribute gap and height to the conversation.
 */
export function isRenderableAssistantMessage(
  message: Message | undefined,
): boolean {
  if (!message) return false;

  if (message.type === "tool") {
    if (isProcessOnlyToolMessage(message)) return false;
    return normalizeProcessText(getContentString(message.content)).length > 0;
  }

  if (message.type === "ai") {
    if (isInternalAssistantMessage(message)) return false;
    if (isCardAssistantPresentation(message)) return true;
    if (isCommittedFinalAssistantMessage(message)) return true;

    // 普通正文必须显式标记为 v2 final。无标记的 AIMessage 可能是旧路由、
    // 中间模型回合或被覆盖前的控制输出，不能因“文本非空”重新泄漏到正文。
    // 历史卡片已在上方通过 v1/v2 card 单独兼容。
    return false;
  }

  // AssistantMessage is normally called for AI/Tool messages, but retaining
  // this branch keeps the predicate safe for future message variants.
  return normalizeProcessText(getContentString(message.content)).length > 0;
}
