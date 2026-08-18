<script lang="ts" setup>
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAccessStore, useUserStore } from '@vben/stores';

import { message } from 'ant-design-vue';

import { kodSsoExchange } from '#/api/core/auth';
import { useAuthStore } from '#/store';
import { resolveKodEntryTarget } from '#/utils/kod-entry';

defineOptions({ name: 'KodSsoLogin' });

const KOD_SSO_CODE_STORAGE_PREFIX = 'kod-sso-consumed:';
const KOD_SSO_AUTO_START_QUERY_KEY = 'autoStart';
let kodSsoLoginInFlight = false;

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const accessStore = useAccessStore();
const userStore = useUserStore();

const loading = ref(true);

function readQueryString(name: string) {
  const value = route.query[name];
  const normalizedValue = Array.isArray(value) ? value[0] : value;
  return typeof normalizedValue === 'string' ? normalizedValue : null;
}

function resolveTenantIdFromQuery() {
  const tenantIdText = readQueryString('tenantId');
  if (!tenantIdText) {
    return null;
  }
  const parsedTenantId = Number(tenantIdText);
  return Number.isFinite(parsedTenantId) && parsedTenantId > 0
    ? parsedTenantId
    : null;
}

function resolveEntryPath() {
  return resolveKodEntryTarget(
    route.query,
    userStore.userInfo?.homePath,
    userStore.userRoles,
  );
}

function buildLoginFallbackTarget() {
  return encodeURIComponent(resolveEntryPath());
}

function resolveKodSsoCode() {
  const value = route.query.kodSsoCode;
  const normalizedValue = Array.isArray(value) ? value[0] : value;
  return typeof normalizedValue === 'string' ? normalizedValue : null;
}

function shouldAutoStartKodSso() {
  return readQueryString(KOD_SSO_AUTO_START_QUERY_KEY) === '1';
}

function buildCurrentKodSsoRouteUrl() {
  const currentUrl = new URL(window.location.href);
  return currentUrl.toString();
}

function redirectToKodSsoStart() {
  const redirectUri = buildCurrentKodSsoRouteUrl();
  const startUrl = `/admin-api/system/auth/kod-sso/start?redirectUri=${encodeURIComponent(redirectUri)}`;
  window.location.replace(startUrl);
}

function buildConsumedCodeKey(code: string) {
  return `${KOD_SSO_CODE_STORAGE_PREFIX}${code}`;
}

function markCodeConsumed(code: string) {
  sessionStorage.setItem(buildConsumedCodeKey(code), '1');
}

function isCodeConsumed(code: string) {
  return sessionStorage.getItem(buildConsumedCodeKey(code)) === '1';
}

async function clearKodSsoCodeFromUrl() {
  if (!('kodSsoCode' in route.query)) {
    return;
  }
  const nextQuery = { ...route.query };
  delete nextQuery.kodSsoCode;
  await router.replace({
    path: route.path,
    query: nextQuery,
  });
}

async function handleKodSsoLogin() {
  if (kodSsoLoginInFlight) {
    return;
  }
  const tenantId = resolveTenantIdFromQuery();
  if (tenantId) {
    accessStore.setTenantId(tenantId);
  }

  const code = resolveKodSsoCode();
  if (!code) {
    if (accessStore.accessToken && !userStore.userInfo) {
      await authStore.fetchUserInfo();
    }
    if (!accessStore.accessToken && shouldAutoStartKodSso()) {
      redirectToKodSsoStart();
      return;
    }
    await router.replace(resolveEntryPath());
    return;
  }
  if (!tenantId && !accessStore.tenantId) {
    throw new Error('缺少租户编号，无法完成可道云登录');
  }

  if (isCodeConsumed(code)) {
    await router.replace(resolveEntryPath());
    return;
  }

  kodSsoLoginInFlight = true;
  try {
    markCodeConsumed(code);
    await clearKodSsoCodeFromUrl();

    const loginResult = await kodSsoExchange(code);
    accessStore.setAccessToken(loginResult.accessToken);
    accessStore.setRefreshToken(loginResult.refreshToken);

    await authStore.fetchUserInfo();
    const targetPath = resolveEntryPath();

    await router.replace(targetPath);
  } catch (error) {
    sessionStorage.removeItem(buildConsumedCodeKey(code));
    throw error;
  } finally {
    kodSsoLoginInFlight = false;
  }
}

onMounted(async () => {
  try {
    await handleKodSsoLogin();
  } catch (error: any) {
    const isConsumedCodeError =
      error?.message === '可道云登录换票码不存在或已过期';
    if (!isConsumedCodeError) {
      message.error(error?.message || '可道云登录失败');
    }
    await router.replace({
      path: '/auth/login',
      query: {
        redirect: buildLoginFallbackTarget(),
      },
    });
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div v-if="loading" class="kod-sso-loading-shell"></div>
</template>

<style scoped>
.kod-sso-loading-shell {
  position: fixed;
  inset: 0;
  z-index: 9999;
  width: 100vw;
  height: 100vh;
  background: #fff;
}
</style>
