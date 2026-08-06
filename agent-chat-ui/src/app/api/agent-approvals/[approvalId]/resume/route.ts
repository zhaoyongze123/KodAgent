import { NextResponse } from "next/server";
import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/**
 * Records the durable fact that an already-approved LangGraph run was
 * resumed.  The LangGraph submit itself is intentionally performed by the
 * client SDK first; this endpoint only records the audit fact and must never
 * resume the graph a second time.
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ approvalId: string }> },
) {
  const { approvalId } = await params;
  if (!approvalId.trim() || approvalId.length > 128) {
    return NextResponse.json({ error: "Invalid approval id" }, { status: 400 });
  }

  let input: unknown;
  try {
    input = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }
  const resumeIdempotencyKey =
    input && typeof input === "object" && "resumeIdempotencyKey" in input
      ? (input as { resumeIdempotencyKey?: unknown }).resumeIdempotencyKey
      : undefined;
  if (
    typeof resumeIdempotencyKey !== "string" ||
    !resumeIdempotencyKey.trim() ||
    resumeIdempotencyKey.length > 128
  ) {
    return NextResponse.json(
      { error: "resumeIdempotencyKey is required" },
      { status: 400 },
    );
  }

  const baseUrl = (
    process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080"
  ).replace(/\/$/, "");
  try {
    const agentHeaders = await getOaAgentHeaders("approval:write");
    const response = await fetch(
      `${baseUrl}/agent/approvals/${encodeURIComponent(approvalId)}/resume`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
          ...agentHeaders,
        },
        // Do not forward arbitrary client fields to the approval service.
        body: JSON.stringify({ idempotencyKey: resumeIdempotencyKey.trim() }),
        cache: "no-store",
      },
    );
    const responseBody = await response.text();
    return new NextResponse(responseBody || null, {
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
        error: "Agent approval resume audit service is unavailable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
