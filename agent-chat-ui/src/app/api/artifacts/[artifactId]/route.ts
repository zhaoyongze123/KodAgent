import { NextRequest, NextResponse } from "next/server";

import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/** 同源附件下载代理；Java 仍按当前用户、租户与到期时间重新授权。 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ artifactId: string }> },
) {
  const { artifactId } = await params;
  if (!/^[0-9a-f-]{16,80}$/i.test(artifactId)) {
    return NextResponse.json({ error: "附件编号无效" }, { status: 400 });
  }
  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  try {
    const upstream = await fetch(
      `${baseUrl}/agent/artifacts/${encodeURIComponent(artifactId)}/download`,
      { headers: { ...(await getOaAgentHeaders("agent:artifact")), Accept: "*/*" }, cache: "no-store" },
    );
    if (!upstream.ok) {
      return NextResponse.json({ error: "附件不存在、已过期或无权下载" }, { status: upstream.status >= 400 ? upstream.status : 503 });
    }
    const headers = new Headers({ "Cache-Control": "private, no-store, max-age=0", "X-Content-Type-Options": "nosniff" });
    for (const name of ["content-type", "content-disposition", "content-length"]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new NextResponse(upstream.body, { status: 200, headers });
  } catch (error) {
    return NextResponse.json({ error: "附件服务暂不可用" }, { status: getOaAgentErrorStatus(error) });
  }
}
