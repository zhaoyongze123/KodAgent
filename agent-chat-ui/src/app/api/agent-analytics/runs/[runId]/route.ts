import { NextResponse } from "next/server";

import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/** 转发单次 Run 的安全追踪，Java 侧只返回 allowlist 阶段字段。 */
export async function GET(
  _request: Request,
  context: { params: Promise<{ runId: string }> },
) {
  const { runId } = await context.params;
  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  try {
    const response = await fetch(
      `${baseUrl}/agent/runs/analytics/runs/${encodeURIComponent(runId)}`,
      {
        headers: await getOaAgentHeaders("agent:analytics:read"),
        cache: "no-store",
      },
    );
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Agent analytics service is unavailable" },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
