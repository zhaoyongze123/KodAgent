import { NextResponse } from "next/server";

import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/** 转发当前登录用户的真实 Agent 运行统计，浏览器不直接接触 Java 凭据。 */
export async function GET(request: Request) {
  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  const url = new URL(request.url);
  const requestedDays = url.searchParams.get("days") ?? "14";
  const granularity = url.searchParams.get("granularity") ?? "day";
  try {
    const headers = await getOaAgentHeaders("agent:analytics:read");
    const response = await fetch(
      `${baseUrl}/agent/runs/analytics/overview?days=${encodeURIComponent(requestedDays)}&granularity=${encodeURIComponent(granularity)}`,
      { headers, cache: "no-store" },
    );
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") ?? "application/json",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Agent analytics service is unavailable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
