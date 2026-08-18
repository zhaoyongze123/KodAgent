import { type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import { useSessionBootstrap } from '@/features/auth/hooks/use-session-bootstrap';
import { useSessionStore } from '@/features/auth/store/session-store';

interface AuthGateProps {
  children: ReactNode;
}

export function AuthGate({ children }: AuthGateProps) {
  const location = useLocation();
  const accessToken = useSessionStore((state) => state.accessToken);
  const permissionInfo = useSessionStore((state) => state.permissionInfo);
  const bootstrapQuery = useSessionBootstrap();

  if (!accessToken) {
    return (
      <Navigate
        replace
        to={`/login?redirect=${encodeURIComponent(location.pathname + location.search)}`}
      />
    );
  }

  if (!permissionInfo && bootstrapQuery.isLoading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-[var(--bg)]">
        <div className="surface px-6 py-5 text-sm text-[var(--text-muted)]">
          正在加载权限与工作台入口...
        </div>
      </div>
    );
  }

  if (!permissionInfo) {
    return (
      <Navigate
        replace
        to={`/login?redirect=${encodeURIComponent(location.pathname + location.search)}`}
      />
    );
  }

  return <>{children}</>;
}
