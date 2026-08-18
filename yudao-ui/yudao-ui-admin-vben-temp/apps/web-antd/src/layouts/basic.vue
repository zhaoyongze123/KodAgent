<script lang="ts" setup>
import type { CSSProperties } from 'vue';
import type { MenuRecordRaw } from '@vben/types';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { RouterView, useRoute } from 'vue-router';

import { useAccess } from '@vben/access';
import { AuthenticationLoginExpiredModal } from '@vben/common-ui';
import { useWatermark } from '@vben/hooks';
import { IconifyIcon } from '@vben/icons';
import { LayoutMenu } from '@vben/layouts';
import { preferences } from '@vben/preferences';
import { useAccessStore, useUserStore } from '@vben/stores';
import { useWebSocket } from '@vueuse/core';

import { Dropdown, Menu, message } from 'ant-design-vue';

import { router } from '#/router';
import { useAuthStore } from '#/store';
import {
  getStandaloneCenterMenuItems,
  getStandaloneCenterMenuPathSet,
  getStandaloneCenterRootMenu,
  isApprovalEntryQuery,
  isStandaloneWorkspacePath,
  KOD_ENTRY_APPROVAL,
  resolveStandaloneRootMenuPath,
} from '#/utils/kod-entry';
import { isAdminUser } from '#/utils/oa-user';
import LoginForm from '#/views/_core/authentication/login.vue';

defineOptions({ name: 'UnifiedOALiteLayout' });

const OA_LITE_NOTICE_PUSH_EVENT = 'oa-lite-notice-push';
const OA_LITE_SIDEBAR_WIDTH_STORAGE_KEY = 'oa-lite-unified-sidebar-width-v2';
const OA_LITE_SIDEBAR_MIN_WIDTH = 140;
const OA_LITE_SIDEBAR_MAX_WIDTH = 320;
const OA_LITE_SIDEBAR_DEFAULT_WIDTH = 140;

const BPM_MANAGEMENT_MENU_PATHS = new Set([
  '/bpm/category',
  '/bpm/manager/form',
  '/bpm/manager/template',
  '/bpm/manager/model',
  '/bpm/manager/definition',
  '/bpm/process-instance/manager',
  '/bpm/group',
]);

const BPM_MANAGEMENT_MENU_ITEMS: MenuRecordRaw[] = [
  {
    name: '流程分类',
    path: '/bpm/category',
  },
  {
    name: '流程表单',
    path: '/bpm/manager/form',
  },
  {
    name: '审批模板管理',
    path: '/bpm/manager/template',
  },
  {
    name: '流程模型',
    path: '/bpm/manager/model',
  },
  {
    name: '流程定义',
    path: '/bpm/manager/definition',
  },
  {
    name: '流程实例',
    path: '/bpm/process-instance/manager',
  },
  {
    name: '用户组',
    path: '/bpm/group',
  },
];

const SYSTEM_MANAGEMENT_MENU_PATHS = new Set([
  '/system/user',
  '/system/role',
  '/system/dept',
  '/system/post',
  '/system/notice',
]);

const SYSTEM_MANAGEMENT_MENU_ITEMS: MenuRecordRaw[] = [
  {
    name: '用户管理',
    path: '/system/user',
  },
  {
    name: '角色管理',
    path: '/system/role',
  },
  {
    name: '部门管理',
    path: '/system/dept',
  },
  {
    name: '岗位管理',
    path: '/system/post',
  },
  {
    name: '通知公告',
    path: '/system/notice',
  },
];

function flattenMenus(
  menus: MenuRecordRaw[] = [],
  result: MenuRecordRaw[] = [],
) {
  menus.forEach((menu) => {
    result.push(menu);
    if (menu.children?.length) {
      flattenMenus(menu.children, result);
    }
  });
  return result;
}

const route = useRoute();
const authStore = useAuthStore();
const userStore = useUserStore();
const accessStore = useAccessStore();
const { hasAccessByCodes } = useAccess();
const { destroyWatermark, updateWatermark } = useWatermark();

const webSocketServer = ref('');
const sidebarWidth = ref(OA_LITE_SIDEBAR_DEFAULT_WIDTH);
const isSidebarResizing = ref(false);
let removeSidebarResizeListeners: (() => void) | null = null;
const {
  data: webSocketData,
  close: closeWebSocket,
  open: openWebSocket,
} = useWebSocket(webSocketServer, {
  autoReconnect: true,
  heartbeat: true,
  immediate: false,
});

const avatar = computed(
  () => userStore.userInfo?.avatar ?? preferences.app.defaultAvatar,
);

function handleUserMenuClick(key: string) {
  if (key === 'logout') {
    void authStore.logout();
  }
}

