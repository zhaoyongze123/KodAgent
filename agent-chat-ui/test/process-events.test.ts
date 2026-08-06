import assert from "node:assert/strict";
import test from "node:test";
import {
  buildProcessRunTurnMap,
  collectCustomProcessEvents,
  normalizeProcessEvents,
  reduceProcessEvents,
  type ProcessEvent,
} from "../src/components/thread/process-events.ts";
import { adaptAgentCustomEvent } from "../src/lib/agent-event-adapter.ts";

const narration = (
  id: string,
  entryId: string,
  text: string,
  revision: number,
  extra: Partial<ProcessEvent> = {},
): ProcessEvent => ({
  id,
  entryId,
  type: "message",
  text,
  revision,
  narrationStatus: "completed",
  ...extra,
});

test("same entryId revisions update one narration row", () => {
  const events = reduceProcessEvents([
    narration("evt-1", "nar:one", "正在查询", 1, { source: "custom" }),
    narration("evt-1", "nar:one", "查询完成", 2, { source: "custom" }),
  ]);

  assert.equal(events.length, 1);
  assert.equal(events[0].text, "查询完成");
  assert.equal(events[0].revision, 2);
});

test("terminal narration cannot regress to streaming", () => {
  const events = reduceProcessEvents([
    narration("evt-1", "nar:terminal", "已完成", 2, {
      narrationStatus: "completed",
      source: "persisted",
      cursorId: 20,
    }),
    narration("evt-1", "nar:terminal", "继续处理中", 3, {
      narrationStatus: "streaming",
      source: "custom",
    }),
  ]);

  assert.equal(events.length, 1);
  assert.equal(events[0].text, "已完成");
  assert.equal(events[0].narrationStatus, "completed");
});

test("server cursor orders out-of-order narration delivery", () => {
  const events = normalizeProcessEvents([
    narration("evt-2", "nar:two", "第二步", 1, { cursorId: 20 }),
    narration("evt-1", "nar:one", "第一步", 1, { cursorId: 10 }),
  ]);
  assert.deepEqual(
    events.map((event) => event.text),
    ["第一步", "第二步"],
  );
});

test("same narration text from different actors remains distinct", () => {
  const events = reduceProcessEvents([
    narration("evt-main", "nar:main", "正在检查可用性", 1, {
      actor: "main_agent",
    }),
    narration("evt-sub", "nar:sub", "正在检查可用性", 1, {
      actor: "sub_agent",
    }),
  ]);
  assert.equal(events.length, 2);
});

test("legacy plan and progress are projected without namespace inference", () => {
  const custom = adaptAgentCustomEvent(
    {
      type: "agent_event",
      event: {
        eventId: "legacy-plan",
        runId: "run-1",
        type: "plan.created",
        data: { text: "旧计划" },
      },
    },
    { namespace: ["tools:ignored"], receivedOrder: 1 },
  );
  assert.ok(custom);
  const events = collectCustomProcessEvents([custom]);
  assert.equal(events[0].entryId, "legacy:legacy-plan");
  assert.equal(events[0].text, "旧计划");
});

test("workflow lifecycle events are projected as ordered process messages", () => {
  const custom = adaptAgentCustomEvent(
    {
      type: "agent_event",
      event: {
        eventId: "workflow-node-1",
        runId: "run-workflow",
        type: "workflow.node.completed",
        data: {
          text: "预约信息已整理完成",
          workflowType: "meeting_booking",
          workflowNode: "prepare_request",
        },
      },
    },
    { namespace: [], receivedOrder: 1 },
  );
  assert.ok(custom);
  const events = collectCustomProcessEvents([custom]);
  assert.equal(events[0].text, "预约信息已整理完成");
  assert.equal(events[0].entryId, "legacy:workflow-node-1");
});

test("run-to-turn ownership remains stable during approval pause and recovery", () => {
  const ownership = buildProcessRunTurnMap(
    [{ runId: "paused-run", messageId: "human-1" }],
    [{ runId: "paused-run" }],
    "human-2",
  );
  assert.equal(ownership.get("paused-run"), "human-1");
});
