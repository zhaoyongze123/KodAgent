import assert from "node:assert/strict";
import test from "node:test";
import { CLIENT_RUN_COMPLETION_DISABLED } from "../src/lib/client-run-completion.ts";

test("client run completion contract is disabled and cannot write a lifecycle fact", () => {
  assert.deepEqual(CLIENT_RUN_COMPLETION_DISABLED, {
    error: "CLIENT_RUN_COMPLETION_DISABLED",
    detail: "Run completion is recorded by the backend.",
  });
});
