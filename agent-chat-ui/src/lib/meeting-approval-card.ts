import type { ApprovalField, ApprovalPayload } from "@/types/agent-block";

export type InterruptActionRequest = {
  name?: string;
  args?: Record<string, unknown>;
};

const APPROVAL_INTERRUPT_ACTIONS = new Set([
  "confirm_meeting_booking",
  "confirm_personal_schedule",
  "confirm_create_party_file",
  "confirm_update_party_file",
  "confirm_delete_party_file",
  "confirm_approval_batch_action",
  "confirm_approval_task_action",
  "confirm_approval_request_action",
  "confirm_approval_withdraw_action",
]);

function interruptValue(interrupt: unknown): {
  action_requests?: InterruptActionRequest[];
} | null {
  const value = (Array.isArray(interrupt) ? interrupt[0] : interrupt) as
    | { value?: unknown }
    | null
    | undefined;
  const nested = value?.value;
  return nested && typeof nested === "object"
    ? (nested as { action_requests?: InterruptActionRequest[] })
    : null;
}

export function getInterruptAction(
  interrupt: unknown,
): InterruptActionRequest | undefined {
  return interruptValue(interrupt)?.action_requests?.[0];
}

/**
 * Identify the dedicated ApprovalCard protocol independently from the
 * generic inbox presentation schema.  The action request is the protocol
 * contract; `review_configs` is optional LangGraph UI metadata and must not
 * cause a business confirmation to degrade into free-form text input.
 */
export function isApprovalInterruptAction(interrupt: unknown): boolean {
  return APPROVAL_INTERRUPT_ACTIONS.has(getInterruptAction(interrupt)?.name ?? "");
}

function nonEmptyString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() ? value : undefined;
}

function readFieldArray(value: unknown): ApprovalField[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const field = item as { label?: unknown; value?: unknown; icon?: unknown };
    const label = nonEmptyString(field.label);
    if (!label) return [];
    return [
      {
        label,
        value: field.value == null ? "" : String(field.value),
        ...(nonEmptyString(field.icon) ? { icon: String(field.icon) } : {}),
      },
    ];
  });
}

/** Build display data only from the current LangGraph interrupt payload. */
export function approvalPayloadFromInterrupt(
  interrupt: unknown,
): ApprovalPayload | undefined {
  const action = getInterruptAction(interrupt);
  const actionName = action?.name;
  // Do not infer a card contract from partial or unknown interrupt data.
  // `action` is transport data and may be absent even when a malformed
  // interrupt wrapper exists; such a payload must remain non-actionable.
  if (!action || !actionName || !APPROVAL_INTERRUPT_ACTIONS.has(actionName)) {
    return undefined;
  }

  const args = action.args ?? {};
  const draft =
    args.draft && typeof args.draft === "object"
      ? (args.draft as Record<string, unknown>)
      : undefined;
  const status =
    args.status === "APPROVED" ||
    args.status === "REJECTED" ||
    args.status === "EXPIRED"
      ? args.status
      : "PENDING";

  return {
    approvalId: nonEmptyString(args.approvalId) ?? "",
    draftId: nonEmptyString(args.draftId) ?? "",
    operationId: nonEmptyString(args.operationId),
    threadId: nonEmptyString(args.threadId),
    runId: nonEmptyString(args.runId),
    originRunId: nonEmptyString(args.originRunId),
    resumeRunId: nonEmptyString(args.resumeRunId),
    messageId: nonEmptyString(args.messageId),
    action: actionName,
    status,
    fields: readFieldArray(args.fields),
    allowedActions: ["approve", "reject"],
    cardType: nonEmptyString(args.cardType),
    title: nonEmptyString(args.title),
    approveLabel: nonEmptyString(args.approveLabel),
    rejectLabel: nonEmptyString(args.rejectLabel),
    expiresAt: nonEmptyString(args.expiresAt),
    draft,
  };
}

/** A historical payload never contains enough context to enable a write. */
export function isActionableApprovalPayload(
  payload: ApprovalPayload | undefined,
): payload is ApprovalPayload & {
  approvalId: string;
  draftId: string;
  threadId: string;
  runId: string;
  messageId: string;
} {
  const hasIdentity = (value: unknown) =>
    typeof value === "string" && value.trim().length > 0;
  return Boolean(
    payload &&
    payload.status === "PENDING" &&
    hasIdentity(payload.approvalId) &&
    hasIdentity(payload.draftId) &&
    hasIdentity(payload.threadId) &&
    hasIdentity(payload.runId) &&
    hasIdentity(payload.messageId),
  );
}

export function isActionableMeetingInterrupt(interrupt: unknown): boolean {
  return (
    isApprovalInterruptAction(interrupt) &&
    isActionableApprovalPayload(approvalPayloadFromInterrupt(interrupt))
  );
}

/** Require the card payload and interrupt to describe the same approval slot. */
export function isCurrentActionableApproval(
  payload: ApprovalPayload | undefined,
  interrupt: unknown,
): boolean {
  const current = approvalPayloadFromInterrupt(interrupt);
  return Boolean(
    isActionableApprovalPayload(payload) &&
    isActionableMeetingInterrupt(interrupt) &&
    current &&
    payload.approvalId === current.approvalId &&
    payload.draftId === current.draftId &&
    payload.threadId === current.threadId &&
    payload.runId === current.runId &&
    payload.messageId === current.messageId,
  );
}
