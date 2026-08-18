import type { AppRouteRecordRaw, MenuRecordRaw } from '@vben/types';
import type { RouteRecordRaw } from 'vue-router';

import { isAdminUser } from '#/utils/oa-user';

const REMOVED_MENU_PATH_PREFIXES = ['/system/dict', '/system/menu'];
const REMOVED_MENU_NAMES = new Set(['字典管理', '菜单管理']);
const NON_ADMIN_HIDDEN_ROOT_PATHS = new Set(['/bpm', '/system']);

function isRemovedMenuPath(path?: string) {
  if (!path) {
    return false;
  }
  return REMOVED_MENU_PATH_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`),
  );
}

function isRemovedMenuName(name?: string) {
  return !!name && REMOVED_MENU_NAMES.has(name);
}

function shouldRemoveEntry(entry?: { name?: string; path?: string }) {
  return isRemovedMenuName(entry?.name) || isRemovedMenuPath(entry?.path);
}

function isRoleRestrictedRootPath(path?: string, roles: string[] = []) {
  if (!path || isAdminUser(roles)) {
    return false;
  }
  return NON_ADMIN_HIDDEN_ROOT_PATHS.has(path);
}

function filterMenuTree<T extends { children?: T[]; name?: string; path?: string }>(
  menus: T[] = [],
  roles: string[] = [],
): T[] {
  return menus.reduce<T[]>((result, menu) => {
    if (
      shouldRemoveEntry(menu) ||
      isRoleRestrictedRootPath(menu.path, roles)
    ) {
      return result;
    }
    const filteredChildren = menu.children
      ? filterMenuTree(menu.children, roles)
      : undefined;
    result.push({
      ...menu,
      children: filteredChildren,
    });
    return result;
  }, []);
}

function filterRouteMenus<T extends { children?: T[]; name?: string; path?: string }>(
  menus: T[] = [],
): T[] {
  return menus.reduce<T[]>((result, menu) => {
    if (shouldRemoveEntry(menu)) {
      return result;
    }
    const filteredChildren = menu.children
      ? filterRouteMenus(menu.children)
      : undefined;
    result.push({
      ...menu,
      children: filteredChildren,
    });
    return result;
  }, []);
}

function filterAccessMenus(menus: AppRouteRecordRaw[] = []) {
  // 路由注册阶段必须保留 /bpm、/system 根节点，否则普通用户无法拿到
  // OA 发起页依赖的隐藏子路由（例如 /bpm/oa/*/create）。
  return filterRouteMenus<AppRouteRecordRaw>(menus);
}

function filterMenuRecords(menus: MenuRecordRaw[] = []) {
  return filterMenuTree<MenuRecordRaw>(menus);
}

function filterAccessRoutes(routes: RouteRecordRaw[] = []) {
  return routes.filter((route) => !isRemovedMenuPath(route.path));
}

function isBlockedMenuPath(path: string) {
  return isRemovedMenuPath(path);
}

export {
  filterAccessMenus,
  filterAccessRoutes,
  filterMenuRecords,
  isBlockedMenuPath,
};