const accessRootMenus = computed<MenuRecordRaw[]>(() => accessStore.accessMenus);
const accessFlatMenus = computed<MenuRecordRaw[]>(() =>
  flattenMenus(accessRootMenus.value, []),
);
const isAdminWorkbenchUser = computed(() =>
  isAdminUser(userStore.userRoles || []),
);
const isApprovalEntryMode = computed(
  () => !isAdminWorkbenchUser.value && isApprovalEntryQuery(route.query),
);
const isMeetingOrScheduleEntryMode = computed(
  () => !isApprovalEntryMode.value && isStandaloneWorkspacePath(route.path),
);
const bpmRootMenu = computed(
  () =>
    accessFlatMenus.value.find(
      (menu) =>
        menu.path === '/bpm' ||
        menu.path?.startsWith('/bpm/') ||
        menu.name === '流程管理',
    ) || null,
);
const systemRootMenu = computed(
  () =>
    accessFlatMenus.value.find(
      (menu) =>
        menu.path === '/system' ||
        menu.path?.startsWith('/system/') ||
        menu.name === '系统管理',
    ) || null,
);
const currentActivePath = computed(() =>
  String(route.meta.activePath || route.path),
);
const isOaLiteReturnRoute = computed(() => {
  const returnTo = Array.isArray(route.query.returnTo)
    ? route.query.returnTo[0]
    : route.query.returnTo;
  return returnTo === 'oa-lite';
});
const isOARequestRoute = computed(() => route.path.startsWith('/bpm/oa/'));
const isOaLiteProcessInstanceCreateRoute = computed(
  () =>
    route.name === 'BpmProcessInstanceCreate' &&
    (isOaLiteReturnRoute.value ||
      isApprovalEntryQuery(route.query) ||
      currentActivePath.value === '/oa-lite/center'),
);
const isWorkbenchCreateRoute = computed(
  () =>
    (route.path === '/oa-lite/center' && route.query.view === 'create') ||
    route.path === '/oa-lite' ||
    isOARequestRoute.value ||
    isOaLiteProcessInstanceCreateRoute.value,
);
const isWorkbenchNotificationRoute = computed(
  () => route.path.startsWith('/oa-lite/notifications'),
);
const isWorkbenchCenterRoute = computed(
  () => route.path === '/oa-lite/center' && route.query.view !== 'create',
);
const isWorkbenchRoute = computed(
  () =>
    isWorkbenchCreateRoute.value ||
    isWorkbenchCenterRoute.value ||
    isWorkbenchNotificationRoute.value,
);
// 发起审批和审批中心共用同一个工作台视口，避免外层 main 在 create
// 视图下回落到普通页面的左右 padding。
const isWorkbenchViewportRoute = computed(
  () => isWorkbenchCreateRoute.value || isWorkbenchCenterRoute.value,
);
const isManagementRoute = computed(
  () => route.path.startsWith('/bpm') || route.path.startsWith('/system'),
);

const currentMatchedMenu = computed(() => {
  const matched =
    accessStore.getMenuByPath(currentActivePath.value) ||
    accessStore.getMenuByPath(route.path);
  if (matched) {
    return matched;
  }
  if (route.path.startsWith('/system/')) {
    return accessStore.getMenuByPath('/system/user');
  }
  if (route.path.startsWith('/meeting-room/')) {
    return (
      accessStore.getMenuByPath('/meeting-room/booking') ||
      accessStore.getMenuByPath('/meeting-room/schedule') ||
      getStandaloneCenterRootMenu('/meeting-room')
    );
  }
  if (route.path.startsWith('/schedule/')) {
    return (
      accessStore.getMenuByPath('/schedule/calendar') ||
      getStandaloneCenterRootMenu('/schedule')
    );
  }
  if (route.path.startsWith('/party-file/')) {
    return (
      accessStore.getMenuByPath('/party-file/my') ||
      getStandaloneCenterRootMenu('/party-file')
    );
  }
  if (route.path.startsWith('/bpm/')) {
    return (
      accessStore.getMenuByPath('/bpm/manager/model') ||
      accessStore.getMenuByPath('/bpm/manager/form') ||
      accessStore.getMenuByPath('/bpm/category') ||
      accessStore.getMenuByPath('/bpm/group') ||
      accessStore.getMenuByPath('/bpm/process-expression') ||
      accessStore.getMenuByPath('/bpm/process-listener') ||
      bpmRootMenu.value
    );
  }
  return null;
});

const currentRootMenuPath = computed(() => {
  if (isOARequestRoute.value) {
    return '';
  }
  if (isOaLiteProcessInstanceCreateRoute.value) {
    return '';
  }
  if (route.path === '/bpm' || route.path.startsWith('/bpm/')) {
    return '/bpm';
  }
  if (route.path === '/system' || route.path.startsWith('/system/')) {
    return '/system';
  }
  if (route.path === '/meeting-room' || route.path.startsWith('/meeting-room/')) {
    return resolveStandaloneRootMenuPath(route.path);
  }
  const standaloneRootMenuPath = resolveStandaloneRootMenuPath(route.path);
  if (standaloneRootMenuPath) {
    return standaloneRootMenuPath;
  }
  const matchedMenu = currentMatchedMenu.value;
  if (!matchedMenu) {
    return '';
  }
  return matchedMenu.parents?.[0] || matchedMenu.path || '';
});

const currentRootMenu = computed(
  () => {
    if (currentRootMenuPath.value === '/bpm') {
      return bpmRootMenu.value;
    }
    if (currentRootMenuPath.value === '/system') {
      return systemRootMenu.value;
    }
    const standaloneRootMenu = resolveStandaloneRootMenuPath(
      currentRootMenuPath.value,
    );
    if (standaloneRootMenu) {
      return getStandaloneCenterRootMenu(standaloneRootMenu);
    }
    return (
      accessRootMenus.value.find(
        (menu) => menu.path === currentRootMenuPath.value,
      ) || null
    );
  },
);

