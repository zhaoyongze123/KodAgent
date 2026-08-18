"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

const FALLBACK_CHECK_MS = 5 * 60 * 1000;
const RENEW_AHEAD_MS = 60 * 1000;

function loginUrl() {
  const currentPath = `${window.location.pathname}${window.location.search}`;
  const params = new URLSearchParams({
    tenantId: "1",
    redirectPath: currentPath,
  });
  return `/auth/kod-sso?${params.toString()}`;
}

export default function AgentSessionKeeper() {
  const pathname = usePathname();

  useEffect(() => {
    // The SSO page owns the initial exchange. Running the keeper there would
    // create a redirect loop while the one-time kodSsoCode is being consumed.
    if (pathname === "/auth/kod-sso") {
      return;
    }

    let disposed = false;
    let timer: number | undefined;
    let checking = false;

    const schedule = (expiresAt?: number) => {
      if (disposed) return;
      const expiryDelay = expiresAt
        ? expiresAt * 1000 - Date.now() - RENEW_AHEAD_MS
        : FALLBACK_CHECK_MS;
      const delay = Math.max(10_000, Math.min(expiryDelay, FALLBACK_CHECK_MS));
      timer = window.setTimeout(() => void checkSession(), delay);
    };

    const redirectToLogin = () => {
      if (disposed) return;
      const lastRedirectAt = Number(
        window.sessionStorage.getItem("kodagent_sso_redirect_at") ?? "0",
      );
      // Do not create a redirect storm when the browser cannot persist the
      // returned ticket (for example while an embedded plugin is recovering).
      // The SSO page exposes a manual retry after this cooldown.
      if (Date.now() - lastRedirectAt < 30_000) return;
      window.sessionStorage.setItem(
        "kodagent_sso_redirect_at",
        String(Date.now()),
      );
      window.location.replace(loginUrl());
    };

    const checkSession = async () => {
      if (disposed || checking) return;
      checking = true;
      try {
        const sessionResponse = await fetch("/api/auth/kod-sso/session", {
          cache: "no-store",
        });
        const sessionBody = await sessionResponse.json().catch(() => ({}));
        if (sessionResponse.ok && sessionBody?.authenticated === true) {
          const expiresAt = Number(sessionBody.expiresAt);
          const renewalDelay = Number.isFinite(expiresAt)
            ? expiresAt
            : undefined;
          const now = Math.floor(Date.now() / 1000);
          if (renewalDelay && renewalDelay - now <= 60) {
            const renewResponse = await fetch("/api/auth/kod-sso/renew", {
              method: "POST",
              cache: "no-store",
            });
            const renewBody = await renewResponse.json().catch(() => ({}));
            if (renewResponse.ok && renewBody?.authenticated === true) {
              schedule(Number(renewBody.expiresAt));
              return;
            }
            if (renewResponse.status === 401) {
              redirectToLogin();
              return;
            }
            schedule();
            return;
          }
          schedule(renewalDelay);
          return;
        }
        if (sessionResponse.status === 401) {
          redirectToLogin();
          return;
        }
        // A temporary Java/Redis/network failure must not log the user out.
        schedule();
      } catch {
        schedule();
      } finally {
        checking = false;
      }
    };

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void checkSession();
      }
    };

    document.addEventListener("visibilitychange", onVisibilityChange);
    void checkSession();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [pathname]);

  return null;
}
