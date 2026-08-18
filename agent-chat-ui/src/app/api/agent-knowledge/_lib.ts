import { NextResponse } from "next/server";

import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";
import { knowledgeManagementPermission } from "@/lib/knowledge-source";

const baseUrl = () =>
  (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");

export async function proxyKnowledgeRequest(
  request: Request,
  path: string,
  init: RequestInit = {},
) {
  try {
    const headers = await getOaAgentHeaders(knowledgeManagementPermission);
    const response = await fetch(`${baseUrl()}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...headers,
        ...(init.headers ?? {}),
      },
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
      {
        error: "知识库管理服务暂不可用",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
