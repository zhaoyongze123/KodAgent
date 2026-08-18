import { NextResponse } from "next/server";
import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/**
 * A user click is the confirmation boundary for a BPM task action.  The
 * browser never receives the OA service key or identity ticket; Java still
 * validates that this task is currently assigned to the signed-in user.
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ taskId: string; action: string }> },
) {
  const { taskId, action } = await params;
  if (action !== "approve" && action !== "reject") {
    return NextResponse.json({ error: "Unsupported task action" }, { status: 400 });
  }
  const rawBody = await request.text();
  let reason = "";
  try {
    const body = rawBody ? JSON.parse(rawBody) : {};
    reason = typeof body?.reason === "string" ? body.reason.trim() : "";
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }
  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  try {
    const response = await fetch(`${baseUrl}/agent/tools/tasks/${action}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...(await getOaAgentHeaders("approval:write")),
      },
      body: JSON.stringify({
        taskId,
        reason,
      }),
      cache: "no-store",
    });
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Agent task service is unavailable", detail: error instanceof Error ? error.message : String(error) },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