function filterSidebarMenusByRoot(
  rootMenuPath: string,
  menus: MenuRecordRaw[],
): MenuRecordRaw[] {
  if (rootMenuPath === '/bpm') {
    const flattenedMenus = flattenMenus(menus, []);
    const dynamicBpmMenus = flattenedMenus.filter((menu) =>
      BPM_MANAGEMENT_MENU_PATHS.has(menu.path || ''),
    );
    if (dynamicBpmMenus.length > 0) {
      return BPM_MANAGEMENT_MENU_ITEMS.map((item) => {
        return dynamicBpmMenus.find((menu) => menu.path === item.path) || item;
      });
    }
    return BPM_MANAGEMENT_MENU_ITEMS;
  }
  if (rootMenuPath === '/system') {
    const flattenedMenus = flattenMenus(menus, []);
    const dynamicSystemMenus = flattenedMenus.filter((menu) =>
      SYSTEM_MANAGEMENT_MENU_PATHS.has(menu.path || ''),
    );
    if (dynamicSystemMenus.length > 0) {
      const baseMenus = SYSTEM_MANAGEMENT_MENU_ITEMS.map((item) => {
        return dynamicSystemMenus.find((menu) => menu.path === item.path) || item;
      });
      const extraMenus = dynamicSystemMenus.filter(
        (menu) =>
          menu.path &&
          !SYSTEM_MANAGEMENT_MENU_ITEMS.some((item) => item.path === menu.path),
      );
      return [...baseMenus, ...extraMenus];
    }
    return SYSTEM_MANAGEMENT_MENU_ITEMS;
  }
  const standaloneRootMenuPath = resolveStandaloneRootMenuPath(rootMenuPath);
  if (standaloneRootMenuPath) {
    const flattenedMenus = flattenMenus(menus, []);
    const standalonePathSet = getStandaloneCenterMenuPathSet(
      standaloneRootMenuPath,
    );
    const standaloneMenus = getStandaloneCenterMenuItems(
      standaloneRootMenuPath,
    ).filter((menu) => {
      if (menu.path === '/meeting-room/manage') {
        return hasAccessByCodes(['system:meeting-room:query']);
      }
      if (menu.path === '/party-file/manage') {
        return hasAccessByCodes(['system:party-file:query']);
      }
      return true;
    });
    const dynamicStandaloneMenus = flattenedMenus.filter((menu) =>
      standalonePathSet.has(menu.path || ''),
    );
    if (dynamicStandaloneMenus.length > 0) {
      return standaloneMenus.map((item) => {
        return (
          dynamicStandaloneMenus.find((menu) => menu.path === item.path) || item
        );
      });
    }
    return standaloneMenus;
  }
  return menus;
}

const sidebarMenus = computed<MenuRecordRaw[]>(
  () =>
    filterSidebarMenusByRoot(
      currentRootMenuPath.value,
      currentRootMenu.value?.children || [],
    ),
);

const sidebarOpeneds = computed(() => {
  if (currentRootMenuPath.value === '/bpm') {
    return [];
  }
  const matchedMenu = currentMatchedMenu.value;
  if (!matchedMenu?.parents?.length) {
    return [];
  }
  return matchedMenu.parents.filter((path) => path !== currentRootMenuPath.value);
});

const sidebarMenuKey = computed(
  () => `${currentRootMenuPath.value}:${currentActivePath.value}`,
);

const showSidebar = computed(
  () => !isWorkbenchRoute.value && sidebarMenus.value.length > 0,
);
const sidebarStyle = computed<CSSProperties>(() => ({
  width: `${sidebarWidth.value}px`,
}) as CSSProperties);

const contentStyle = computed<CSSProperties>(() => ({
  '--vben-content-height': isMeetingOrScheduleEntryMode.value
    ? '100vh'
    : showSidebar.value
      ? 'calc(100vh - 132px)'
      : 'calc(100vh - 132px)',
  '--vben-content-width': showSidebar.value
    ? 'calc(100vw - 420px)'
    : 'calc(100vw - 80px)',
}) as CSSProperties);

function handleTopNavSelect(path: string, query: Record<string, string> = {}) {
  if (path === route.path && Object.keys(query).every((key) => route.query[key] === query[key])) {
    return;
  }
  const shouldKeepApprovalEntry =
    isApprovalEntryMode.value && path.startsWith('/oa-lite');
  const nextQuery = shouldKeepApprovalEntry
    ? { ...route.query, ...query, entry: KOD_ENTRY_APPROVAL }
    : query;
  if (path !== '/oa-lite/center' && 'forceCreate' in nextQuery) {
    delete nextQuery.forceCreate;
  }
  router.push({
    path,
    query: nextQuery,
  });
}

function buildWebSocketServer(refreshToken: string) {
  return `${`${import.meta.env.VITE_BASE_URL}/infra/ws`.replace(
    'http',
    'ws',
  )}?token=${encodeURIComponent(refreshToken)}`;
}

function connectNoticeWebSocket() {
  const refreshToken = accessStore.refreshToken as string;
  if (!refreshToken) {
    return;
  }
  const nextServer = buildWebSocketServer(refreshToken);
  if (webSocketServer.value !== nextServer) {
    closeWebSocket();
    webSocketServer.value = nextServer;
  }
  openWebSocket();
}

function parseNoticePushMessage(rawMessage: string) {
  if (rawMessage === 'pong') {
    return null;
  }
  const envelope = JSON.parse(rawMessage);
  if (envelope.type !== 'notice-push' || !envelope.content) {
    return null;
  }
  return JSON.parse(envelope.content) as {
    content: string;
    createTime?: string;
    id: number;
    title: string;
    type?: number;
  };
}

async function handleNoticePushBroadcast(rawMessage: string) {
  const notice = parseNoticePushMessage(rawMessage);
  if (!notice) {
    return;
  }
  message.info(`收到公告：${notice.title}`);
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent(OA_LITE_NOTICE_PUSH_EVENT, {
        detail: notice,
      }),
    );
  }
}

function handleSidebarSelect(path: string) {
  if (path === route.path) {
    return;
  }
  router.push(path);
}

function clampSidebarWidth(nextWidth: number) {
  return Math.min(
    OA_LITE_SIDEBAR_MAX_WIDTH,
    Math.max(OA_LITE_SIDEBAR_MIN_WIDTH, nextWidth),
  );
}

function persistSidebarWidth() {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(
    OA_LITE_SIDEBAR_WIDTH_STORAGE_KEY,
    String(sidebarWidth.value),
  );
}

function stopSidebarResize() {
  isSidebarResizing.value = false;
  removeSidebarResizeListeners?.();
  removeSidebarResizeListeners = null;
}

