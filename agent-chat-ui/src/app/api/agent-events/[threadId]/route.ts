import { NextResponse } from "next/server";
import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params;
  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  let response: Response;
  try {
    const agentHeaders = await getOaAgentHeaders("agent:audit");
    response = await fetch(
      `${baseUrl}/agent/threads/${encodeURIComponent(threadId)}/events`,
      {
        headers: {
          Accept: "application/json",
          ...agentHeaders,
        },
        cache: "no-store",
      },
    );
  } catch (error) {
    return NextResponse.json(
      {
        error: "Agent event service is unavailable",
        detail: error instanceof Error ? error.message : String(error),
      },
      {
        status: getOaAgentErrorStatus(error),
        headers: { "Cache-Control": "no-store, max-age=0" },
      },
    );
  }

  const body = await response.text();
  return new NextResponse(body, {
    status: response.status,
    headers: {
      "Content-Type":
        response.headers.get("Content-Type") ?? "application/json",
      "Cache-Control": "no-store, max-age=0",
    },
  });
}
