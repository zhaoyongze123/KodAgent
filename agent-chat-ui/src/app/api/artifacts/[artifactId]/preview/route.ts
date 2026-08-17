import { NextRequest, NextResponse } from "next/server";

import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/**
 * 同源附件预览代理。Java 在每一次预览时重新校验附件归属、有效期和当前用户，
 * 此处只透传受控的只读 HTML，浏览器永远不会拿到 Java 服务凭证或存储路径。
 */
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ artifactId: string }> },
) {
  const { artifactId } = await params;
  if (!/^[0-9a-f-]{16,80}$/i.test(artifactId)) {
    return NextResponse.json({ error: "附件编号无效" }, { status: 400 });
  }
  const baseUrl = (
    process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080"
  ).replace(/\/$/, "");
  try {
    const upstream = await fetch(
      `${baseUrl}/agent/artifacts/${encodeURIComponent(artifactId)}/preview`,
      {
        headers: {
          ...(await getOaAgentHeaders("agent:artifact")),
          Accept: "text/html",
        },
        cache: "no-store",
      },
    );
    if (!upstream.ok) {
      return NextResponse.json(
        { error: "附件不存在、已过期、无权预览或暂不支持预览" },
        { status: upstream.status >= 400 ? upstream.status : 503 },
      );
    }
    const html = await upstream.text();
    return new NextResponse(html, {
      status: 200,
      headers: {
        "Cache-Control": "private, no-store, max-age=0",
        "Content-Type": "text/html; charset=utf-8",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "附件预览服务暂不可用" },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