function handleSidebarResizeStart(event: MouseEvent) {
  if (typeof window === 'undefined' || window.innerWidth <= 768) {
    return;
  }
  event.preventDefault();
  const startX = event.clientX;
  const startWidth = sidebarWidth.value;
  isSidebarResizing.value = true;

  const handleMouseMove = (moveEvent: MouseEvent) => {
    const deltaX = moveEvent.clientX - startX;
    sidebarWidth.value = clampSidebarWidth(startWidth + deltaX);
  };

  const handleMouseUp = () => {
    persistSidebarWidth();
    stopSidebarResize();
  };

  window.addEventListener('mousemove', handleMouseMove);
  window.addEventListener('mouseup', handleMouseUp, { once: true });

  removeSidebarResizeListeners = () => {
    window.removeEventListener('mousemove', handleMouseMove);
    window.removeEventListener('mouseup', handleMouseUp);
  };
}

watch(
  () => ({
    enable: preferences.app.watermark,
    content: preferences.app.watermarkContent,
  }),
  async ({ enable, content }) => {
    if (enable) {
      await updateWatermark({
        content:
          content ||
          `${userStore.userInfo?.id} - ${userStore.userInfo?.nickname}`,
      });
    } else {
      destroyWatermark();
    }
  },
  {
    immediate: true,
  },
);

onMounted(() => {
  if (typeof window !== 'undefined') {
    const savedSidebarWidth = Number.parseInt(
      window.localStorage.getItem(OA_LITE_SIDEBAR_WIDTH_STORAGE_KEY) || '',
      10,
    );
    if (!Number.isNaN(savedSidebarWidth)) {
      sidebarWidth.value = clampSidebarWidth(savedSidebarWidth);
    }
  }
  connectNoticeWebSocket();
});

onBeforeUnmount(() => {
  closeWebSocket();
  stopSidebarResize();
});

watch(
  () => webSocketData.value,
  async (rawMessage) => {
    if (!rawMessage) {
      return;
    }
    try {
      await handleNoticePushBroadcast(rawMessage);
    } catch (error) {
      console.error('处理通知公告实时消息失败', error);
    }
  },
);

</script>

<template>
  <div class="oa-lite-unified-layout">
    <div class="oa-lite-unified-bg"></div>

    <header v-if="!isMeetingOrScheduleEntryMode" class="oa-lite-unified-topbar">
      <button
        class="oa-lite-unified-brand"
        @click="handleTopNavSelect('/oa-lite/center', { view: 'create' })"
      >
        <span class="oa-lite-unified-brand-icon">
          <IconifyIcon icon="carbon:task-asset-view" />
        </span>
        <span class="oa-lite-unified-brand-copy">
          <span class="oa-lite-unified-brand-title">OA 审批</span>
        </span>
      </button>

      <nav class="oa-lite-unified-topnav">
      </nav>

      <div class="oa-lite-unified-actions">
        <div class="oa-lite-unified-action-card">
          <Dropdown placement="bottomRight" :trigger="['click']">
            <button
              class="oa-lite-unified-user-button"
              type="button"
              aria-haspopup="menu"
              aria-label="打开用户菜单"
            >
              <span class="oa-lite-unified-user-name">
                {{ userStore.userInfo?.nickname || userStore.userInfo?.username || '-' }}
              </span>
              <IconifyIcon icon="solar:alt-arrow-down-outline" />
            </button>
            <template #overlay>
              <Menu @click="(e) => handleUserMenuClick(e.key as string)">
                <Menu.Item key="logout">
                  <div class="oa-lite-unified-user-menu-item">
                    <IconifyIcon icon="solar:logout-2-outline" />
                    退出登录
                  </div>
                </Menu.Item>
              </Menu>
            </template>
          </Dropdown>
        </div>
      </div>
    </header>

    <main
      class="oa-lite-unified-main"
      :class="{
        'is-standalone-entry': isMeetingOrScheduleEntryMode,
        'is-workbench': isWorkbenchRoute,
        'is-workbench-center': isWorkbenchViewportRoute,
        'is-management': isManagementRoute,
      }"
    >
      <aside
        v-if="showSidebar"
        class="oa-lite-unified-sidebar"
        :style="sidebarStyle"
      >
        <div class="oa-lite-unified-sidebar-card">
          <div
            v-if="currentRootMenuPath !== '/bpm' && currentRootMenuPath !== '/system'"
            class="oa-lite-unified-sidebar-title"
          >
            {{ currentRootMenu?.name }}
          </div>
          <LayoutMenu
            :key="sidebarMenuKey"
            class="oa-lite-unified-menu"
            :default-active="currentActivePath"
            :default-openeds="sidebarOpeneds"
            :menus="sidebarMenus"
            mode="vertical"
            scroll-to-active
            theme="light"
            @select="handleSidebarSelect"
          />
        </div>
      </aside>
      <button
        v-if="showSidebar"
        class="oa-lite-unified-resizer"
        :class="{ active: isSidebarResizing }"
        aria-label="调整侧边栏宽度"
        @mousedown="handleSidebarResizeStart"
      ></button>

      <section
        class="oa-lite-unified-content"
        :class="{
          'is-workbench': isWorkbenchRoute,
          'is-management': isManagementRoute,
        }"
        :style="contentStyle"
      >
        <div
          class="oa-lite-unified-content-shell"
          :class="{
            'is-workbench': isWorkbenchRoute,
            'is-management': isManagementRoute,
          }"
        >
          <RouterView v-slot="{ Component }">
            <component :is="Component" v-if="Component" />
          </RouterView>
        </div>
      </section>
    </main>

    <AuthenticationLoginExpiredModal
      v-model:open="accessStore.loginExpired"
      :avatar="avatar"
    >
      <LoginForm />
    </AuthenticationLoginExpiredModal>

  </div>
</template>

<style scoped>
.oa-lite-unified-layout {
  position: relative;
  min-height: 100vh;
  overflow-x: hidden;
  background: var(--oa-shell-bg);
  color: var(--oa-ink);
}

