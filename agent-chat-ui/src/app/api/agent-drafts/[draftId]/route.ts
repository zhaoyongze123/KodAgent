import { NextResponse } from "next/server";
import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ draftId: string }> },
) {
  const { draftId } = await params;
  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  try {
    const agentHeaders = await getOaAgentHeaders("meeting:read");
    const response = await fetch(
      `${baseUrl}/agent/drafts/meeting-booking/${encodeURIComponent(draftId)}`,
      {
        headers: {
          Accept: "application/json",
          ...agentHeaders,
        },
        cache: "no-store",
      },
    );
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store, max-age=0",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Agent draft service is unavailable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
