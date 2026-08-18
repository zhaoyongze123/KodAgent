import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { useSessionStore } from '@/features/auth/store/session-store';
import {
  getPermissionInfo,
  getTenantByWebsite,
  getTenantSimpleList,
  login,
  socialLogin,
} from '@/shared/api/auth';

export function SocialLoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSession = useSessionStore((state) => state.setSession);
  const setTenantContext = useSessionStore((state) => state.setTenantContext);
  const savedTenantId = useSessionStore((state) => state.tenantId);

  const socialType = Number(searchParams.get('type') || 0);
  const socialCode = searchParams.get('code') || '';
  const socialState = searchParams.get('state') || '';
  const redirect = searchParams.get('redirect') || '/workspace';

  const tenantListQuery = useQuery({
    queryKey: ['social-auth-tenants'],
    queryFn: getTenantSimpleList,
  });
  const websiteTenantQuery = useQuery({
    queryKey: ['social-auth-tenant-website', window.location.hostname],
    queryFn: () => getTenantByWebsite(window.location.hostname),
  });

  const loginMutation = useMutation({
    mutationFn: async () => {
      const websiteTenantId = websiteTenantQuery.data?.id || null;
      const fallbackTenantId = savedTenantId || tenantListQuery.data?.[0]?.id || null;
      const tenantId = websiteTenantId || fallbackTenantId;
      if (tenantId) {
        setTenantContext({ tenantId });
      }

      try {
        const loginResult = await socialLogin({
          code: socialCode,
          state: socialState,
          type: socialType,
        });
        const permissionInfo = await getPermissionInfo();
        setSession({
          accessToken: loginResult.accessToken,
          permissionInfo,
          refreshToken: loginResult.refreshToken,
        });
        return true;
      } catch {
        return false;
      }
    },
    onSuccess: (success) => {
      if (success) {
        navigate(redirect);
      }
    },
  });

  useEffect(() => {
    if (!socialType || !socialCode || !socialState) {
      return;
    }
    if (tenantListQuery.isLoading || websiteTenantQuery.isLoading) {
      return;
    }
    if (!loginMutation.isPending && !loginMutation.isSuccess) {
      loginMutation.mutate();
    }
  }, [
    loginMutation,
    socialCode,
    socialState,
    socialType,
    tenantListQuery.isLoading,
    websiteTenantQuery.isLoading,
  ]);

  return (
    <div className="flex min-h-dvh items-center justify-center bg-[#f4f7fb] px-6">
      <div className="surface w-full max-w-xl px-8 py-10 text-center">
        <div className="hairline-title">社交登录</div>
        <h1 className="mt-3 text-2xl font-semibold">正在尝试快捷登录</h1>
        <div className="mt-4 text-sm leading-7 text-[var(--text-muted)]">
          已根据当前租户上下文尝试调用 `/system/auth/social-login`。
          如果社交账号尚未绑定系统用户，将回退到账号密码绑定登录。
        </div>
        {!loginMutation.isPending && !loginMutation.isSuccess ? (
          <form
            className="mt-8 space-y-4 text-left"
            onSubmit={async (event) => {
              event.preventDefault();
              const formData = new FormData(event.currentTarget);
              const username = String(formData.get('username') || '');
              const password = String(formData.get('password') || '');
              const loginResult = await login({
                password,
                socialCode,
                socialState,
                socialType,
                username,
              });
              const permissionInfo = await getPermissionInfo();
              setSession({
                accessToken: loginResult.accessToken,
                permissionInfo,
                refreshToken: loginResult.refreshToken,
              });
              navigate(redirect);
            }}
          >
            <div>
              <label className="mb-2 block text-sm font-medium">用户名</label>
              <input
                className="w-full border border-[var(--line)] bg-[var(--panel)] px-3 py-3 outline-none"
                name="username"
                placeholder="请输入要绑定的账号"
              />
            </div>
            <div>
              <label className="mb-2 block text-sm font-medium">密码</label>
              <input
                className="w-full border border-[var(--line)] bg-[var(--panel)] px-3 py-3 outline-none"
                name="password"
                placeholder="请输入密码以完成绑定登录"
                type="password"
              />
            </div>
            <button
              className="w-full border border-[#0f56a6] bg-[var(--accent)] px-4 py-3 text-sm font-medium text-white"
              type="submit"
            >
              账号绑定并登录
            </button>
          </form>
        ) : (
          <div className="mt-8 text-sm text-[var(--text-muted)]">正在同步权限，请稍候...</div>
        )}
      </div>
    </div>
  );
}
