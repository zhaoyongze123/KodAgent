/**
 * 根据持久化审批 ID 生成恢复审计幂等键。
 *
 * 键不能依赖卡片渲染、点击次数或网络请求 ID；页面刷新后卡片可能重新挂载，
 * 但同一审批恢复仍必须被识别为同一件业务动作。
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
 * 在 LangGraph Server 将 ``Command(resume)`` 实体化为新 Run 时，保留被中断
 * 业务动作的原始身份。
 *
 * 新 Run ID 只是传输身份；审批校验必须继续绑定到持久化审批记录中的原始用户
 * 消息和原始 Run，不能因恢复而换成新 Run。
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
 * 构造一次审批决策对应的唯一持久化业务状态请求。
 *
 * 不在前端单独发送草稿取消请求：驳回审批是 Java 事务边界，由后端原子地结算
 * 它关联的草稿，避免审批状态与草稿状态分离。
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
        // 网络超时后的重复点击仍是同一业务决策，因此幂等键按审批决策固定。
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
