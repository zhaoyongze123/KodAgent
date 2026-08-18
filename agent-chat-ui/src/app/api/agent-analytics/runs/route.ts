import { NextResponse } from "next/server";

import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/** 转发管理员运行列表筛选，浏览器不直接持有 Java 身份票据。 */
export async function GET(request: Request) {
  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  const query = new URL(request.url).searchParams;
  const target = new URL(`${baseUrl}/agent/runs/analytics/runs`);
  for (const name of ["days", "status", "domain", "pageNo", "pageSize"]) {
    const value = query.get(name);
    if (value) target.searchParams.set(name, value);
  }
  try {
    const response = await fetch(target, {
      headers: await getOaAgentHeaders("agent:analytics:read"),
      cache: "no-store",
    });
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
