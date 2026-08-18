import { lazy, Suspense } from 'react';
import { RouterProvider, createBrowserRouter, Navigate } from 'react-router-dom';

import { AuthGate } from '@/features/auth/components/auth-gate';
import { RootLayout } from '@/widgets/app-shell/root-layout';

const LoginPage = lazy(() =>
  import('@/features/auth/pages/login-page').then((module) => ({
    default: module.LoginPage,
  })),
);
const SocialLoginPage = lazy(() =>
  import('@/features/auth/pages/social-login-page').then((module) => ({
    default: module.SocialLoginPage,
  })),
);
const KodSsoLoginPage = lazy(() =>
  import('@/features/auth/pages/kod-sso-login-page').then((module) => ({
    default: module.KodSsoLoginPage,
  })),
);
const WorkspacePage = lazy(() =>
  import('@/features/approval-center/pages/workspace-page').then((module) => ({
    default: module.WorkspacePage,
  })),
);
const ProcessLaunchPage = lazy(() =>
  import('@/features/process-launch/pages/process-launch-page').then((module) => ({
    default: module.ProcessLaunchPage,
  })),
);
const OACreatePage = lazy(() =>
  import('@/features/oa/pages/oa-create-page').then((module) => ({
    default: module.OACreatePage,
  })),
);
const ApprovalCenterPage = lazy(() =>
  import('@/features/approval-center/pages/approval-center-page').then((module) => ({
    default: module.ApprovalCenterPage,
  })),
);
const ApprovalDetailPage = lazy(() =>
  import('@/features/approval-detail/pages/approval-detail-page').then((module) => ({
    default: module.ApprovalDetailPage,
  })),
);
const AssetManagementPage = lazy(() =>
  import('@/features/process-assets/pages/asset-management-page').then((module) => ({
    default: module.AssetManagementPage,
  })),
);
const AdminMonitorPage = lazy(() =>
  import('@/features/admin-monitor/pages/admin-monitor-page').then((module) => ({
    default: module.AdminMonitorPage,
  })),
);
const ModulePage = lazy(() =>
  import('@/features/module/pages/module-page').then((module) => ({
    default: module.ModulePage,
  })),
);

function withSuspense(element: React.ReactNode) {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-dvh items-center justify-center bg-[var(--bg)] text-sm text-[var(--text-muted)]">
          正在加载页面...
        </div>
      }
    >
      {element}
    </Suspense>
  );
}

const router = createBrowserRouter([
  {
    path: '/login',
    element: withSuspense(<LoginPage />),
  },
  {
    path: '/social-login',
    element: withSuspense(<SocialLoginPage />),
  },
  {
    path: '/kod-sso-login',
    element: withSuspense(<KodSsoLoginPage />),
  },
  {
    path: '/',
    element: (
      <AuthGate>
        <RootLayout />
      </AuthGate>
    ),
    children: [
      { index: true, element: <Navigate to="/workspace" replace /> },
      { path: 'workspace', element: withSuspense(<WorkspacePage />) },
      { path: 'launch', element: withSuspense(<ProcessLaunchPage />) },
      { path: 'launch/oa/:moduleKey', element: withSuspense(<OACreatePage />) },
      { path: 'center/:section', element: withSuspense(<ApprovalCenterPage />) },
      { path: 'detail/:processInstanceId', element: withSuspense(<ApprovalDetailPage />) },
      { path: 'assets/:assetType', element: withSuspense(<AssetManagementPage />) },
      { path: 'admin/:monitorType', element: withSuspense(<AdminMonitorPage />) },
      { path: 'module/:moduleKey', element: withSuspense(<ModulePage />) },
    ],
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
