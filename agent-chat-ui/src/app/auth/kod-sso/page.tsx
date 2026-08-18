import { Suspense } from "react";

import KodSsoAgentClient from "./kod-sso-agent-client";

export default function KodSsoAgentPage() {
  return (
    <Suspense
      fallback={
        <main className="flex min-h-screen items-center justify-center p-8">
          <div className="max-w-sm text-center text-sm text-muted-foreground">
            <p>正在完成可道云登录……</p>
            <p className="mt-2 text-xs text-muted-foreground/70">
              前端刚刚重启，正在预热登录页面，通常需要约 30～40 秒，请稍候。
            </p>
          </div>
        </main>
      }
    >
      <KodSsoAgentClient />
    </Suspense>
  );
}
