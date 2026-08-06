import assert from "node:assert/strict";
import test from "node:test";
import {
  agentBlockFromToolResult,
  approvalWorkflowPayloadFromData,
} from "../src/types/agent-block.ts";

test("approval preview is rendered as a structured workflow card", () => {
  const block = agentBlockFromToolResult(
    "preview_approval_request",
    JSON.stringify({
      ok: true,
      presentation: { blockType: "card", cardType: "approval_preview" },
      data: {
        request: { requestType: "leave", startTime: "2026-08-01 09:00:00", endTime: "2026-08-01 18:00:00", reason: "家庭事务" },
        preview: { normalizedSummary: "部门负责人", requiresApprovalSelection: false },
      },
    }),
  );

  assert.equal(block?.kind, "card");
  assert.equal(block?.kind === "card" ? block.card.type : "", "approval_workflow");
});

test("workflow card does not expose Flowable raw variables", () => {
  const payload = approvalWorkflowPayloadFromData("approval_task", {
    name: "部门审批",
    startUserName: "张三",
    processDefinitionName: "请假流程",
    formVariables: { privateInternalVariable: "must not render" },
  });

  assert.deepEqual(payload?.fields.map((field) => field.label), ["任务", "发起人", "流程"]);
});
