import {
  isApprovalControlFlow,
  type ApprovalToolMessage,
} from "./approval-tool-result.ts";

export type MeetingToolMessage = ApprovalToolMessage;

/**
 * Official DeepAgents HITL reject is an error-status ToolMessage by protocol,
 * but it means the approval control flow ended, not that the tool failed.
 * Every discriminator is required so ordinary tool errors stay errors.
 */
export function isMeetingApprovalCancellation(
  message: MeetingToolMessage,
): boolean {
  return message.name === "confirm_meeting_booking" && isApprovalControlFlow(message);
}
