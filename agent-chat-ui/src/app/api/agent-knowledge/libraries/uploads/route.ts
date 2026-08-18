import { NextResponse } from "next/server";

import { getOaAgentErrorStatus, getOaAgentHeaders } from "@/lib/oa-agent-request";
import { knowledgeManagementPermission } from "@/lib/knowledge-source";

const baseUrl = () =>
  (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");

export const runtime = "nodejs";

export async function POST(request: Request) {
  try {
    const form = await request.formData();
    const response = await fetch(`${baseUrl()}/admin-api/agent/knowledge-libraries/uploads`, {
      method: "POST",
      headers: { Accept: "application/json", ...(await getOaAgentHeaders(knowledgeManagementPermission)) },
      // Do not manually set Content-Type. Fetch adds the multipart boundary for FormData.
      body: form,
      cache: "no-store",
    });
    return new NextResponse(response.body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store, max-age=0",
      },
    });
  } catch (error) {
    return NextResponse.json(
      { error: "本地资料上传服务暂不可用", detail: error instanceof Error ? error.message : String(error) },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
