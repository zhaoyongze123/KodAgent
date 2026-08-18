import {
  ArrowsClockwise,
  Buildings,
  ClipboardText,
  FlowArrow,
  GearSix,
  HardDrives,
  House,
  SignOut,
  Stack,
} from '@phosphor-icons/react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';

import { useSessionStore } from '@/features/auth/store/session-store';
import {
  getSectionModules,
  navSections,
  type NavSectionKey,
} from '@/shared/config/module-registry';
import { cn } from '@/shared/lib/cn';

const iconMap: Record<NavSectionKey, typeof House> = {
  admin: Buildings,
  'bpm-assets': Stack,
  center: FlowArrow,
  infra: HardDrives,
  launch: ClipboardText,
  system: GearSix,
  workspace: House,
};

function resolveActiveSection(pathname: string): NavSectionKey {
  if (pathname.startsWith('/launch')) return 'launch';
  if (pathname.startsWith('/center')) return 'center';
  if (pathname.startsWith('/assets')) return 'bpm-assets';
  if (pathname.startsWith('/admin')) return 'admin';
  if (pathname.startsWith('/module/system-')) return 'system';
  if (pathname.startsWith('/module/infra-')) return 'infra';
  return 'workspace';
}

export function RootLayout() {
  const location = useLocation();
  const user = useSessionStore((state) => state.permissionInfo?.user);
  const permissions = useSessionStore(
    (state) => state.permissionInfo?.permissions || [],
  );
  const clearSession = useSessionStore((state) => state.clearSession);
  const activeSection = resolveActiveSection(location.pathname);
  const visibleSections = navSections.filter((section) => {
    const modules = getSectionModules(section.key);
    if (modules.length === 0) {
      return true;
    }
    return modules.some(
      (item) => !item.permission || permissions.includes(item.permission),
    );
  });
  const visibleModules = getSectionModules(activeSection).filter(
    (item) => !item.permission || permissions.includes(item.permission),
  );
  const activeSectionMeta = visibleSections.find((item) => item.key === activeSection);
  const visiblePermissionCount = permissions.length;

  return (
    <div className="grid min-h-dvh grid-cols-[84px_296px_minmax(0,1fr)] bg-[var(--bg)]">
      <aside className="border-r border-[var(--line)] bg-[#e7edf4] px-2 py-3">
        <div className="mb-4 flex h-14 flex-col items-center justify-center border border-[var(--line)] bg-white">
          <div className="text-[10px] font-semibold text-[var(--text-soft)]">YUD</div>
          <div className="mt-1 text-sm font-semibold">OA</div>
        </div>
        <nav className="space-y-1.5">
          {visibleSections.map((item) => {
            const Icon = iconMap[item.key];
            return (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex flex-col items-center gap-1 border border-transparent px-2 py-3 text-[11px] text-[var(--text-muted)] transition-colors',
                    isActive
                      ? 'border-[var(--line)] bg-white text-[var(--text)]'
                      : 'hover:bg-[#f2f6fa]',
                  )
                }
              >
                <Icon size={18} />
                <span className="text-center">{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </aside>

      <aside className="border-r border-[var(--line)] bg-[#f6f9fc]">
        <div className="section-heading">
          <div>
            <div className="hairline-title">当前工作域</div>
            <h2>{activeSectionMeta?.label || '工作台'}</h2>
          </div>
        </div>
        <div className="border-b border-[var(--line)] px-5 py-4">
          <div className="shell-subtitle text-pretty">
            {activeSectionMeta?.subtitle || '统一承接员工处理、审批配置与流程监管'}
          </div>
        </div>
        <div className="grid grid-cols-2 gap-0 border-b border-[var(--line)]">
          <div className="px-5 py-3">
            <div className="work-meta">可见模块</div>
            <div className="mt-1 text-lg font-semibold tabular-nums">
              {visibleModules.length}
            </div>
          </div>
          <div className="border-l border-[var(--line)] px-5 py-3">
            <div className="work-meta">权限点</div>
            <div className="mt-1 text-lg font-semibold tabular-nums">
              {visiblePermissionCount}
            </div>
          </div>
        </div>
        <div className="px-3 py-3">
          {visibleModules.length > 0 ? (
            <div className="space-y-1">
              {visibleModules.map((item) => (
                <NavLink
                  key={item.key}
                  to={item.path}
                  className={({ isActive }) =>
                    cn(
                      'block border border-transparent px-3 py-3 text-sm transition-colors',
                      isActive
                        ? 'border-[var(--line)] bg-white text-[var(--text)]'
                        : 'text-[var(--text-muted)] hover:bg-white',
                    )
                  }
                >
                  <div className="font-medium">{item.label}</div>
                  <div className="mt-1 text-xs text-[var(--text-soft)]">
                    {item.description}
                  </div>
                </NavLink>
              ))}
            </div>
          ) : (
            <div className="px-2 text-sm text-[var(--text-muted)]">当前区域没有附加模块</div>
          )}
        </div>
      </aside>

      <div className="flex min-h-dvh flex-col">
        <header className="border-b border-[var(--line)] bg-[#f8fbfe] px-6 py-4">
          <div className="flex items-start justify-between gap-6">
            <div>
              <div className="hairline-title">统一审批工作面</div>
              <div className="mt-1 text-[20px] font-semibold text-balance">
                员工、审批人、负责人、财务与管理员共用一套界面，按权限收敛入口
              </div>
              <div className="mt-2 shell-subtitle text-pretty">
                以待办处理、流程发起、审批跟踪和流程资产维护为核心，而不是通用后台卡片首页。
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button
                aria-label="刷新"
                className="subtle-chip"
                type="button"
                onClick={() => window.location.reload()}
              >
                <ArrowsClockwise size={14} />
                刷新
              </button>
              <div className="border-l border-[var(--line)] pl-3 text-right">
                <div className="text-sm font-medium">{user?.nickname || '未登录'}</div>
                <div className="text-xs text-[var(--text-soft)]">
                  {user?.deptName || '未识别部门'}
                </div>
              </div>
              <button
                aria-label="退出登录"
                className="subtle-chip"
                type="button"
                onClick={() => clearSession()}
              >
                <SignOut size={14} />
                退出
              </button>
            </div>
          </div>
        </header>
        <main className="min-h-0 flex-1 p-4 lg:p-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