.oa-lite-unified-bg {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--oa-shell-surface) 72%, transparent) 0%,
      color-mix(in srgb, var(--oa-shell-surface-subtle) 88%, transparent) 88px,
      transparent 240px
    );
  opacity: 1;
}

:global(body.oa-lite-theme-dark) .oa-lite-unified-bg {
  background:
    linear-gradient(
      180deg,
      rgb(10 18 28 / 72%) 0%,
      rgb(10 18 28 / 28%) 88px,
      transparent 240px
    );
}

.oa-lite-unified-topbar {
  position: sticky;
  top: 0;
  z-index: 40;
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr) auto;
  align-items: center;
  gap: 24px;
  padding: 14px 24px 12px;
  background: color-mix(in srgb, var(--oa-overlay-bg) 100%, transparent);
  border-bottom: 1px solid var(--oa-shell-border);
  box-shadow: 0 1px 0 rgb(15 23 42 / 2%);
}

:global(body.oa-lite-theme-dark) .oa-lite-unified-topbar {
  background: rgb(10 18 28 / 96%);
  box-shadow: none;
}

.oa-lite-unified-brand {
  display: flex;
  align-items: center;
  gap: 14px;
  border: 0;
  background: transparent;
  text-align: left;
}

.oa-lite-unified-brand-icon {
  display: flex;
  size: 36px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--oa-shell-border);
  border-radius: 0;
  background: transparent;
  color: var(--oa-accent);
  font-size: 18px;
}

.oa-lite-unified-brand-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.oa-lite-unified-brand-title {
  color: var(--oa-ink);
  font-size: 16px;
  font-weight: 600;
}

.oa-lite-unified-topnav {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 0;
  overflow-x: auto;
  padding: 0;
  border-bottom: 0;
  border-radius: 0;
  background: transparent;
}

.oa-lite-unified-topnav::-webkit-scrollbar {
  display: none;
}

.oa-lite-unified-topnav-item {
  flex: none;
  height: 42px;
  padding: 0 16px;
  border: 0;
  border-bottom: 2px solid transparent;
  border-radius: 0;
  background: transparent;
  color: var(--oa-ink-soft);
  font-size: 14px;
  font-weight: 500;
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    border-color 0.2s ease;
}

.oa-lite-unified-topnav-item:hover,
.oa-lite-unified-topnav-item.active {
  background: transparent;
  color: var(--oa-ink);
}

.oa-lite-unified-topnav-item.active {
  border-bottom-color: var(--oa-accent);
  color: var(--oa-accent);
  background: transparent;
}

.oa-lite-unified-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.oa-lite-unified-action-card {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0;
  border-radius: 0;
  border: 0;
  background: transparent;
}

.oa-lite-unified-user-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--oa-ink);
  cursor: pointer;
  font: inherit;
  transition:
    background-color 0.2s ease,
    border-color 0.2s ease,
    color 0.2s ease;
}

.oa-lite-unified-user-button:hover,
.oa-lite-unified-user-button:focus-visible {
  border-color: var(--oa-shell-border);
  background: var(--oa-shell-surface-subtle);
  color: var(--oa-accent);
  outline: none;
}

.oa-lite-unified-user-name {
  color: var(--oa-ink);
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
}

.oa-lite-unified-user-menu-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.oa-lite-unified-icon-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--oa-ink-soft);
  transition:
    background-color 0.2s ease,
    color 0.2s ease;
}

.oa-lite-unified-icon-button:hover,
.oa-lite-unified-icon-button.active {
  background: transparent;
  color: var(--oa-accent);
}

.oa-lite-unified-tenant {
  padding: 0 6px;
}

.oa-lite-unified-main {
  display: flex;
  gap: 16px;
  padding: 14px 24px 20px;
}

.oa-lite-unified-main.is-standalone-entry {
  padding-top: 0;
}

.oa-lite-unified-main.is-workbench-center {
  padding-right: 0;
  padding-left: 0;
  padding-bottom: 0;
  flex: 1;
  height: auto;
  min-height: 0;
  overflow: hidden;
}

.oa-lite-unified-layout:has(.oa-lite-unified-main.is-workbench-center) {
  height: 100dvh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* Management pages own the viewport below the top bar. Keep this height chain
 * explicit so the page shell and its table can consume the remaining space
 * instead of collapsing to their content height. */
.oa-lite-unified-layout:has(.oa-lite-unified-main.is-management) {
  display: flex;
  height: 100dvh;
  flex-direction: column;
  overflow: hidden;
}

.oa-lite-unified-main.is-management {
  flex: 1 1 auto;
  height: auto;
  min-height: 0;
  overflow: hidden;
}

.oa-lite-unified-main.is-management .oa-lite-unified-sidebar,
.oa-lite-unified-main.is-management .oa-lite-unified-sidebar-card,
.oa-lite-unified-main.is-management .oa-lite-unified-resizer,
.oa-lite-unified-main.is-management .oa-lite-unified-content,
.oa-lite-unified-main.is-management .oa-lite-unified-content-shell {
  height: 100%;
  min-height: 0;
}

.oa-lite-unified-layout:has(.oa-lite-unified-main.is-workbench-center)
  .oa-lite-unified-content,
.oa-lite-unified-layout:has(.oa-lite-unified-main.is-workbench-center)
  .oa-lite-unified-content-shell {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.oa-lite-unified-sidebar {
  flex: none;
}

.oa-lite-unified-resizer {
  position: relative;
  flex: none;
  width: 14px;
  margin: 0 -5px;
  border: 0;
  background: transparent;
  cursor: col-resize;
  touch-action: none;
  user-select: none;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    margin: auto;
    width: 1px;
    height: 100%;
    background: color-mix(in srgb, var(--oa-shell-border) 78%, transparent);
    transition:
      background-color 0.18s ease,
      transform 0.18s ease;
  }

  &::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 4px;
    height: 36px;
    border-radius: 999px;
    background: color-mix(in srgb, var(--oa-accent) 22%, transparent);
    transform: translate(-50%, -50%);
    opacity: 0;
    transition: opacity 0.18s ease;
  }

  &:hover::before,
  &.active::before {
    background: color-mix(in srgb, var(--oa-accent) 48%, var(--oa-shell-border));
    transform: scaleX(1.2);
  }

  &:hover::after,
  &.active::after {
    opacity: 1;
  }
}

