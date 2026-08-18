import { v4 as uuidv4 } from "uuid";
import { Message, ToolMessage } from "@langchain/langgraph-sdk";

export const DO_NOT_RENDER_ID_PREFIX = "do-not-render-";

export function ensureToolCallsHaveResponses(messages: Message[]): Message[] {
  const newMessages: ToolMessage[] = [];

  // Collect every tool_call_id that already has a ToolMessage response in the
  // message stream. This prevents injecting duplicate placeholder responses
  // for tool calls whose real response exists but is not immediately adjacent
  // to the AI message (e.g. due to streaming event ordering or values
  // overwrites).
  const answeredToolCallIds = new Set<string>();
  for (const message of messages) {
    if (message.type === "tool" && message.tool_call_id) {
      answeredToolCallIds.add(message.tool_call_id);
    }
  }

  messages.forEach((message, index) => {
    if (message.type !== "ai" || message.tool_calls?.length === 0) {
      // If it's not an AI message, or it doesn't have tool calls, we can ignore.
      return;
    }
    // If it has tool calls, ensure the message which follows this is a tool message
    const followingMessage = messages[index + 1];
    if (followingMessage && followingMessage.type === "tool") {
      // Following message is a tool message, so we can ignore.
      return;
    }

    // The following message is not a tool message. Only inject placeholder
    // responses for tool calls that don't already have a response elsewhere
    // in the stream. Injecting a duplicate response for an already-answered
    // tool_call_id causes provider validation errors ("tool messages must be
    // preceded by a tool call message").
    const unansweredCalls = (message.tool_calls ?? []).filter(
      (tc) => tc.id && !answeredToolCallIds.has(tc.id),
    );

    if (unansweredCalls.length === 0) return;

    newMessages.push(
      ...unansweredCalls.map((tc) => ({
        type: "tool" as const,
        tool_call_id: tc.id ?? "",
        id: `${DO_NOT_RENDER_ID_PREFIX}${uuidv4()}`,
        name: tc.name,
        content: "Successfully handled tool call.",
      })),
    );
  });

  return newMessages;
}
