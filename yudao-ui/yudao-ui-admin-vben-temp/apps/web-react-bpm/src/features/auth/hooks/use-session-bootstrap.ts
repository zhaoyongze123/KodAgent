import { useQuery } from '@tanstack/react-query';

import { useSessionStore } from '@/features/auth/store/session-store';
import { getPermissionInfo } from '@/shared/api/auth';

export function useSessionBootstrap() {
  const accessToken = useSessionStore((state) => state.accessToken);
  const permissionInfo = useSessionStore((state) => state.permissionInfo);
  const refreshToken = useSessionStore((state) => state.refreshToken);
  const setSession = useSessionStore((state) => state.setSession);
  const clearSession = useSessionStore((state) => state.clearSession);

  return useQuery({
    enabled: Boolean(accessToken) && !permissionInfo,
    queryKey: ['session-bootstrap', accessToken],
    queryFn: async () => {
      try {
        const nextPermissionInfo = await getPermissionInfo();
        setSession({
          accessToken: accessToken || '',
          permissionInfo: nextPermissionInfo,
          refreshToken: refreshToken || '',
        });
        return nextPermissionInfo;
      } catch (error) {
        clearSession();
        throw error;
      }
    },
    retry: false,
  });
}
