import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { useSessionStore } from '@/features/auth/store/session-store';
import { getPermissionInfo, kodSsoExchange } from '@/shared/api/auth';

export function KodSsoLoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSession = useSessionStore((state) => state.setSession);
  const setTenantContext = useSessionStore((state) => state.setTenantContext);
  const savedTenantId = useSessionStore((state) => state.tenantId);

  useEffect(() => {
    async function handleLogin() {
      const queryTenantId = Number(searchParams.get('tenantId') || '') || savedTenantId;
      const code = searchParams.get('kodSsoCode') || '';
      if (queryTenantId) {
        setTenantContext({ tenantId: queryTenantId });
      }
      if (!code) {
        throw new Error('缺少可道云登录换票码');
      }
      const loginResult = await kodSsoExchange(code);
      const permissionInfo = await getPermissionInfo();
      setSession({
        accessToken: loginResult.accessToken,
        permissionInfo,
        refreshToken: loginResult.refreshToken,
      });
      navigate('/workspace');
    }

    handleLogin().catch(() => {
      navigate('/login');
    });
  }, [navigate, savedTenantId, searchParams, setSession, setTenantContext]);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-[#f4f7fb] px-6">
      <div className="surface w-full max-w-lg px-8 py-10 text-center">
        <div className="hairline-title">可道云 SSO</div>
        <h1 className="mt-3 text-2xl font-semibold">正在同步单点登录身份</h1>
        <div className="mt-4 text-sm leading-7 text-[var(--text-muted)]">
          当前页面会使用 `kodSsoCode` 向 `/system/auth/kod-sso/exchange`
          换取系统令牌，并继续初始化权限与菜单。
        </div>
      </div>
    </div>
  );
}
