type StructuredToolError = {
  code?: string;
  message?: string;
};

type StructuredToolResponse = {
  error?: StructuredToolError | null;
};

export type MeetingToolMessage = {
  name?: string;
  status?: "success" | "error";
  content: unknown;
};

const OFFICIAL_HITL_REJECTION =
  /^User rejected the tool call for `confirm_meeting_booking` with id .+?\. The tool was not executed\b/;

function parseStructuredToolResponse(
  content: unknown,
): StructuredToolResponse | undefined {
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
  const response = value as StructuredToolResponse;
  return response.error && typeof response.error === "object"
    ? response
    : undefined;
}

/**
 * Official DeepAgents HITL reject is an error-status ToolMessage by protocol,
 * but it means the approval control flow ended, not that the tool failed.
 * Every discriminator is required so ordinary tool errors stay errors.
 */
export function isMeetingApprovalCancellation(
  message: MeetingToolMessage,
): boolean {
  if (
    message.name !== "confirm_meeting_booking" ||
    message.status !== "error"
  ) {
    return false;
  }

  const response = parseStructuredToolResponse(message.content);
  if (response?.error?.code === "APPROVAL_REJECTED") return true;

  return (
    typeof message.content === "string" &&
    OFFICIAL_HITL_REJECTION.test(message.content.trim())
  );
}
