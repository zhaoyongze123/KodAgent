import assert from "node:assert/strict";
import test from "node:test";
import { findLatestCorrelatedToolEvent } from "../src/lib/tool-event-correlation.ts";

const event = (
  toolCallId: string | undefined,
  type: "tool.completed" | "tool.failed",
  toolName = "get_my_calendar",
) => ({
  toolCallId,
  type,
  data: { toolName },
});

test("does not match same-name events with a different toolCallId", () => {
  assert.equal(
    findLatestCorrelatedToolEvent(
      [event("call-other", "tool.completed")],
      "call-current",
      "get_my_calendar",
    ),
    undefined,
  );
});

test("matches the same toolCallId and toolName", () => {
  const current = event("call-current", "tool.completed");
  assert.equal(
    findLatestCorrelatedToolEvent([current], "call-current", "get_my_calendar"),
    current,
  );
});

test("does not scan by name when the ToolMessage has no tool_call_id", () => {
  assert.equal(
    findLatestCorrelatedToolEvent(
      [event("call-existing", "tool.completed")],
      undefined,
      "get_my_calendar",
    ),
    undefined,
  );
});

test("does not match an event without the correlation ID", () => {
  assert.equal(
    findLatestCorrelatedToolEvent(
      [{ type: "tool.completed", data: { toolName: "get_my_calendar" } }],
      "call-current",
      "get_my_calendar",
    ),
    undefined,
  );
});

test("selects the latest terminal event for the current tool call", () => {
  const completed = event("call-current", "tool.completed");
  const failed = event("call-current", "tool.failed");
  assert.equal(
    findLatestCorrelatedToolEvent(
      [completed, failed],
      "call-current",
      "get_my_calendar",
    ),
    failed,
  );
});
