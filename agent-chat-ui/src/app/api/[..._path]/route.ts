import { initApiPassthrough } from "langgraph-nextjs-api-passthrough";
import { NextRequest, NextResponse } from "next/server";

const now = () => performance.now();

function traceId(request: NextRequest): string {
  return request.headers.get("x-kodagent-trace-id") ?? crypto.randomUUID();
}

function logTrace(
  phase: string,
  request: NextRequest,
  trace: string,
  startedAt: number,
  extra: Record<string, unknown> = {},
) {
  console.info(
    JSON.stringify({
      source: "kodagent.next.proxy",
      traceId: trace,
      phase,
      method: request.method,
      path: request.nextUrl.pathname,
      elapsedMs: Math.round(now() - startedAt),
      ...extra,
    }),
  );
}

function withTrace(
  handler: (request: NextRequest) => Promise<NextResponse<unknown>>,
  method: string,
) {
  return async (request: NextRequest) => {
    const startedAt = now();
    const trace = traceId(request);
    logTrace("proxy.received", request, trace, startedAt);
    try {
      const response = await handler(request);
      const output = new NextResponse(response.body, response);
      output.headers.set("X-KodAgent-Trace-Id", trace);
      output.headers.set(
        "Server-Timing",
        `kodagent-proxy;dur=${Math.round(now() - startedAt)}`,
      );
      logTrace("proxy.upstream-response", request, trace, startedAt, {
        status: response.status,
        handler: method,
      });
      return output;
    } catch (error) {
      logTrace("proxy.failed", request, trace, startedAt, {
        error: error instanceof Error ? error.message : String(error),
      });
      throw error;
    }
  };
}

// This file acts as a proxy for requests to your LangGraph server.
// Read the [Going to Production](https://github.com/langchain-ai/agent-chat-ui?tab=readme-ov-file#going-to-production) section for more information.

const passthrough = initApiPassthrough({
  // NEXT_PUBLIC_API_URL is deliberately the local Agent UI proxy (3000/api),
  // not this upstream. Keeping the target server-only lets this route forward
  // the HttpOnly OA identity ticket as X-Agent-Identity.
  apiUrl: process.env.LANGGRAPH_API_URL ?? "http://127.0.0.1:2024",
  apiKey: "",
  runtime: "nodejs",
  headers: (request) => {
    const identity = request.cookies.get("oa_agent_identity")?.value;
    const headers: Record<string, string> = {};
    if (identity) headers["X-Agent-Identity"] = identity;
    console.info(
      JSON.stringify({
        source: "kodagent.next.proxy",
        traceId: traceId(request),
        phase: "proxy.auth-prepared",
        identityPresent: Boolean(identity),
      }),
    );
    return headers;
  },
  disableWarningLog: true,
});

export const GET = withTrace(passthrough.GET, "GET");
export const POST = withTrace(passthrough.POST, "POST");
export const PUT = withTrace(passthrough.PUT, "PUT");
export const PATCH = withTrace(passthrough.PATCH, "PATCH");
export const DELETE = withTrace(passthrough.DELETE, "DELETE");
export const OPTIONS = passthrough.OPTIONS;
export const runtime = "nodejs";
