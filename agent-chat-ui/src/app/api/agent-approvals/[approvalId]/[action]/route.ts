import { NextResponse } from "next/server";
import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

export const runtime = "nodejs";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ approvalId: string; action: string }> },
) {
  const { approvalId, action } = await params;
  if (action !== "approve" && action !== "reject") {
    return NextResponse.json(
      { error: "Unsupported approval action" },
      { status: 400 },
    );
  }

  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  const apiKey = process.env.OA_AGENT_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "OA_AGENT_API_KEY is not configured" },
      { status: 503 },
    );
  }

  const body = await request.text();
  try {
    const agentHeaders = await getOaAgentHeaders("approval:write");
    const response = await fetch(
      `${baseUrl}/agent/approvals/${encodeURIComponent(approvalId)}/${action}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...agentHeaders,
        },
        body,
        cache: "no-store",
      },
    );
    const responseBody = await response.text();
    return new NextResponse(responseBody, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Agent approval service is unavailable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
