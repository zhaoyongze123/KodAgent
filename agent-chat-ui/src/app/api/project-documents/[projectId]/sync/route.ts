import { NextResponse } from "next/server";

import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/**
 * 项目资料索引的同源刷新代理。
 * 浏览器只携带当前 OA 会话，Java 仍会用 KodCloud 项目权限重新校验项目和文件。
 */
export async function POST(
  _request: Request,
  { params }: { params: Promise<{ projectId: string }> },
) {
  const { projectId } = await params;
  if (!/^\d+$/.test(projectId) || Number(projectId) <= 0) {
    return NextResponse.json({ error: "项目编号无效" }, { status: 400 });
  }
  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  try {
    const upstream = await fetch(
      `${baseUrl}/agent/tools/projects/${encodeURIComponent(projectId)}/documents/sync`,
      {
        method: "POST",
        headers: { ...(await getOaAgentHeaders("project:read")), Accept: "application/json" },
        cache: "no-store",
      },
    );
    const body = await upstream.json().catch(() => ({ error: "项目资料同步返回无效" }));
    return NextResponse.json(body, { status: upstream.status });
  } catch (error) {
    return NextResponse.json({ error: "项目资料同步服务暂不可用" }, { status: getOaAgentErrorStatus(error) });
  }
}
