import { NextResponse } from "next/server";

export const runtime = "nodejs";

const REQUEST_TIMEOUT_MS = 8_000;

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  // Next.js 在部分开发代理环境中会把 request.url 规范化为 localhost；
  // 这里优先使用外部 Host，确保换票后回到用户实际打开的域名。
  const forwardedHost = request.headers.get("x-forwarded-host") ?? request.headers.get("host");
  const forwardedProto = request.headers.get("x-forwarded-proto") ?? requestUrl.protocol.replace(":", "");
  const appOrigin = forwardedHost ? `${forwardedProto}://${forwardedHost}` : requestUrl.origin;
  const redirectPath = requestUrl.searchParams.get("redirectPath");
  if (!redirectPath) {
    return NextResponse.json({ error: "redirectPath is required" }, { status: 400 });
  }

  let target: URL;
  try {
    target = new URL(redirectPath, appOrigin);
  } catch {
    return NextResponse.json({ error: "redirectPath is invalid" }, { status: 400 });
  }
  // 只允许回到固定的 Agent SSO 页面，避免把换票结果导向任意地址。
  if (target.origin !== appOrigin || target.pathname !== "/auth/kod-sso") {
    return NextResponse.json({ error: "redirectPath is not allowed" }, { status: 400 });
  }

  const baseUrl = (process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080").replace(/\/$/, "");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(
      `${baseUrl}/admin-api/system/auth/kod-sso/start?redirectUri=${encodeURIComponent(target.toString())}`,
      { redirect: "manual", cache: "no-store", signal: controller.signal },
    );
    const location = response.headers.get("location");
    if (!location) {
      return NextResponse.json(
        { error: "可道云登录启动失败", detail: `Java SSO 返回 ${response.status}` },
        { status: 502 },
      );
    }
    return NextResponse.json({ redirectUrl: location });
  } catch (error) {
    const message = error instanceof Error && error.name === "AbortError"
      ? "可道云登录服务连接超时"
      : error instanceof Error ? error.message : String(error);
    return NextResponse.json({ error: message }, { status: 503 });
  } finally {
    clearTimeout(timeout);
  }
}
