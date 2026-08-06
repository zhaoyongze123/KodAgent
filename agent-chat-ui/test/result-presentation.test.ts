import test from "node:test";
import assert from "node:assert/strict";
import {
  agentBlockFromToolResult,
  resultEnvelopeFromToolResult,
} from "../src/types/agent-block.ts";

test("canonical top-level result presentation becomes a result block", () => {
  const content = {
    ok: true,
    data: { items: [{ id: "task-1", name: "合同审批", amount: 180000 }] },
    presentation: {
      resultKind: "ranked_list",
      sourceResultId: "approval-query-1",
      title: "金额排序",
      summary: "共 1 条可排序记录",
    },
  };
  const result = resultEnvelopeFromToolResult(content, "message-1");
  assert.equal(result?.presentation.resultKind, "ranked_list");
  assert.equal(result?.sourceResultId, "approval-query-1");
  assert.equal(result?.messageId, "message-1");
  assert.equal(agentBlockFromToolResult("search_my_pending_approvals", content)?.kind, "result");
});

test("nested PresentationSpec is accepted and unknown kinds use rich_text fallback", () => {
  const content = {
    ok: true,
    data: {
      presentation: {
        resultKind: "future_result_kind",
        sourceResultId: "result-2",
        summary: { headline: "后续能力" },
      },
      primaryData: { markdown: "结果正文" },
    },
  };
  const result = resultEnvelopeFromToolResult(content);
  assert.equal(result?.presentation.resultKind, "rich_text");
  assert.equal(result?.presentation.sourceResultId, "result-2");
  assert.equal(result?.presentation.headline, "后续能力");
  assert.deepEqual((result?.data as { primaryData: { markdown: string } }).primaryData, { markdown: "结果正文" });
});

test("legacy cardType presentation remains on the compatibility path", () => {
  const block = agentBlockFromToolResult("list_my_pending_approvals", {
    ok: true,
    data: { list: [{ taskId: "task-1", name: "请假审批" }], total: 1 },
    presentation: { blockType: "card", cardType: "todo" },
  });
  assert.equal(block?.kind, "card");
  assert.equal(block?.kind === "card" ? block.card.type : undefined, "todo");
});
