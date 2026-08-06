import { NextResponse } from "next/server";
import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ runId: string }> },
) {
  const { runId } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  try {
    const headers = await getOaAgentHeaders("agent:audit");
    const response = await fetch(
      `${baseUrl}/agent/runs/${encodeURIComponent(runId)}/metrics`,
      {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(body),
        cache: "no-store",
      },
    );
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Agent telemetry service is unavailable", detail: error instanceof Error ? error.message : String(error) },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
