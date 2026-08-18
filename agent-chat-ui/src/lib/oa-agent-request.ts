import { cookies } from "next/headers";

export class AgentIdentitySessionError extends Error {
  constructor() {
    super("Agent identity session is missing or expired");
    this.name = "AgentIdentitySessionError";
  }
}

export function getOaAgentErrorStatus(error: unknown): number {
  return error instanceof AgentIdentitySessionError ? 401 : 503;
}

export async function getOaAgentHeaders(
  permission: "agent:audit" | "knowledge:manage" | string = "agent:audit",
): Promise<Record<string, string>> {
  const apiKey = process.env.OA_AGENT_API_KEY;
  if (!apiKey) {
    throw new Error("OA_AGENT_API_KEY is not configured on the server");
  }

  const cookieStore = await cookies();
  const identity = cookieStore.get("oa_agent_identity")?.value;
  if (!identity) {
    throw new AgentIdentitySessionError();
  }
  return {
    Accept: "application/json",
    // Agent identity is tenant-scoped. The session endpoint already sends
    // this header; all proxied business requests must carry it as well.
    "tenant-id": process.env.OA_AGENT_TENANT_ID ?? "1",
    "X-Agent-Key": apiKey,
    "X-Agent-Identity": identity,
    "X-Agent-Permission": permission,
  };
}
