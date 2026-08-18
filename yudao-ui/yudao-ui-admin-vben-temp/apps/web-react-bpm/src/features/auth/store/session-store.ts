import { create } from 'zustand';

import type { PermissionInfo } from '@/shared/api/auth';

interface SessionState {
  accessToken: string | null;
  permissionInfo: PermissionInfo | null;
  refreshToken: string | null;
  tenantId: number | null;
  visitTenantId: number | null;
  setTokens: (payload: {
    accessToken: string;
    refreshToken: string;
  }) => void;
  setSession: (payload: {
    accessToken: string;
    permissionInfo: PermissionInfo;
    refreshToken: string;
  }) => void;
  setTenantContext: (payload: {
    tenantId: null | number;
    visitTenantId?: null | number;
  }) => void;
  clearSession: () => void;
}

export const useSessionStore = create<SessionState>((set) => ({
  accessToken: localStorage.getItem('approval_access_token'),
  permissionInfo: null,
  refreshToken: localStorage.getItem('approval_refresh_token'),
  tenantId: Number(localStorage.getItem('approval_tenant_id') || '') || null,
  visitTenantId:
    Number(localStorage.getItem('approval_visit_tenant_id') || '') || null,
  clearSession: () => {
    localStorage.removeItem('approval_access_token');
    localStorage.removeItem('approval_refresh_token');
    localStorage.removeItem('approval_tenant_id');
    localStorage.removeItem('approval_visit_tenant_id');
    set({
      accessToken: null,
      permissionInfo: null,
      refreshToken: null,
      tenantId: null,
      visitTenantId: null,
    });
  },
  setTokens: ({ accessToken, refreshToken }) => {
    localStorage.setItem('approval_access_token', accessToken);
    localStorage.setItem('approval_refresh_token', refreshToken);
    set({
      accessToken,
      refreshToken,
    });
  },
  setSession: ({ accessToken, permissionInfo, refreshToken }) => {
    localStorage.setItem('approval_access_token', accessToken);
    localStorage.setItem('approval_refresh_token', refreshToken);
    set({
      accessToken,
      permissionInfo,
      refreshToken,
    });
  },
  setTenantContext: ({ tenantId, visitTenantId }) => {
    if (tenantId) {
      localStorage.setItem('approval_tenant_id', String(tenantId));
    } else {
      localStorage.removeItem('approval_tenant_id');
    }
    if (visitTenantId) {
      localStorage.setItem('approval_visit_tenant_id', String(visitTenantId));
    } else {
      localStorage.removeItem('approval_visit_tenant_id');
    }
    set({
      tenantId,
      visitTenantId: visitTenantId ?? null,
    });
  },
}));