.oa-lite-unified-sidebar-card {
  height: calc(100vh - 132px);
  padding: 10px 0 0;
  border-right: 1px solid var(--oa-shell-border);
  border-radius: 0;
  background: transparent;
  overflow: hidden auto;
}

.oa-lite-unified-main.is-standalone-entry .oa-lite-unified-sidebar-card {
  height: 100vh;
}

.oa-lite-unified-sidebar-title {
  padding: 6px 0 14px;
  color: var(--oa-ink);
  font-size: 14px;
  font-weight: 600;
}

.oa-lite-unified-content {
  min-width: 0;
  flex: 1;
  min-height: calc(100vh - 132px);
}

.oa-lite-unified-main.is-standalone-entry .oa-lite-unified-content {
  min-height: 100vh;
}

.oa-lite-unified-content-shell {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  min-height: 100%;
  overflow: visible;
  border-left: 1px solid var(--oa-shell-border);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.oa-lite-unified-content-shell.is-workbench {
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.oa-lite-unified-menu {
  height: calc(100% - 42px);
  overflow: auto;
}

.oa-lite-unified-sidebar :deep(.vben-menu) {
  padding: 0;
  background: transparent;
}

.oa-lite-unified-sidebar :deep(.vben-menu-item),
.oa-lite-unified-sidebar :deep(.vben-sub-menu-content) {
  border-radius: 0;
}

.oa-lite-unified-sidebar :deep(.vben-menu-item a),
.oa-lite-unified-sidebar :deep(.vben-sub-menu-content) {
  color: var(--oa-ink-soft);
  margin: 0;
}

:global(body.oa-lite-theme-dark) .oa-lite-unified-sidebar :deep(.vben-menu-item a),
:global(body.oa-lite-theme-dark)
  .oa-lite-unified-sidebar :deep(.vben-sub-menu-content) {
  background: color-mix(in srgb, var(--oa-shell-surface) 94%, black);
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 70%, transparent);
  color: var(--oa-ink);
}

.oa-lite-unified-sidebar :deep(.vben-menu-item.is-active a),
.oa-lite-unified-sidebar :deep(.vben-sub-menu-content.is-active) {
  background: color-mix(in srgb, var(--oa-accent-soft) 40%, transparent);
  color: var(--oa-accent);
  box-shadow: inset 2px 0 0 var(--oa-accent);
}

:global(body.oa-lite-theme-dark)
  .oa-lite-unified-sidebar :deep(.vben-menu-item.is-active a),
:global(body.oa-lite-theme-dark)
  .oa-lite-unified-sidebar :deep(.vben-sub-menu-content.is-active) {
  background: color-mix(in srgb, var(--oa-accent-soft) 28%, var(--oa-shell-surface));
  color: var(--oa-accent);
}

.oa-lite-unified-sidebar :deep(.vben-menu-item a:hover),
.oa-lite-unified-sidebar :deep(.vben-sub-menu-content:hover) {
  background: color-mix(in srgb, var(--oa-shell-surface-muted) 55%, transparent);
}

:global(body.oa-lite-theme-dark) .oa-lite-unified-sidebar :deep(.vben-menu-item a:hover),
:global(body.oa-lite-theme-dark)
  .oa-lite-unified-sidebar :deep(.vben-sub-menu-content:hover) {
  background: color-mix(in srgb, var(--oa-shell-surface-muted) 88%, black);
}

.oa-lite-unified-content-shell :deep(.bg-card),
.oa-lite-unified-content-shell :deep(.ant-card),
.oa-lite-unified-content-shell :deep(.vxe-grid),
.oa-lite-unified-content-shell :deep(.ant-modal-content) {
  border-radius: 0;
  box-shadow: none;
}

.oa-lite-unified-content-shell :deep(.border-border),
.oa-lite-unified-content-shell :deep(.ant-card),
.oa-lite-unified-content-shell :deep(.vxe-grid) {
  border-color: var(--oa-shell-border);
}

.oa-lite-unified-content-shell :deep(.vxe-grid),
.oa-lite-unified-content-shell :deep(.vxe-grid--toolbar-wrapper),
.oa-lite-unified-content-shell :deep(.vxe-table--header-wrapper),
.oa-lite-unified-content-shell :deep(.vxe-table--body-wrapper) {
  background: transparent;
}

.oa-lite-unified-content-shell :deep(.vxe-toolbar),
.oa-lite-unified-content-shell :deep(.vxe-grid--toolbar-wrapper) {
  border-radius: 0;
}

.oa-lite-unified-content-shell :deep(.vxe-grid) {
  border-left: 0 !important;
  border-right: 0 !important;
  border-radius: 0 !important;
}

.oa-lite-unified-content-shell :deep(.vxe-grid--toolbar-wrapper),
.oa-lite-unified-content-shell :deep(.vxe-table--header-wrapper) {
  border-left: 0 !important;
  border-right: 0 !important;
}

.oa-lite-unified-content-shell :deep(.ant-btn-primary) {
  border-color: var(--oa-accent);
  background: var(--oa-accent);
  color: var(--oa-accent-contrast);
  box-shadow: none;
}

.oa-lite-unified-content-shell :deep(.ant-input),
.oa-lite-unified-content-shell :deep(.ant-select-selector),
.oa-lite-unified-content-shell :deep(.ant-picker),
.oa-lite-unified-content-shell :deep(.ant-input-affix-wrapper) {
  border-radius: 0;
}

:deep(.oa-lite-settings-modal .ant-modal-content) {
  overflow: hidden;
  border-radius: 0;
  border: 1px solid var(--oa-shell-border);
  box-shadow: 0 10px 28px rgb(15 23 42 / 4%);
}

:global(body.oa-lite-theme-dark) :deep(.oa-lite-settings-modal .ant-modal-content) {
  background: var(--oa-shell-surface);
  border-color: var(--oa-shell-border);
  box-shadow: none;
}

:deep(.oa-lite-settings-modal .ant-modal-body) {
  padding-top: 8px;
}

:global(body.oa-lite-theme-dark) :deep(.oa-lite-settings-modal .ant-modal-body) {
  background: var(--oa-shell-surface);
}

:deep(.oa-lite-settings-modal .ant-modal-header) {
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 82%, white);
  background: transparent;
}

