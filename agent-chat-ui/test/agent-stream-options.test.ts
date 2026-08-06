import assert from "node:assert/strict";
import test from "node:test";
import {
  AGENT_STREAM_MODES,
  AGENT_SUBAGENT_STREAM_OPTIONS,
  AGENT_SUBAGENT_TOOL_NAMES,
  createAgentJoinStreamOptions,
  createAgentStreamOptions,
} from "../src/lib/agent-stream-options.ts";

test("agent stream factory enables namespaced custom events", () => {
  const options = createAgentStreamOptions({
    command: { resume: { decisions: [{ type: "approve" }] } },
  });

  assert.deepEqual(options.streamMode, ["custom", "messages-tuple"]);
  assert.equal(options.streamSubgraphs, true);
  assert.equal(options.streamResumable, true);
  assert.deepEqual(AGENT_SUBAGENT_TOOL_NAMES, ["task"]);
  assert.deepEqual(AGENT_SUBAGENT_STREAM_OPTIONS, {
    subagentToolNames: ["task"],
    filterSubagentMessages: true,
  });
  assert.equal(AGENT_STREAM_MODES.includes("values"), false);
  assert.equal(AGENT_STREAM_MODES.includes("updates"), false);
  assert.deepEqual(createAgentJoinStreamOptions(), {
    streamMode: ["custom", "messages-tuple"],
  });
});

test("subgraph custom events are enabled while native subagent messages remain isolated", () => {
  const options = createAgentStreamOptions();

  assert.equal(options.streamSubgraphs, true);
  assert.equal(AGENT_SUBAGENT_STREAM_OPTIONS.filterSubagentMessages, true);
});
