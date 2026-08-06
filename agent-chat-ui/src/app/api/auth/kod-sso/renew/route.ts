import { NextResponse } from "next/server";
import { cookies } from "next/headers";

export const runtime = "nodejs";

const REQUEST_TIMEOUT_MS = 8_000;

export async function POST() {
  const identity = (await cookies()).get("oa_agent_identity")?.value;
  const apiKey = process.env.OA_AGENT_API_KEY;
  if (!identity || !apiKey) {
    return NextResponse.json(
      { error: "Agent identity session is missing or expired" },
      { status: 401 },
    );
  }

  const baseUrl = (
    process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080"
  ).replace(/\/$/, "");
  const tenantId = process.env.OA_AGENT_TENANT_ID ?? "1";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  try {
    const response = await fetch(`${baseUrl}/admin-api/agent/identity/renew`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "tenant-id": tenantId,
        "X-Agent-Key": apiKey,
        "X-Agent-Identity": identity,
      },
      cache: "no-store",
      signal: controller.signal,
    });
    const body = await response.json().catch(() => ({}));
    const ticket = body?.data?.ticket;
    if (!response.ok || body?.code !== 0 || typeof ticket !== "string") {
      const result = NextResponse.json(
        { error: body?.msg ?? "Agent identity renewal failed" },
        { status: response.status === 200 ? 401 : response.status },
      );
      if (response.status === 401 || body?.code === 401) {
        result.cookies.delete("oa_agent_identity");
      }
      return result;
    }

    const responseBody = NextResponse.json({
      authenticated: true,
      expiresAt: body.data.expiresAt,
    });
    responseBody.cookies.set("oa_agent_identity", ticket, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: Number(body.data.expiresIn ?? 7200),
    });
    return responseBody;
  } catch (error) {
    return NextResponse.json(
      {
        error:
          error instanceof Error && error.name === "AbortError"
            ? "Agent identity renewal timed out"
            : error instanceof Error
              ? error.message
              : String(error),
      },
      { status: 503 },
    );
  } finally {
    clearTimeout(timeout);
  }
}
