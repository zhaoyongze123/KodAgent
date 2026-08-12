import type { RouteLocationNormalized, Router } from 'vue-router';

import { LOGIN_PATH } from '@vben/constants';
import { $t } from '@vben/locales';
import { preferences } from '@vben/preferences';
import { useAccessStore, useDictStore, useUserStore } from '@vben/stores';
import { startProgress, stopProgress } from '@vben/utils';

import { message } from 'ant-design-vue';

import { getSimpleDictDataList } from '#/api/system/dict/data';
import { accessRoutes, coreRouteNames } from '#/router/routes';
import { useAuthStore } from '#/store';
import {
  filterAccessRoutes,
  filterMenuRecords,
  isBlockedMenuPath,
} from '#/utils/menu-filter';
import { isAdminUser, resolveUserHomePath } from '#/utils/oa-user';

import { generateAccess } from './access';

const NON_ADMIN_WORKBENCH_ALLOWED_PREFIXES = [
  '/bpm/oa/',
  '/bpm/process-instance/create',
];

function isNonAdminBlockedWorkbenchPath(path: string, roles: string[] = []) {
  if (isAdminUser(roles)) {
    return false;
  }
  if (
    NON_ADMIN_WORKBENCH_ALLOWED_PREFIXES.some(
      (prefix) => path === prefix || path.startsWith(prefix),
    )
  ) {
    return false;
  }
  return (
    path === '/bpm' ||
    path.startsWith('/bpm/') ||
    path === '/system' ||
    path.startsWith('/system/')
  );
}

function buildLoginRedirect(fullPath: string) {
  return {
    path: LOGIN_PATH,
    query:
      fullPath === preferences.app.defaultHomePath
        ? {}
        : { redirect: encodeURIComponent(fullPath) },
    replace: true,
  };
}

function isOaWorkbenchPath(path: string) {
  return path === '/oa-lite' || path.startsWith('/oa-lite/');
}

const OA_LITE_CENTER_PATH = '/oa-lite/center';

const BPM_MANAGEMENT_PAGE_BY_PATH: Record<string, string> = {
  '/bpm/category': 'category',
  '/bpm/group': 'group',
  '/bpm/manager/definition': 'definition',
  '/bpm/manager/form': 'form',
  '/bpm/manager/template': 'template',
  '/bpm/manager/model': 'model',
  '/bpm/process-expression': 'expression',
  '/bpm/process-instance/manager': 'process',
  '/bpm/process-instance/report': 'report',
  '/bpm/process-listener': 'listener',
};

function resolveQueryString(value: unknown) {
  const normalizedValue = Array.isArray(value) ? value[0] : value;
  return typeof normalizedValue === 'string' ? normalizedValue : undefined;
}

/**
 * BPM 管理页必须始终由 OA 工作台承载。列表页内部进入设计器时原本会跳到
 * /bpm/...，导致 RouterView 从 oa-lite 卸载并回落为旧的通用侧栏。
 */
function redirectBpmManagementToWorkbench(
  to: RouteLocationNormalized,
  from: RouteLocationNormalized,
) {
  let page = BPM_MANAGEMENT_PAGE_BY_PATH[to.path];
  let bpmView: string | undefined;
  const query = { ...to.query } as Record<string, string | string[]>;

  if (to.path === '/bpm/manager/form/edit') {
    page = 'form';
    bpmView = 'form-editor';
  } else if (to.path === '/bpm/manager/model/create') {
    page = 'model';
    bpmView = 'model-editor';
    query.modelAction = 'create';
  } else if (to.path.startsWith('/bpm/manager/model/')) {
    page = 'model';
    bpmView = 'model-editor';
    const action = resolveQueryString(to.params.type);
    const id = resolveQueryString(to.params.id);
    if (action) {
      query.modelAction = action;
    }
    if (id) {
      query.modelId = id;
    }
  }

  if (!page) {
    return undefined;
  }

  // 从可道云审批入口进入时，深层页面也必须保留该上下文。
  if (!query.entry && resolveQueryString(from.query.entry) === 'approval') {
    query.entry = 'approval';
  }

  return {
    path: OA_LITE_CENTER_PATH,
    query: {
      ...query,
      bpmView,
      manage: 'bpm',
      page,
      view: 'center',
    },
    replace: true,
  };
}

function resolveQueryValue(value: unknown) {
  return Array.isArray(value) ? value[0] : value;
}

function redirectWorkbenchProcessDetail(
  to: RouteLocationNormalized,
  from: RouteLocationNormalized,
) {
  if (
    to.name !== 'BpmProcessInstanceDetail' ||
    !isOaWorkbenchPath(from.path)
  ) {
    return undefined;
  }
  const processInstanceId = resolveQueryValue(to.query?.id);
  if (!processInstanceId) {
    return undefined;
  }
  const taskId = resolveQueryValue(to.query?.taskId);
  const activityId = resolveQueryValue(to.query?.activityId);
  const managementEntry =
    resolveQueryValue(from.query?.manage) === 'bpm' &&
    resolveQueryValue(from.query?.page) === 'process';
  return {
    path: '/oa-lite/center',
    query: {
      view: 'center',
      detailSection: managementEntry ? 'manager' : taskId ? 'pending' : 'initiated',
      detailProcessInstanceId: String(processInstanceId),
      ...(taskId ? { detailTaskId: String(taskId) } : {}),
      ...(activityId ? { detailActivityId: String(activityId) } : {}),
      ...(managementEntry ? { manage: 'bpm', page: 'process' } : {}),
      ...(resolveQueryValue(from.query?.entry) === 'approval'
        ? { entry: 'approval' }
        : {}),
    },
    replace: true,
  };
}

