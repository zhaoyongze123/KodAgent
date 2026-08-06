import assert from "node:assert/strict";
import test from "node:test";
import {
  approvalPayloadFromInterrupt,
  isApprovalInterruptAction,
  isActionableApprovalPayload,
  isActionableMeetingInterrupt,
  isCurrentActionableApproval,
} from "../src/lib/meeting-approval-card.ts";

function interrupt(args: Record<string, unknown>) {
  return {
    value: {
      action_requests: [{ name: "confirm_meeting_booking", args }],
    },
  };
}

const completeArgs = {
  approvalId: "approval-2",
  draftId: "draft-2",
  threadId: "thread-2",
  runId: "run-2",
  messageId: "message-2",
  cardType: "meeting_booking",
  fields: [{ label: "主题", value: "验收会议" }],
};

test("only the current interrupt with complete identity is actionable", () => {
  const currentInterrupt = interrupt(completeArgs);
  const payload = approvalPayloadFromInterrupt(currentInterrupt);
  assert.equal(isActionableApprovalPayload(payload), true);
  assert.equal(isActionableMeetingInterrupt(currentInterrupt), true);
  assert.equal(isCurrentActionableApproval(payload, currentInterrupt), true);
  assert.equal(payload?.fields[0]?.value, "验收会议");
});

test("missing one interrupt identity makes the card read-only", () => {
  const args = { ...completeArgs };
  delete (args as Record<string, unknown>).messageId;
  const payload = approvalPayloadFromInterrupt(interrupt(args));
  assert.equal(isActionableApprovalPayload(payload), false);
  assert.equal(isActionableMeetingInterrupt(interrupt(args)), false);
});

test("a complete historical payload cannot authorize a different interrupt", () => {
  const historical = approvalPayloadFromInterrupt(interrupt(completeArgs));
  const current = interrupt({
    ...completeArgs,
    approvalId: "approval-current",
  });
  assert.equal(isCurrentActionableApproval(historical, current), false);
});

test("legacy snake_case or unrelated event data cannot authorize a card", () => {
  const payload = approvalPayloadFromInterrupt(
    interrupt({
      approval_id: "old-approval",
      draft_id: "old-draft",
      thread_id: "old-thread",
      run_id: "old-run",
      message_id: "old-message",
    }),
  );
  assert.equal(payload?.approvalId, "");
  assert.equal(isActionableApprovalPayload(payload), false);
  assert.equal(
    approvalPayloadFromInterrupt({
      type: "approval.required",
      data: { approvalId: "event-approval", draftId: "event-draft" },
    }),
    undefined,
  );
  assert.equal(
    approvalPayloadFromInterrupt({
      value: { action_requests: [{ args: completeArgs }] },
    }),
    undefined,
  );
  assert.equal(
    isApprovalInterruptAction({
      value: { action_requests: [{ args: completeArgs }] },
    }),
    false,
  );
  assert.equal(
    approvalPayloadFromInterrupt({
      value: {
        action_requests: [
          { name: "confirm_unregistered_operation", args: completeArgs },
        ],
      },
    }),
    undefined,
  );
});

test("batch approval interrupt uses the same one-card approval contract", () => {
  const batchInterrupt = {
    value: {
      action_requests: [
        {
          name: "confirm_approval_batch_action",
          args: {
            ...completeArgs,
            approvalId: "preview-1",
            draftId: "preview-1",
            cardType: "approval_batch",
            title: "确认批量驳回",
            approveLabel: "确认批量驳回",
            rejectLabel: "取消操作",
          },
        },
      ],
    },
  };
  const payload = approvalPayloadFromInterrupt(batchInterrupt);
  assert.equal(payload?.cardType, "approval_batch");
  assert.equal(payload?.approveLabel, "确认批量驳回");
  // The durable action request is enough to choose ApprovalCard. Some
  // LangGraph server versions omit review_configs, which is only generic UI
  // metadata and must not turn a batch operation into text confirmation.
  assert.equal(isApprovalInterruptAction(batchInterrupt), true);
  assert.equal(isActionableMeetingInterrupt(batchInterrupt), true);
  assert.equal(isCurrentActionableApproval(payload, batchInterrupt), true);
});

test("meeting update and cancellation retain their operation-specific labels", () => {
  const cancellation = approvalPayloadFromInterrupt(
    interrupt({
      ...completeArgs,
      title: "取消会议预约",
      approveLabel: "确认取消",
      rejectLabel: "保留原预约",
      fields: [{ label: "预约编号", value: "38" }],
      draft: { operation: "CANCEL", sourceBookingId: 38 },
    }),
  );
  const update = approvalPayloadFromInterrupt(
    interrupt({
      ...completeArgs,
      title: "修改会议预约",
      approveLabel: "确认提交",
      rejectLabel: "取消操作",
      draft: { operation: "UPDATE", sourceBookingId: 38 },
    }),
  );
  assert.equal(cancellation?.approveLabel, "确认取消");
  assert.equal(cancellation?.fields[0]?.label, "预约编号");
  assert.equal(update?.title, "修改会议预约");
  assert.equal(isActionableApprovalPayload(cancellation), true);
  assert.equal(isActionableApprovalPayload(update), true);
});
