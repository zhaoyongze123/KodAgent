import type { StreamMode } from "@langchain/langgraph-sdk";

/**
 * Event kinds explicitly requested by KodAgent for both the main graph and
 * subgraphs. Namespace routing determines whether an event belongs to the
 * main Agent or a sub-agent.
 *
 * The SDK orchestrator always adds the main-graph `values` and `updates`
 * modes to every submit. We intentionally do not add them here: the SDK will
 * provide those two modes, while this factory adds the application-owned
 * custom process events and token stream.
 */
export const AGENT_STREAM_MODES: StreamMode[] = ["custom", "messages-tuple"];

export const AGENT_SUBAGENT_TOOL_NAMES = ["task"] as const;

export const AGENT_SUBAGENT_STREAM_OPTIONS = {
  subagentToolNames: [...AGENT_SUBAGENT_TOOL_NAMES],
  filterSubagentMessages: true,
};

export type AgentStreamOptions = {
  streamMode: StreamMode[];
  streamSubgraphs: true;
  streamResumable: true;
};

export type AgentJoinStreamOptions = {
  streamMode: StreamMode[];
};

/**
 * One submit configuration for new turns, regenerate, edit/retry, HITL resume
 * and inbox actions. The invariant fields are applied last so callers cannot
 * accidentally re-enable subgraph snapshots in one path.
 */
export function createAgentStreamOptions<
  T extends Record<string, unknown> = Record<string, never>,
>(options?: T): T & AgentStreamOptions {
  return {
    ...(options ?? ({} as T)),
    streamMode: AGENT_STREAM_MODES.slice(),
    // Subgraph custom events contain the business progress timeline. The SDK
    // still keeps sub-agent messages/values out of the main conversation via
    // AGENT_SUBAGENT_STREAM_OPTIONS.filterSubagentMessages.
    streamSubgraphs: true,
    streamResumable: true,
  } as T & AgentStreamOptions;
}

/** Rejoin inherits the modes of the original run; streamSubgraphs belongs to creation. */
export function createAgentJoinStreamOptions(): AgentJoinStreamOptions {
  return { streamMode: AGENT_STREAM_MODES.slice() };
}
