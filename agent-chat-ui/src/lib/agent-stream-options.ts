import type { StreamMode } from "@langchain/langgraph-sdk";

/**
 * Event kinds explicitly requested by KodAgent for the main graph.
 *
 * The SDK orchestrator always adds the main-graph `values` and `updates`
 * modes to every submit. We intentionally do not add them here: the SDK will
 * provide those two modes, while this factory adds the application-owned
 * custom process events.
 *
 * Request `messages-tuple` so the final main-agent answer can be rendered as it
 * is generated. The UI still reads durable custom events for summaries and
 * tool lifecycle; raw child-agent subgraphs remain disabled below.
 */
export const AGENT_STREAM_MODES: StreamMode[] = ["custom", "messages-tuple"];

export type AgentStreamOptions = {
  streamMode: StreamMode[];
  streamSubgraphs: false;
  streamResumable: true;
};

export type AgentJoinStreamOptions = {
  streamMode: StreamMode[];
};

/**
 * One submit configuration for new turns, regenerate, edit/retry, HITL resume
 * and inbox actions. The invariant fields are applied last so callers cannot
 * accidentally re-enable the high-volume subgraph state stream in one path.
 */
export function createAgentStreamOptions<
  T extends Record<string, unknown> = Record<string, never>,
>(options?: T): T & AgentStreamOptions {
  return {
    ...(options ?? ({} as T)),
    streamMode: AGENT_STREAM_MODES.slice(),
    // Browser process rows are read from the Java durable event stream. The
    // LangGraph SDK forces values/updates for its own state handling; turning
    // on subgraph streaming would duplicate every child Agent state snapshot
    // and raw tool result in the browser response without adding a new fact.
    streamSubgraphs: false,
    streamResumable: true,
  } as T & AgentStreamOptions;
}

/** Rejoin inherits the modes of the original run; streamSubgraphs belongs to creation. */
export function createAgentJoinStreamOptions(): AgentJoinStreamOptions {
  return { streamMode: AGENT_STREAM_MODES.slice() };
}
