"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export default function KodSsoAgentClient() {
  const params = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("正在完成可道云登录……");
  const [showWarmupHint, setShowWarmupHint] = useState(true);
  const [retryCount, setRetryCount] = useState(0);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) {
      return;
    }
    startedRef.current = true;

    const targetAfterLogin = () => {
      const redirectPath = params.get("redirectPath");
      return redirectPath &&
        redirectPath.startsWith("/") &&
        !redirectPath.startsWith("//")
        ? redirectPath
        : "/";
    };

    const requestWithTimeout = async (
      input: RequestInfo | URL,
      init: RequestInit = {},
      timeoutMs = 10_000,
    ) => {
      const controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
      try {
        return await fetch(input, { ...init, signal: controller.signal });
      } finally {
        window.clearTimeout(timeout);
      }
    };

    const restartKodSso = async () => {
      setError(null);
      setStatus("登录状态已过期，正在重新连接可道云……");
      const redirectUri = new URL(window.location.href);
      // 一次性换票码只能使用一次；重新登录时必须带干净的回跳地址。
      redirectUri.searchParams.delete("kodSsoCode");
      redirectUri.searchParams.delete("error");
      const startResponse = await requestWithTimeout(
        `/api/auth/kod-sso/start?redirectPath=${encodeURIComponent(`${redirectUri.pathname}${redirectUri.search}`)}`,
        { cache: "no-store" },
        10_000,
      );
      const startBody = await startResponse.json().catch(() => ({}));
      if (!startResponse.ok || typeof startBody.redirectUrl !== "string") {
        throw new Error(startBody.error ?? "无法启动可道云登录");
      }
      window.location.replace(startBody.redirectUrl);
    };

    const retryAllowed = () => {
      const lastAttemptAt = Number(
        window.sessionStorage.getItem("kodagent_sso_attempt_at") ?? "0",
      );
      if (Date.now() - lastAttemptAt < 30_000) return false;
      window.sessionStorage.setItem(
        "kodagent_sso_attempt_at",
        String(Date.now()),
      );
      return true;
    };

    const run = async () => {
      const code = params.get("kodSsoCode");
      const sessionResponse = await requestWithTimeout(
        "/api/auth/kod-sso/session",
        { cache: "no-store" },
      );
      if (sessionResponse.ok) {
        router.replace(targetAfterLogin());
        return;
      }

      if (!code) {
        if (sessionResponse.status === 401) {
          if (!retryAllowed()) {
            throw new Error("登录凭证未能保存，请点击“重新登录”再试");
          }
          await restartKodSso();
          return;
        }
        const body = await sessionResponse.json().catch(() => ({}));
        throw new Error(body.error ?? "登录服务暂时不可用，请稍后重试");
      }

      setStatus("正在换取新的 Agent 登录凭证……");
      setShowWarmupHint(false);
      const response = await requestWithTimeout("/api/auth/kod-sso/exchange", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      if (!response.ok) {
        // 回跳码过期或已被使用时，直接重新走 SSO，不让用户停在旧地址。
        if (response.status === 401) {
          await restartKodSso();
          return;
        }
        const body = await response.json().catch(() => ({}));
        throw new Error(body.error ?? "可道云登录失败");
      }
      window.sessionStorage.removeItem("kodagent_sso_attempt_at");
      window.sessionStorage.removeItem("kodagent_sso_redirect_at");
      router.replace(targetAfterLogin());
    };

    void run().catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : String(reason));
    });
  }, [params, retryCount, router]);

  return (
    <main className="flex min-h-screen items-center justify-center p-8">
      <div className="text-muted-foreground max-w-sm text-center text-sm">
        <p>{error ?? status}</p>
        {!error && showWarmupHint ? (
          <p className="mt-2 text-xs text-muted-foreground/70">
            如果前端刚刚重启，系统正在预热页面，通常需要约 30～40 秒；预热完成后会自动继续登录。
          </p>
        ) : null}
        {error ? (
          <button
            type="button"
            className="hover:bg-muted mt-4 rounded-md border px-3 py-1.5 text-sm"
            onClick={() => {
              window.sessionStorage.removeItem("kodagent_sso_attempt_at");
              window.sessionStorage.removeItem("kodagent_sso_redirect_at");
              startedRef.current = false;
              setError(null);
              setRetryCount((count) => count + 1);
            }}
          >
            重新登录
          </button>
        ) : null}
      </div>
    </main>
  );
}
