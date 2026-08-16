import { NextRequest, NextResponse } from "next/server";

import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/**
 * 项目报告的同源字节代理。
 * 浏览器只拿到短期报告文件，Java 仍按当前 OA 用户、租户和 owner 再次校验。
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ reportId: string }> },
) {
  const { reportId } = await params;
  if (!/^[0-9a-f-]{16,80}$/i.test(reportId)) {
    return NextResponse.json({ error: "项目报告编号无效" }, { status: 400 });
  }
  const format = request.nextUrl.searchParams.get("format")?.toLowerCase() === "xlsx" ? "xlsx" : "docx";
  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  try {
    const upstream = await fetch(
      `${baseUrl}/agent/tools/projects/reports/${encodeURIComponent(reportId)}/download?format=${format}`,
      { headers: { ...(await getOaAgentHeaders("project:read")), Accept: "*/*" }, cache: "no-store" },
    );
    if (!upstream.ok) {
      return NextResponse.json({ error: "项目报告不存在、已过期或无权下载" }, { status: upstream.status >= 400 ? upstream.status : 503 });
    }
    const headers = new Headers({ "Cache-Control": "private, no-store, max-age=0", "X-Content-Type-Options": "nosniff" });
    for (const name of ["content-type", "content-disposition", "content-length"]) {
      const value = upstream.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new NextResponse(upstream.body, { status: 200, headers });
  } catch (error) {
    return NextResponse.json({ error: "项目报告服务暂不可用" }, { status: getOaAgentErrorStatus(error) });
  }
}
