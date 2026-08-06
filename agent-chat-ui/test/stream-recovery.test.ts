import assert from "node:assert/strict";
import test from "node:test";
import {
  MAX_STREAM_RECOVERY_ATTEMPTS,
  isDurableRunPaused,
  isDurableRunActive,
  isDurableRunTerminal,
  shouldRejoinDurableRun,
  streamRecoveryDelayMs,
} from "../src/lib/stream-recovery.ts";
import {
  acquireRunStreamAttachment,
  clearLiveRunId,
  getRunStreamAttachment,
  liveRunStorageKey,
  readLiveRunId,
  releaseRunStreamAttachment,
  resetRunStreamAttachmentsForTests,
  storeLiveRunId,
} from "../src/lib/run-stream-attachment.ts";
import {
  acquireDurableRunReconciliation,
  reconcileDurableRun,
} from "../src/lib/run-stream-coordinator.ts";

test("only pending or running durable runs are eligible for stream recovery", () => {
  assert.equal(shouldRejoinDurableRun("pending", 0), true);
  assert.equal(shouldRejoinDurableRun("RUNNING", 1), true);
  assert.equal(shouldRejoinDurableRun("success", 0), false);
  assert.equal(shouldRejoinDurableRun("error", 0), false);
  assert.equal(
    shouldRejoinDurableRun("running", MAX_STREAM_RECOVERY_ATTEMPTS),
    false,
  );
});

test("transport finish keeps active durable runs recoverable", () => {
  assert.equal(isDurableRunActive("pending"), true);
  assert.equal(isDurableRunActive("RUNNING"), true);
  assert.equal(isDurableRunTerminal("success"), true);
  assert.equal(isDurableRunTerminal("error"), true);
  assert.equal(isDurableRunTerminal("cancelled"), true);
  assert.equal(isDurableRunTerminal("running"), false);
  assert.equal(isDurableRunPaused("interrupted"), true);
  assert.equal(isDurableRunTerminal("interrupted"), false);
  assert.equal(isDurableRunActive("interrupted"), false);
});

test("stream recovery backoff is bounded", () => {
  assert.equal(streamRecoveryDelayMs(0), 1000);
  assert.equal(streamRecoveryDelayMs(1), 2000);
  assert.equal(streamRecoveryDelayMs(10), 5000);
});

test("concurrent recovery joins share one live attachment", async () => {
  resetRunStreamAttachmentsForTests();
  let calls = 0;
  let resolveJoin!: (value: string) => void;
  const join = () => {
    calls += 1;
    return new Promise<string>((resolve) => {
      resolveJoin = resolve;
    });
  };

  const first = acquireRunStreamAttachment("run-1", join);
  const second = acquireRunStreamAttachment("run-1", join);

  await Promise.resolve();
  assert.equal(calls, 1);
  assert.equal(second.reused, true);
  assert.deepEqual(second.token, first.token);
  assert.equal(getRunStreamAttachment("run-1"), first.token);

  resolveJoin("joined");
  assert.equal(await first.promise, "joined");
  assert.equal(await second.promise, "joined");
  assert.equal(getRunStreamAttachment("run-1"), null);

  const next = acquireRunStreamAttachment("run-1", async () => {
    calls += 1;
    return "next";
  });
  assert.equal(next.reused, false);
  assert.equal(await next.promise, "next");
  assert.equal(calls, 2);
});

test("different runs have independent attachments", async () => {
  resetRunStreamAttachmentsForTests();
  const first = acquireRunStreamAttachment("run-a", async () => "a");
  const second = acquireRunStreamAttachment("run-b", async () => "b");

  assert.notDeepEqual(first.token, second.token);
  assert.equal(await first.promise, "a");
  assert.equal(await second.promise, "b");
});

test("a stale cleanup cannot release a newer attachment", async () => {
  resetRunStreamAttachmentsForTests();
  let resolveFirst!: () => void;
  const first = acquireRunStreamAttachment(
    "run-stale",
    () => new Promise<void>((resolve) => (resolveFirst = resolve)),
  );
  await Promise.resolve();
  assert.equal(releaseRunStreamAttachment(first.token), true);

  const second = acquireRunStreamAttachment("run-stale", async () => undefined);
  assert.equal(releaseRunStreamAttachment(first.token), false);
  assert.equal(getRunStreamAttachment("run-stale"), second.token);

  resolveFirst();
  await first.promise;
  await second.promise;
});

test("live run markers are scoped to a thread", () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
    removeItem: (key: string) => void values.delete(key),
  };

  assert.equal(liveRunStorageKey("thread-1"), "lg:stream:thread-1");
  assert.equal(readLiveRunId(storage, "thread-1"), null);
  storeLiveRunId(storage, "thread-1", "run-1");
  assert.equal(readLiveRunId(storage, "thread-1"), "run-1");
  assert.equal(readLiveRunId(storage, "thread-2"), null);
  clearLiveRunId(storage, "thread-1");
  assert.equal(readLiveRunId(storage, "thread-1"), null);
});

test("early transport finish rejoins a still-running durable run", async () => {
  const values = new Map<string, string>([
    ["lg:stream:thread-early", "run-early"],
  ]);
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    removeItem: (key: string) => void values.delete(key),
  };
  const statuses = ["running", "running", "success"];
  let joinCalls = 0;

  const result = await reconcileDurableRun({
    threadId: "thread-early",
    runId: "run-early",
    storage,
    getStatus: async () => ({ status: statuses.shift() }),
    joinStream: async () => {
      joinCalls += 1;
    },
    delay: async () => undefined,
  });

  assert.equal(result, "terminal");
  assert.equal(joinCalls, 1);
  assert.equal(values.has("lg:stream:thread-early"), false);
});

test("an interrupted HITL run stays resumable without an automatic join", async () => {
  const values = new Map<string, string>([
    ["lg:stream:thread-hitl", "run-hitl"],
  ]);
  let joinCalls = 0;

  const result = await reconcileDurableRun({
    threadId: "thread-hitl",
    runId: "run-hitl",
    storage: {
      getItem: (key: string) => values.get(key) ?? null,
      removeItem: (key: string) => void values.delete(key),
    },
    getStatus: async () => ({ status: "interrupted" }),
    joinStream: async () => {
      joinCalls += 1;
    },
    delay: async () => undefined,
  });

  assert.equal(result, "active");
  assert.equal(joinCalls, 0);
  assert.equal(values.get("lg:stream:thread-hitl"), "run-hitl");
});

test("concurrent coordinator recovery calls share one reconciliation promise", async () => {
  resetRunStreamAttachmentsForTests();
  let resolve!: () => void;
  let calls = 0;
  const reconcile = () => {
    calls += 1;
    return new Promise<void>((done) => (resolve = done));
  };

  const first = acquireDurableRunReconciliation("run-coordinator", reconcile);
  const second = acquireDurableRunReconciliation("run-coordinator", reconcile);
  assert.equal(second.reused, true);
  assert.equal(first.promise, second.promise);
  await Promise.resolve();
  assert.equal(calls, 1);
  resolve();
  await first.promise;
});
