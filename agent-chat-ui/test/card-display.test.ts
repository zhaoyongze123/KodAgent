import assert from "node:assert/strict";
import test from "node:test";
import {
  displayBatchStatus,
  displayFieldValue,
  displayDimensionValue,
  displayDocumentType,
  displaySourceType,
  displayStatus,
  displayVerdict,
} from "../src/lib/card-display.ts";

test("party-file enum codes are rendered as human labels", () => {
  assert.equal(displayFieldValue("分类", 5, { domain: "party_file" }), "分类名称待确认");
  assert.equal(displayFieldValue("状态", 0, { domain: "party_file" }), "已发布");
  assert.equal(displayFieldValue("存储方式", 2, { domain: "party_file" }), "可道云存储");
  assert.equal(displayFieldValue("分发类型", 1, { domain: "party_file" }), "全员");
});

test("approval and validation statuses are stable across cards", () => {
  assert.equal(displayStatus("PENDING"), "待确认");
  assert.equal(displayBatchStatus("SUCCESS"), "已完成");
  assert.equal(displayVerdict("BLOCK"), "阻断");
});

test("technical identifiers never appear as raw card values", () => {
  assert.equal(displayFieldValue("预约编号", 40), "已关联业务记录");
  assert.equal(displayFieldValue("流程实例", "process-42"), "已关联业务记录");
  assert.match(
    displayFieldValue("表单", JSON.stringify({ categoryId: 5, status: 0, amount: 50 }), { domain: "approval" }),
    /分类名称待确认/,
  );
  assert.doesNotMatch(
    displayFieldValue("表单", JSON.stringify({ categoryId: 5, status: 0, amount: 50 }), { domain: "approval" }),
    /"status": "0"/,
  );
});

test("all common dimension codes have a safe human fallback", () => {
  assert.equal(displaySourceType("MEETING_BOOKING"), "会议预约");
  assert.equal(displaySourceType(7), "来源类型待确认");
  assert.equal(displayDocumentType("NOTICE"), "通知公告");
  assert.equal(displayDimensionValue(12, "部门名称"), "部门名称待确认");
  assert.equal(displayDimensionValue(3, "会议室名称"), "会议室名称待确认");
  assert.equal(displayDimensionValue(4, "审批流程"), "审批流程名称待确认");
  assert.equal(displayFieldValue("审批类型", 3), "审批类型待确认");
  assert.equal(displayFieldValue("参会人", "7,8"), "人员信息待确认");
  assert.equal(displayFieldValue("category", 5), "分类名称待确认");
  assert.equal(displayFieldValue("type", 2), "类型待确认");
  assert.equal(displayFieldValue("targetId", 9), "已关联业务记录");
  assert.equal(displayFieldValue("operationId", 9), "已关联业务记录");
});
