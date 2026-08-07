type StructuredApprovalToolResponse = {
  ok?: boolean;
  error?: { code?: string; message?: string } | null;
  presentation?: {
    blockType?: string;
    cardType?: string;
  } | null;
};

export type ApprovalToolMessage = {
  name?: string;
  status?: "success" | "error";
  content: unknown;
};

const OFFICIAL_HITL_REJECTION =
  /^User rejected the tool call for `confirm_[^`]+` with id .+?\. The tool was not executed\b/;

function parseStructuredApprovalResponse(
  content: unknown,
): StructuredApprovalToolResponse | undefined {
  const value =
    typeof content === "string"
      ? (() => {
          try {
            return JSON.parse(content) as unknown;
          } catch {
            return undefined;
          }
        })()
      : content;

  if (!value || typeof value !== "object") return undefined;
  const response = value as StructuredApprovalToolResponse;
  return typeof response.ok === "boolean" ||
    (response.error && typeof response.error === "object")
    ? response
    : undefined;
}

/**
 * Approval rejection and expiry are normal HITL control-flow outcomes. They
 * must not be projected as generic ToolResult failures after the assistant has
 * already produced the durable user-facing outcome.
 */
export function isApprovalControlFlow(message: ApprovalToolMessage): boolean {
  const response = parseStructuredApprovalResponse(message.content);
  if (
    response?.error?.code === "APPROVAL_REJECTED" ||
    response?.error?.code === "APPROVAL_EXPIRED"
  ) {
    return true;
  }

  // The LangGraph server may persist a structured rejected ToolMessage with a
  // successful transport status. The approval error code is the durable
  // discriminator; status alone is not.
  if (message.status !== "error") return false;

  return (
    typeof message.content === "string" &&
    OFFICIAL_HITL_REJECTION.test(message.content.trim())
  );
}

/**
 * Approval draft payloads are rendered by the authoritative interrupt card.
 * Their ToolMessage is transport data and must not become a second generic
 * result card in the transcript.
 */
export function isApprovalCardProjection(message: ApprovalToolMessage): boolean {
  const response = parseStructuredApprovalResponse(message.content);
  return (
    response?.ok === true &&
    response.presentation?.blockType === "card" &&
    response.presentation.cardType === "party_file_approval"
  );
}