/**
 * 通用守卫配置
 * @param router
 */
function setupCommonGuard(router: Router) {
  // 记录已经加载的页面
  const loadedPaths = new Set<string>();

  router.beforeEach((to) => {
    to.meta.loaded = loadedPaths.has(to.path);

    // 页面加载进度条
    if (!to.meta.loaded && preferences.transition.progress) {
      startProgress();
    }
    return true;
  });

  router.afterEach((to) => {
    // 记录页面是否加载,如果已经加载，后续的页面切换动画等效果不在重复执行

    loadedPaths.add(to.path);

    // 关闭页面加载进度条
    if (preferences.transition.progress) {
      stopProgress();
    }
  });
}

/**
 * 权限访问守卫配置
 * @param router
 */
function setupAccessGuard(router: Router) {
  router.beforeEach(async (to, from) => {
    const accessStore = useAccessStore();
    const userStore = useUserStore();
    const authStore = useAuthStore();
    const dictStore = useDictStore();

    const workbenchDetailRedirect = redirectWorkbenchProcessDetail(to, from);
    if (workbenchDetailRedirect) {
      return workbenchDetailRedirect;
    }

    if (isBlockedMenuPath(to.path)) {
      return {
        path: preferences.app.defaultHomePath,
        replace: true,
      };
    }

    // 基本路由，这些路由不需要进入权限拦截
    if (coreRouteNames.includes(to.name as string)) {
      if (to.path === LOGIN_PATH && accessStore.accessToken) {
        return decodeURIComponent(
          (to.query?.redirect as string) ||
            resolveUserHomePath(
              userStore.userInfo?.homePath,
              userStore.userRoles,
            ),
        );
      }
      return true;
    }

    // accessToken 检查
    if (!accessStore.accessToken) {
      // 明确声明忽略权限访问权限，则可以访问
      if (to.meta.ignoreAccess) {
        return true;
      }

      // 没有访问权限，跳转登录页面
      if (to.fullPath !== LOGIN_PATH) {
        return buildLoginRedirect(to.fullPath);
      }
      return to;
    }

    let userInfo = userStore.userInfo;
    let userRoles = userStore.userRoles ?? [];

    // 是否已经生成过动态路由
    if (accessStore.isAccessChecked) {
      if (isNonAdminBlockedWorkbenchPath(to.path, userStore.userRoles)) {
        return {
          path: resolveUserHomePath(
            userStore.userInfo?.homePath,
            userStore.userRoles,
          ),
          replace: true,
        };
      }
      const workbenchManagementRedirect = redirectBpmManagementToWorkbench(
        to,
        from,
      );
      if (workbenchManagementRedirect) {
        return workbenchManagementRedirect;
      }
      accessStore.setAccessMenus(filterMenuRecords(accessStore.accessMenus));
      accessStore.setAccessRoutes(filterAccessRoutes(accessStore.accessRoutes));
      return true;
    }

    // 加载字典数据（不阻塞加载）
    dictStore.setDictCacheByApi(getSimpleDictDataList);

    // 生成路由表
    // 当前登录用户拥有的角色标识列表
    if (!userInfo) {
      // add by 芋艿：由于 yudao 是 fetchUserInfo 统一加载用户 + 权限信息，所以将 fetchMenuListAsync
      const loading = message.loading({
        content: `${$t('common.loadingMenu')}...`,
      });
      try {
        const authPermissionInfo = await authStore.fetchUserInfo();
        if (authPermissionInfo) {
          userInfo = authPermissionInfo.user;
        }
      } catch (error) {
        console.error('加载用户信息失败，已回退到登录页', error);
        return buildLoginRedirect(to.fullPath);
      } finally {
        loading();
      }
      userRoles = userStore.userRoles ?? [];
    }

    if (isNonAdminBlockedWorkbenchPath(to.path, userRoles)) {
      return {
        path: resolveUserHomePath(
          userInfo?.homePath,
          userRoles,
        ),
        replace: true,
      };
    }

    const workbenchManagementRedirect = redirectBpmManagementToWorkbench(
      to,
      from,
    );
    if (workbenchManagementRedirect) {
      return workbenchManagementRedirect;
    }

    // 生成菜单和路由
    const { accessibleMenus, accessibleRoutes } = await generateAccess({
      roles: userRoles,
      router,
      // 则会在菜单中显示，但是访问会被重定向到403
      routes: accessRoutes,
    });

    // 保存菜单信息和路由信息
    accessStore.setAccessMenus(filterMenuRecords(accessibleMenus));
    accessStore.setAccessRoutes(filterAccessRoutes(accessibleRoutes));
    accessStore.setIsAccessChecked(true);
    userStore.setUserRoles(userRoles);
    const hasExplicitTargetQuery =
      Object.keys(to.query || {}).length > 0 ||
      typeof to.query?.entry === 'string' ||
      typeof to.query?.redirect === 'string';
    const redirectPath = (from.query.redirect ??
      (to.path === preferences.app.defaultHomePath && !hasExplicitTargetQuery
        ? resolveUserHomePath(
            userInfo?.homePath,
            userRoles,
          )
        : to.fullPath)) as string;
    const normalizedRedirectPath = decodeURIComponent(redirectPath);

    return {
      ...router.resolve(normalizedRedirectPath),
      replace: true,
    };
  });
}

/**
 * 项目守卫配置
 * @param router
 */
function createRouterGuard(router: Router) {
  /** 通用 */
  setupCommonGuard(router);
  /** 权限访问 */
  setupAccessGuard(router);
}

export { createRouterGuard };
