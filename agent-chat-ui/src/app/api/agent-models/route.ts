import { NextResponse } from "next/server";
import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

export async function GET() {
  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  try {
    const response = await fetch(`${baseUrl}/agent/config/models`, {
      headers: { Accept: "application/json", ...(await getOaAgentHeaders("model:read")) },
      cache: "no-store",
    });
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store, max-age=0",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Agent model service is unavailable", detail: error instanceof Error ? error.message : String(error) },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
