/**
 * A resume audit key is derived from the durable approval id rather than from
 * a render, click, or network attempt.  This keeps retries idempotent even if
 * the card is remounted after a refresh.
 */
export function getResumeIdempotencyKey(approvalId: string): string {
  const normalized = approvalId.trim();
  if (!normalized) {
    throw new Error("审批记录不存在，无法记录 Agent resume");
  }
  return `agent-resume:v1:${normalized}`;
}

export function shouldRecordResumeAudit(action: "approve" | "reject"): boolean {
  return action === "approve";
}

export type ApprovalDecision = "approve" | "reject";

export type ApprovalDecisionContext = {
  approvalId: string;
  draftId: string;
  operationId?: string;
  threadId?: string;
  runId?: string;
  messageId?: string;
  cardType?: string;
};

/**
 * Preserve the identity of the interrupted business action when LangGraph
 * Server materializes Command(resume) as a new Run. The new Run id is a
 * transport identity; approval validation must remain bound to the original
 * user message and original Run stored with the durable approval.
 */
export function buildApprovalResumeMetadata(
  context: ApprovalDecisionContext,
): Record<string, string> {
  const approvalId = context.approvalId.trim();
  const draftId = context.draftId.trim();
  const originRunId = context.runId?.trim();
  const messageId = context.messageId?.trim();
  if (!approvalId || !draftId || !originRunId || !messageId) {
    throw new Error("审批恢复上下文不完整，无法恢复 Agent");
  }
  return {
    approvalId,
    draftId,
    ...(context.operationId?.trim() ? { operationId: context.operationId.trim() } : {}),
    originRunId,
    messageId,
    ...(context.threadId?.trim() ? { threadId: context.threadId.trim() } : {}),
  };
}

/**
 * Build the single durable business-state request for an approval decision.
 *
 * Draft cancellation is deliberately not represented here: rejecting an
 * approval is the Java transaction boundary and atomically settles its draft.
 */
export function buildApprovalDecisionRequest(
  context: ApprovalDecisionContext,
  action: ApprovalDecision,
): { url: string; init: RequestInit } {
  const approvalId = context.approvalId.trim();
  const draftId = context.draftId.trim();
  if (!approvalId || !draftId) {
    throw new Error("审批上下文不完整，无法提交审批决策");
  }

  const batchApproval = context.cardType === "approval_batch";
  const requestApproval =
    context.cardType === "approval_request" ||
    context.cardType === "approval_withdraw";
  return {
    url: batchApproval
      ? `/api/agent-approval-batches/${encodeURIComponent(approvalId)}/${action}`
      : `/api/agent-approvals/${encodeURIComponent(approvalId)}/${action}`,
    init: {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        // A retried click after a network timeout must stay the same action,
        // so the idempotency key is stable per decision.
        idempotencyKey: `${approvalId}:${action}`,
        draftId,
        threadId: context.threadId,
        runId: context.runId,
        messageId: context.messageId,
        ...(action === "reject"
          ? {
              reason: batchApproval
                ? "用户取消批量审批"
                : requestApproval
                  ? "用户取消审批操作"
                  : "用户取消会议预约",
            }
          : {}),
      }),
    },
  };
}
