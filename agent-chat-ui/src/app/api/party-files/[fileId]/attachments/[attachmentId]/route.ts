import { NextRequest, NextResponse } from "next/server";

import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

export const runtime = "nodejs";

const POSITIVE_ID = /^[1-9]\d*$/;

function validId(value: string) {
  return POSITIVE_ID.test(value);
}

function upstreamFailureStatus(status: number) {
  if (status === 401 || status === 403 || status === 404) return status;
  return 503;
}

/**
 * A same-origin byte proxy for party-file attachments.  The page never sees
 * the server-only OA API key or identity ticket, and LangGraph never receives
 * the bytes. Java rechecks the user's audience visibility and confirms that
 * the attachment belongs to the requested party file on every request.
 */
export async function GET(
  request: NextRequest,
  {
    params,
  }: { params: Promise<{ fileId: string; attachmentId: string }> },
) {
  const { fileId, attachmentId } = await params;
  if (!validId(fileId) || !validId(attachmentId)) {
    return NextResponse.json({ error: "Invalid party file attachment" }, { status: 400 });
  }

  const action = request.nextUrl.searchParams.get("action") === "download"
    ? "download"
    : "preview";
  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  try {
    const agentHeaders = await getOaAgentHeaders("party-file:read");
    const query = new URLSearchParams({ id: fileId, fileId: attachmentId, action });
    const response = await fetch(
      `${baseUrl}/agent/tools/party-files/my-attachment/content?${query}`,
      {
        headers: { ...agentHeaders, Accept: "*/*" },
        cache: "no-store",
      },
    );

    if (!response.ok) {
      return NextResponse.json(
        { error: "党务文件附件不可用" },
        { status: upstreamFailureStatus(response.status) },
      );
    }

    const headers = new Headers({
      "Cache-Control": "private, no-store, max-age=0",
      "X-Content-Type-Options": "nosniff",
    });
    for (const header of ["content-type", "content-disposition", "content-length"]) {
      const value = response.headers.get(header);
      if (value) headers.set(header, value);
    }
    return new NextResponse(response.body, { status: 200, headers });
  } catch (error) {
    return NextResponse.json(
      { error: "党务文件附件服务暂不可用" },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
