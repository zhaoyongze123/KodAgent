import assert from "node:assert/strict";
import test from "node:test";
import {
  isApprovalCardProjection,
  isApprovalControlFlow,
} from "../src/lib/approval-tool-result.ts";
import { isMeetingApprovalCancellation } from "../src/lib/meeting-tool-result.ts";

const officialReject =
  "User rejected the tool call for `confirm_meeting_booking` with id confirm-call. " +
  "The tool was not executed. Do not retry this tool call unless the user explicitly requests it.";

test("recognizes the official DeepAgents HITL English rejection", () => {
  assert.equal(
    isMeetingApprovalCancellation({
      name: "confirm_meeting_booking",
      status: "error",
      content: officialReject,
    }),
    true,
  );
});

test("recognizes the structured approval rejection", () => {
  assert.equal(
    isMeetingApprovalCancellation({
      name: "confirm_meeting_booking",
      status: "error",
      content: JSON.stringify({
        ok: false,
        error: { code: "APPROVAL_REJECTED", message: "用户已取消会议室预约" },
      }),
    }),
    true,
  );
});

test("does not classify another tool with the official rejection text", () => {
  assert.equal(
    isMeetingApprovalCancellation({
      name: "list_available_meeting_rooms",
      status: "error",
      content: officialReject,
    }),
    false,
  );
});

test("does not classify a real confirm tool failure", () => {
  assert.equal(
    isMeetingApprovalCancellation({
      name: "confirm_meeting_booking",
      status: "error",
      content: JSON.stringify({
        ok: false,
        error: { code: "TOOL_EXECUTION_FAILED", message: "Java 服务异常" },
      }),
    }),
    false,
  );
});

test("does not classify a non-error status", () => {
  assert.equal(
    isMeetingApprovalCancellation({
      name: "confirm_meeting_booking",
      status: "success",
      content: officialReject,
    }),
    false,
  );
});

test("classifies approval rejection for non-meeting approval tools", () => {
  assert.equal(
    isApprovalControlFlow({
      name: "confirm_personal_schedule",
      status: "error",
      content: JSON.stringify({
        ok: false,
        error: { code: "APPROVAL_REJECTED", message: "用户已取消个人日程操作" },
      }),
    }),
    true,
  );
  assert.equal(
    isApprovalControlFlow({
      name: "confirm_create_party_file",
      status: "error",
      content: JSON.stringify({
        ok: false,
        error: { code: "APPROVAL_EXPIRED", message: "确认已过期" },
      }),
    }),
    true,
  );
});

test("classifies a structured approval rejection even when transport status is success", () => {
  assert.equal(
    isApprovalControlFlow({
      name: "confirm_create_party_file",
      status: "success",
      content: JSON.stringify({
        ok: false,
        error: { code: "APPROVAL_REJECTED", message: "用户已取消党务文件操作" },
      }),
    }),
    true,
  );
});

test("recognizes party-file approval drafts as interrupt projections", () => {
  assert.equal(
    isApprovalCardProjection({
      name: "create_party_file_draft",
      status: "success",
      content: JSON.stringify({
        ok: true,
        data: { draftId: "draft-1", approvalId: "approval-1" },
        presentation: {
          blockType: "card",
          cardType: "party_file_approval",
        },
      }),
    }),
    true,
  );
});

test("does not hide ordinary approval tool failures", () => {
  assert.equal(
    isApprovalControlFlow({
      name: "confirm_personal_schedule",
      status: "error",
      content: JSON.stringify({
        ok: false,
        error: { code: "SCHEDULE_BUSINESS_REJECTED", message: "时间冲突" },
      }),
    }),
    false,
  );
});

test("classifies the official HITL rejection for any confirmation tool", () => {
  assert.equal(
    isApprovalControlFlow({
      name: "confirm_personal_schedule",
      status: "error",
      content:
        "User rejected the tool call for `confirm_personal_schedule` with id confirm-call. " +
        "The tool was not executed. Do not retry this tool call unless the user explicitly requests it.",
    }),
    true,
  );
});
