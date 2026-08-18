import { NextResponse } from "next/server";

export const runtime = "nodejs";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ threadId: string }> },
) {
  const { threadId } = await params;
  // This route is server-side. It must call LangGraph directly rather than
  // using NEXT_PUBLIC_API_URL (which deliberately points back to the Next.js
  // proxy on port 3000). LangGraph itself remains the private 2024 upstream.
  const baseUrl = process.env.LANGGRAPH_API_URL ?? "http://127.0.0.1:2024";
  const apiKey = process.env.LANGSMITH_API_KEY;
  const identity = request.headers
    .get("cookie")
    ?.split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith("oa_agent_identity="))
    ?.slice("oa_agent_identity=".length);

  try {
    const response = await fetch(
      `${baseUrl.replace(/\/$/, "")}/threads/${encodeURIComponent(threadId)}/state`,
      {
        headers: {
          Accept: "application/json",
          ...(apiKey ? { "x-api-key": apiKey } : {}),
          ...(identity
            ? { "X-Agent-Identity": decodeURIComponent(identity) }
            : {}),
        },
        cache: "no-store",
      },
    );
    const body = await response.text();
    return new NextResponse(body, {
      status: response.status,
      headers: {
        "Content-Type":
          response.headers.get("Content-Type") ?? "application/json",
        "Cache-Control": "no-store, max-age=0",
      },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: "LangGraph state service is unavailable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: 503 },
    );
  }
}