:global(body.oa-lite-theme-dark) :deep(.oa-lite-settings-modal .ant-modal-header) {
  border-bottom-color: var(--oa-shell-border);
  background: var(--oa-shell-surface);
}

.oa-lite-settings-sheet {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  min-height: 540px;
}

.oa-lite-settings-sidebar {
  display: flex;
  min-width: 0;
  flex-direction: column;
  padding: 8px 28px 0 0;
  border-right: 1px solid color-mix(in srgb, var(--oa-shell-border) 82%, white);
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-sidebar {
  border-right-color: var(--oa-shell-border);
}

.oa-lite-settings-sidebar-head {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 4px 0 0;
}

.oa-lite-settings-sidebar-head h3 {
  margin: 0;
  color: var(--oa-ink);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.oa-lite-settings-sidebar-tag {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  justify-content: center;
  padding: 6px 12px;
  border: 1px solid color-mix(in srgb, var(--oa-accent) 14%, var(--oa-shell-border));
  border-radius: 999px;
  background: color-mix(in srgb, var(--oa-accent) 8%, white);
  color: var(--oa-accent);
  font-size: 12px;
  font-weight: 600;
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-sidebar-tag {
  border-color: color-mix(in srgb, var(--oa-accent) 20%, var(--oa-shell-border));
  background: color-mix(in srgb, var(--oa-accent-soft) 24%, var(--oa-shell-surface));
}

.oa-lite-settings-sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding-top: 14px;
}

.oa-lite-settings-pane-trigger {
  display: flex;
  width: 100%;
  padding: 12px 0;
  border: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 72%, transparent);
  background: transparent;
  color: var(--oa-ink-soft);
  text-align: left;
  transition:
    color 0.18s ease,
    border-color 0.18s ease,
    padding-left 0.18s ease;
  position: relative;
}

.oa-lite-settings-pane-trigger:hover,
.oa-lite-settings-pane-trigger.active {
  color: var(--oa-accent);
  border-bottom-color: color-mix(in srgb, var(--oa-accent) 26%, var(--oa-shell-border));
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-pane-trigger {
  border-bottom-color: color-mix(in srgb, var(--oa-shell-border) 72%, transparent);
}

.oa-lite-settings-pane-trigger.active {
  padding-left: 12px;
}

.oa-lite-settings-pane-trigger.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 12px;
  bottom: 12px;
  width: 2px;
  background: var(--oa-accent);
}

.oa-lite-settings-pane-main {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 10px;
}

.oa-lite-settings-pane-main :deep(svg) {
  margin-top: 2px;
  font-size: 16px;
}

.oa-lite-settings-pane-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.oa-lite-settings-pane-title {
  color: currentColor;
  font-size: 14px;
  font-weight: 600;
}

.oa-lite-settings-pane-desc {
  color: var(--oa-ink-faint);
  font-size: 12px;
  line-height: 1.5;
}

.oa-lite-settings-content {
  min-width: 0;
  padding: 8px 0 0 32px;
}

.oa-lite-settings-content-head {
  padding: 0 0 14px;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 82%, white);
  margin-bottom: 22px;
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-content-head {
  border-bottom-color: var(--oa-shell-border);
}

.oa-lite-settings-content-title {
  color: var(--oa-ink);
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.oa-lite-settings-inline-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}

.oa-lite-settings-inline-stat {
  display: flex;
  min-width: 132px;
  flex-direction: column;
  gap: 4px;
  padding: 0 18px 0 0;
  border-right: 1px solid color-mix(in srgb, var(--oa-shell-border) 72%, transparent);
  border-radius: 0;
  background: transparent;
}

.oa-lite-settings-inline-label {
  color: var(--oa-ink-soft);
  font-size: 11px;
  font-weight: 600;
}

.oa-lite-settings-inline-stat strong {
  color: var(--oa-ink);
  font-size: 15px;
  font-weight: 600;
}

.oa-lite-settings-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 20px 20px;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 88%, white);
  border-radius: 18px;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, white 92%, var(--oa-accent) 2%) 0%,
      white 100%
    );
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-section {
  border-color: var(--oa-shell-border);
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--oa-shell-surface) 98%, black) 0%,
    color-mix(in srgb, var(--oa-shell-surface-muted) 96%, black) 100%
  );
}

.oa-lite-settings-section + .oa-lite-settings-section {
  margin-top: 18px;
}

.oa-lite-settings-section-head h4 {
  margin: 0;
  color: var(--oa-ink);
  font-size: 15px;
  font-weight: 600;
}

.oa-lite-settings-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.oa-lite-settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 88%, white);
  border-radius: 14px;
  background: color-mix(in srgb, white 94%, var(--oa-accent) 2%);
  text-align: left;
  transition:
    color 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
  transform 0.18s ease;
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-row {
  border-color: color-mix(in srgb, var(--oa-shell-border) 88%, transparent);
  background: color-mix(in srgb, var(--oa-shell-surface-muted) 72%, var(--oa-shell-surface));
}

