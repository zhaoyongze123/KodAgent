import { NextResponse } from "next/server";
import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/** Persist a batch ApprovalCard decision; BPM execution stays in LangGraph HITL. */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ previewId: string; action: string }> },
) {
  const { previewId, action } = await params;
  if (!previewId.trim() || (action !== "approve" && action !== "reject")) {
    return NextResponse.json({ error: "Invalid batch approval action" }, { status: 400 });
  }
  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  try {
    const headers = await getOaAgentHeaders("approval:write");
    const response = await fetch(
      `${baseUrl}/agent/tools/approvals/batch/${encodeURIComponent(previewId)}/${action.toUpperCase()}`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json", ...headers },
        body: await request.text(),
        cache: "no-store",
      },
    );
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Batch approval service is unavailable", detail: error instanceof Error ? error.message : String(error) },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
