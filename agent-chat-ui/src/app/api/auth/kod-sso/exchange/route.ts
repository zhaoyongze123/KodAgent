import { NextResponse } from "next/server";

export const runtime = "nodejs";

const REQUEST_TIMEOUT_MS = 10_000;

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const code = typeof body.code === "string" ? body.code : "";
  if (!code) {
    return NextResponse.json({ error: "kodSsoCode is required" }, { status: 400 });
  }

  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const loginResponse = await fetch(
      `${baseUrl}/admin-api/system/auth/kod-sso/exchange?code=${encodeURIComponent(code)}`,
      { method: "POST", cache: "no-store", signal: controller.signal },
    );
    const loginBody = await loginResponse.json();
    const login = loginBody?.data;
    if (!loginResponse.ok || loginBody?.code !== 0 || !login?.accessToken) {
      return NextResponse.json(
        { error: loginBody?.msg ?? "KodBox SSO exchange failed" },
        { status: loginResponse.ok ? 401 : loginResponse.status },
      );
    }

    const ticketResponse = await fetch(`${baseUrl}/admin-api/agent/identity/ticket`, {
      method: "POST",
      headers: { Authorization: `Bearer ${login.accessToken}` },
      cache: "no-store",
      signal: controller.signal,
    });
    const ticketBody = await ticketResponse.json();
    const ticket = ticketBody?.data?.ticket;
    if (!ticketResponse.ok || ticketBody?.code !== 0 || !ticket) {
      return NextResponse.json(
        { error: ticketBody?.msg ?? "Agent identity ticket failed" },
        { status: ticketResponse.ok ? 401 : ticketResponse.status },
      );
    }

    const response = NextResponse.json({ ok: true });
    response.cookies.set("oa_agent_identity", ticket, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      maxAge: Number(ticketBody?.data?.expiresIn ?? 7200),
    });
    return response;
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error && error.name === "AbortError" ? "可道云登录服务连接超时" : error instanceof Error ? error.message : String(error) },
      { status: 503 },
    );
  } finally {
    clearTimeout(timeout);
  }
}
