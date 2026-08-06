import { NextResponse } from "next/server";

import { cookies } from "next/headers";

export const runtime = "nodejs";

const REQUEST_TIMEOUT_MS = 8_000;

export async function GET() {
  const identity = (await cookies()).get("oa_agent_identity")?.value;
  const apiKey = process.env.OA_AGENT_API_KEY;
  if (!identity || !apiKey) {
    return NextResponse.json({ authenticated: false }, { status: 401 });
  }

  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  const tenantId = process.env.OA_AGENT_TENANT_ID ?? "1";
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${baseUrl}/admin-api/agent/identity/session`, {
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
    if (response.status >= 500) {
      return NextResponse.json({ authenticated: false }, { status: 503 });
    }
    if (!response.ok || body?.code !== 0 || body?.data?.authenticated !== true) {
      const result = NextResponse.json({ authenticated: false }, { status: 401 });
      result.cookies.delete("oa_agent_identity");
      return result;
    }
    return NextResponse.json({ authenticated: true, expiresAt: body.data.expiresAt });
  } catch {
    return NextResponse.json({ authenticated: false }, { status: 503 });
  } finally {
    clearTimeout(timeout);
  }
}
