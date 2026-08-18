import { NextResponse } from "next/server";
import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

const baseUrl = () =>
  (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");

export async function proxyAgentRequest(
  request: Request,
  path: string,
  permission: "model:read" | "model:manage",
  init: RequestInit = {},
) {
  try {
    const headers = await getOaAgentHeaders(permission);
    const response = await fetch(`${baseUrl()}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...headers,
        ...(init.headers ?? {}),
      },
      cache: "no-store",
    });
    const body = await response.text();
    let businessCode: unknown = undefined;
    let businessMessage: unknown = undefined;
    try {
      const parsed = JSON.parse(body) as { code?: unknown; msg?: unknown; message?: unknown };
      businessCode = parsed.code;
      businessMessage = parsed.msg ?? parsed.message;
    } catch {
      // Keep non-JSON upstream responses unchanged.
    }
    console.info(
      JSON.stringify({
        source: "kodagent.next.agent-settings",
        path,
        httpStatus: response.status,
        businessCode,
        businessMessage,
      }),
    );
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store, max-age=0",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "Agent model service is unavailable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}

export async function readJsonBody(request: Request) {
  try {
    return await request.json();
  } catch {
    return {};
  }
}