.oa-lite-settings-row:hover {
  color: var(--oa-accent);
  border-color: color-mix(in srgb, var(--oa-accent) 22%, var(--oa-shell-border));
  background: color-mix(in srgb, white 90%, var(--oa-accent) 4%);
  transform: translateY(-1px);
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-row:hover {
  border-color: color-mix(in srgb, var(--oa-accent) 26%, var(--oa-shell-border));
  background: color-mix(in srgb, var(--oa-accent-soft) 18%, var(--oa-shell-surface-muted));
}

.oa-lite-settings-row-main {
  display: flex;
  min-width: 0;
  align-items: flex-start;
  gap: 12px;
}

.oa-lite-settings-row-main :deep(svg) {
  margin-top: 2px;
  font-size: 17px;
  color: currentColor;
}

.oa-lite-settings-row-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.oa-lite-settings-row-title {
  color: var(--oa-ink);
  font-size: 15px;
  font-weight: 600;
}

.oa-lite-settings-row-meta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 56px;
  padding: 8px 12px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--oa-accent) 10%, white);
  color: var(--oa-accent);
  font-size: 12px;
  font-weight: 600;
  text-align: right;
  word-break: break-all;
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-row-meta {
  background: color-mix(in srgb, var(--oa-accent-soft) 24%, var(--oa-shell-surface));
}

.oa-lite-settings-split-choice {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.oa-lite-settings-choice {
  display: flex;
  min-height: 108px;
  flex-direction: column;
  justify-content: space-between;
  padding: 18px;
  border: 1px solid color-mix(in srgb, var(--oa-shell-border) 88%, white);
  border-radius: 16px;
  background: color-mix(in srgb, white 95%, var(--oa-accent) 1%);
  text-align: left;
  transition:
    color 0.18s ease,
    border-color 0.18s ease,
    background 0.18s ease,
  transform 0.18s ease;
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-choice {
  border-color: color-mix(in srgb, var(--oa-shell-border) 88%, transparent);
  background: color-mix(in srgb, var(--oa-shell-surface-muted) 68%, var(--oa-shell-surface));
}

.oa-lite-settings-choice:hover,
.oa-lite-settings-choice.active {
  color: var(--oa-accent);
  border-color: color-mix(in srgb, var(--oa-accent) 24%, var(--oa-shell-border));
  background: color-mix(in srgb, white 90%, var(--oa-accent) 4%);
  transform: translateY(-1px);
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-choice:hover,
:global(body.oa-lite-theme-dark) .oa-lite-settings-choice.active {
  border-color: color-mix(in srgb, var(--oa-accent) 28%, var(--oa-shell-border));
  background: color-mix(in srgb, var(--oa-accent-soft) 18%, var(--oa-shell-surface-muted));
}

.oa-lite-settings-choice-top {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.oa-lite-settings-choice-top :deep(svg) {
  font-size: 18px;
}

.oa-lite-settings-choice-title {
  color: var(--oa-ink);
  font-size: 17px;
  font-weight: 600;
}

.oa-lite-settings-choice-state {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  justify-content: center;
  padding: 6px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--oa-accent) 12%, white);
  color: var(--oa-accent);
  font-size: 12px;
  font-weight: 600;
}

:global(body.oa-lite-theme-dark) .oa-lite-settings-choice-state {
  background: color-mix(in srgb, var(--oa-accent-soft) 24%, var(--oa-shell-surface));
}

@media (max-width: 960px) {
  .oa-lite-unified-topbar {
    grid-template-columns: 1fr;
  }

  .oa-lite-unified-main {
    flex-direction: column;
  }

  .oa-lite-unified-sidebar {
    width: 100%;
  }

  .oa-lite-unified-resizer {
    display: none;
  }

  .oa-lite-unified-sidebar-card,
  .oa-lite-unified-content {
    height: auto;
    min-height: calc(100vh - 180px);
  }

  .oa-lite-settings-sheet {
    grid-template-columns: 1fr;
  }

  .oa-lite-settings-sidebar {
    padding-right: 0;
    padding-bottom: 18px;
    border-right: 0;
    border-bottom: 1px solid var(--oa-shell-border);
  }

  .oa-lite-settings-content {
    padding-left: 0;
  }

  .oa-lite-settings-split-choice {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1200px) and (min-width: 961px) {
  .oa-lite-unified-main {
    gap: 10px;
    padding-right: 16px;
    padding-left: 16px;
  }

  .oa-lite-unified-sidebar {
    width: 92px !important;
    min-width: 92px;
    max-width: 92px;
  }

  .oa-lite-unified-resizer {
    display: none;
  }

  .oa-lite-unified-sidebar-card {
    overflow-x: hidden;
  }

  .oa-lite-unified-sidebar-title {
    display: none;
  }

  .oa-lite-unified-sidebar :deep(.vben-menu-item a),
  .oa-lite-unified-sidebar :deep(.vben-sub-menu-content) {
    display: flex;
    min-height: 52px;
    align-items: center;
    justify-content: center;
    padding-right: 10px !important;
    padding-left: 10px !important;
    text-align: center;
  }

  .oa-lite-unified-sidebar :deep(.vben-menu-item a span:last-child),
  .oa-lite-unified-sidebar :deep(.vben-sub-menu-content span:last-child) {
    overflow: hidden;
    max-width: 100%;
    font-size: 12px;
    line-height: 1.2;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}

@media (max-width: 768px) {
  .oa-lite-unified-topbar,
  .oa-lite-unified-main {
    padding-right: 16px;
    padding-left: 16px;
  }

  .oa-lite-unified-actions {
    flex-wrap: wrap;
    justify-content: flex-end;
  }
}
</style>
