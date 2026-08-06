import assert from "node:assert/strict";
import test from "node:test";
import {
  agentBlockFromToolResult,
  approvalInboxPayloadFromData,
} from "../src/types/agent-block.ts";

test("approval inbox result becomes a separate read-only filter card", () => {
  const block = agentBlockFromToolResult(
    "search_my_pending_approvals",
    JSON.stringify({
      ok: true,
      presentation: { blockType: "card", cardType: "approval_inbox" },
      data: {
        totalPending: 12,
        scannedCount: 12,
        matchedCount: 1,
        candidates: [{ taskId: "task-1", name: "审批", amount: 4999.5, pendingDays: 3 }],
        excludedCount: 11,
        exclusions: [{ taskId: "task-2", exclusionReasons: ["AMOUNT_MISMATCH"] }],
        exclusionReasonCounts: { AMOUNT_MISMATCH: 11 },
        truncated: false,
      },
    }),
  );

  assert.equal(block?.kind, "card");
  assert.equal(block?.kind === "card" ? block.card.type : "", "approval_inbox");
});

test("approval inbox exposes only allowlisted display fields, never form variables", () => {
  const payload = approvalInboxPayloadFromData({
    candidates: [{ taskId: "task-1", amount: "5000", formVariables: { secret: "must not render" } }],
    exclusions: [],
  });

  assert.deepEqual(payload?.candidates[0], { taskId: "task-1", amount: 5000 });
});
