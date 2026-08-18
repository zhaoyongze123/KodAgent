import { MarkdownText } from "../markdown-text";
import { CardRenderer } from "../cards/CardRenderer";
import { ErrorCard } from "../cards/ErrorCard";
import { ResultRendererRegistry } from "../results/ResultRendererRegistry";
import type { AgentBlock } from "@/types/agent-block";

/**
 * The product rendering boundary for assistant content.
 *
 * LangGraph messages/events are transport data. They are normalized into an
 * AgentBlock before reaching this component, so adding a new business card or
 * error state does not require another branch in AssistantMessage.
 */
export function AgentBlockRenderer({
  block,
  onErrorAction,
}: {
  block: AgentBlock;
  onErrorAction?: (action: NonNullable<
    Extract<AgentBlock, { kind: "error" }>["error"]["action"]
  >) => void;
}) {
  switch (block.kind) {
    case "narration":
      return <MarkdownText>{block.markdown}</MarkdownText>;
    case "card":
      return <CardRenderer card={block.card} />;
    case "result":
      return <ResultRendererRegistry envelope={block.result} />;
    case "error":
      return <ErrorCard error={block.error} onAction={onErrorAction} />;
    case "process":
      return null;
    default:
      return null;
  }
}
