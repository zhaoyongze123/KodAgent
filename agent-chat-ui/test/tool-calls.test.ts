import assert from "node:assert/strict";
import test from "node:test";
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
