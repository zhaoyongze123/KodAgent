import { NextResponse } from "next/server";
import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params;
  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  const requestUrl = new URL(request.url);
  const query = new URLSearchParams();
  for (const name of ["afterCursor", "afterEventTime", "afterEventId", "limit"]) {
    const value = requestUrl.searchParams.get(name);
    if (value) query.set(name, value);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  let response: Response;
  try {
    // 读取当前用户自己的过程进度，不需要管理员审计权限。
    const agentHeaders = await getOaAgentHeaders("agent:progress");
    response = await fetch(
      `${baseUrl}/agent/threads/${encodeURIComponent(threadId)}/events${suffix}`,
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
