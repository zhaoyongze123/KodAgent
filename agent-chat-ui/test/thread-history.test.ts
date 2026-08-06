import assert from "node:assert/strict";
import test from "node:test";
import { withThreadHistoryTimeout } from "../src/lib/thread-history.ts";

test("thread history resolves normally before its timeout", async () => {
  assert.deepEqual(await withThreadHistoryTimeout(Promise.resolve(["thread-1"]), 20), ["thread-1"]);
});

test("thread history leaves loading state when LangGraph never responds", async () => {
  await assert.rejects(
    withThreadHistoryTimeout(new Promise<never>(() => {}), 5),
    /历史记录服务暂时不可用/,
  );
});
