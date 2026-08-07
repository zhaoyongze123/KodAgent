import assert from "node:assert/strict";
import test from "node:test";
import {
  maxDurableEventCursor,
  mergePersistedProcessRuns,
} from "../src/lib/persisted-event-recovery.ts";
import type { ProcessRun } from "../src/components/thread/thread-presentation.ts";

const run = (events: ProcessRun["events"]): ProcessRun => ({
  runId: "run-1",
  messageId: "message-1",
  events,
  elapsedSeconds: 1,
});

test("cursor advances over hidden lifecycle rows", () => {
  assert.equal(
    maxDurableEventCursor([
      { type: "run.started", eventCursor: { cursor: 7 } },
      { type: "draft.created", eventCursor: { cursor: 8 } },
      { type: "narration.upsert", eventCursor: { cursor: 9 } },
    ]),
    9,
  );
});

test("cursor recovery replaces one narration revision without duplicate rows", () => {
  const first = run([
    {
      id: "narration-1",
      entryId: "entry-1",
      type: "message",
      text: "正在检查",
      revision: 1,
      narrationStatus: "streaming",
      source: "persisted",
      cursorId: 10,
    },
  ]);
  const recovered = run([
    {
      id: "narration-1",
      entryId: "entry-1",
      type: "message",
      text: "检查完成",
      revision: 2,
      narrationStatus: "completed",
      source: "persisted",
      cursorId: 10,
    },
    {
      id: "tool-1",
      type: "tool",
      text: "会议室查询",
      status: "completed",
      source: "persisted",
      cursorId: 11,
    },
  ]);

  const merged = mergePersistedProcessRuns([first], [recovered]);
  assert.equal(merged.length, 1);
  assert.deepEqual(
    merged[0].events.map((event) => event.text),
    ["检查完成", "会议室查询"],
  );
  assert.equal(merged[0].events.filter((event) => event.entryId === "entry-1").length, 1);
});

test("out-of-order cursor responses are presented in durable order", () => {
  const merged = mergePersistedProcessRuns(
    [
      run([
        {
          id: "late",
          type: "message",
          text: "第二步",
          source: "persisted",
          cursorId: 20,
        },
      ]),
    ],
    [
      run([
        {
          id: "early",
          type: "message",
          text: "第一步",
          source: "persisted",
          cursorId: 10,
        },
      ]),
    ],
  );

  assert.deepEqual(merged[0].events.map((event) => event.text), ["第一步", "第二步"]);
});
