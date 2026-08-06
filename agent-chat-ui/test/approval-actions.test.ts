import assert from "node:assert/strict";
import test from "node:test";
import {
  buildApprovalDecisionRequest,
  buildApprovalResumeMetadata,
  getResumeIdempotencyKey,
  shouldRecordResumeAudit,
} from "../src/lib/approval-actions.ts";

test("resume audit key is deterministic across retries and remounts", () => {
  const first = getResumeIdempotencyKey("approval-123");
  assert.equal(first, "agent-resume:v1:approval-123");
  assert.equal(getResumeIdempotencyKey(" approval-123 "), first);
  assert.equal(getResumeIdempotencyKey("approval-123"), first);
});

test("resume audit is only recorded for approval, never rejection", () => {
  assert.equal(shouldRecordResumeAudit("approve"), true);
  assert.equal(shouldRecordResumeAudit("reject"), false);
});

test("blank approval ids cannot produce an audit key", () => {
  assert.throws(() => getResumeIdempotencyKey("   "), /审批记录不存在/);
});

test("rejection uses one durable approval decision request", () => {
  const request = buildApprovalDecisionRequest(
    {
      approvalId: "approval-123",
      draftId: "draft-456",
      threadId: "thread-789",
      runId: "run-012",
      messageId: "message-345",
    },
    "reject",
  );

  assert.equal(request.url, "/api/agent-approvals/approval-123/reject");
  assert.equal(request.init.method, "POST");
  assert.deepEqual(JSON.parse(String(request.init.body)), {
    idempotencyKey: "approval-123:reject",
    draftId: "draft-456",
    threadId: "thread-789",
    runId: "run-012",
    messageId: "message-345",
    reason: "用户取消会议预约",
  });
  assert.doesNotMatch(request.url, /agent-drafts/);
});

test("batch rejection persists only the card decision before HITL resume", () => {
  const request = buildApprovalDecisionRequest(
    {
      approvalId: "preview-123",
      draftId: "preview-123",
      threadId: "thread-789",
      runId: "run-012",
      messageId: "message-345",
      cardType: "approval_batch",
    },
    "reject",
  );

  assert.equal(
    request.url,
    "/api/agent-approval-batches/preview-123/reject",
  );
  assert.deepEqual(JSON.parse(String(request.init.body)), {
    idempotencyKey: "preview-123:reject",
    draftId: "preview-123",
    threadId: "thread-789",
    runId: "run-012",
    messageId: "message-345",
    reason: "用户取消批量审批",
  });
});

test("approval request rejection uses an approval-specific reason", () => {
  const request = buildApprovalDecisionRequest(
    {
      approvalId: "request-123",
      draftId: "draft-456",
      threadId: "thread-789",
      runId: "run-012",
      messageId: "message-345",
      cardType: "approval_request",
    },
    "reject",
  );

  assert.deepEqual(JSON.parse(String(request.init.body)), {
    idempotencyKey: "request-123:reject",
    draftId: "draft-456",
    threadId: "thread-789",
    runId: "run-012",
    messageId: "message-345",
    reason: "用户取消审批操作",
  });
});

test("batch ApprovalCard uses one decision request and one origin-bound resume", () => {
  const context = {
    approvalId: "preview-123",
    draftId: "preview-123",
    threadId: "thread-789",
    runId: "origin-run-012",
    messageId: "message-345",
    cardType: "approval_batch",
  };
  const decision = buildApprovalDecisionRequest(context, "approve");
  const resume = buildApprovalResumeMetadata(context);

  assert.equal(decision.url, "/api/agent-approval-batches/preview-123/approve");
  assert.deepEqual(JSON.parse(String(decision.init.body)), {
    idempotencyKey: "preview-123:approve",
    draftId: "preview-123",
    threadId: "thread-789",
    runId: "origin-run-012",
    messageId: "message-345",
  });
  assert.deepEqual(resume, {
    approvalId: "preview-123",
    draftId: "preview-123",
    threadId: "thread-789",
    originRunId: "origin-run-012",
    messageId: "message-345",
  });
});

test("HITL resume stays bound to the interrupted message and origin run", () => {
  assert.deepEqual(
    buildApprovalResumeMetadata({
      approvalId: "approval-123",
      draftId: "draft-456",
      threadId: "thread-789",
      runId: "origin-run-012",
      messageId: "message-345",
    }),
    {
      approvalId: "approval-123",
      draftId: "draft-456",
      threadId: "thread-789",
      originRunId: "origin-run-012",
      messageId: "message-345",
    },
  );
});

test("HITL resume rejects missing origin identity", () => {
  assert.throws(
    () =>
      buildApprovalResumeMetadata({
        approvalId: "approval-123",
        draftId: "draft-456",
      }),
    /审批恢复上下文不完整/,
  );
});

test("ApprovalCard does not issue a second draft cancellation write", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(
    new URL("../src/components/thread/cards/ApprovalCard.tsx", import.meta.url),
    "utf8",
  );

  assert.match(source, /buildApprovalDecisionRequest/);
  assert.match(source, /isApprovalInterruptAction\(interrupt\)/);
  assert.doesNotMatch(source, /agent-drafts\/.*\/cancel/);
});
