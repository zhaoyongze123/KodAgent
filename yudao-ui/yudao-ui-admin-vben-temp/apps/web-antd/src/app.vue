<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref, watchEffect } from 'vue';

import { useAntdDesignTokens } from '@vben/hooks';
import { preferences, updatePreferences } from '@vben/preferences';

import { App, ConfigProvider, theme } from 'ant-design-vue';

import { antdLocale } from '#/locales';

defineOptions({ name: 'App' });

const { tokens } = useAntdDesignTokens();
const OA_LITE_THEME_STORAGE_KEY = 'oa-lite-theme-mode';
const OA_LITE_THEME_EVENT = 'oa-lite-theme-change';
const OA_LITE_BODY_THEME_CLASS = 'oa-lite-theme';
const themeMode = ref<'dark' | 'light'>('light');

function handleThemeModeChange(event: Event) {
  const nextMode = (event as CustomEvent<'dark' | 'light'>).detail;
  themeMode.value = nextMode === 'dark' ? 'dark' : 'light';
}

function resolveInitialThemeMode(): 'dark' | 'light' {
  if (typeof window === 'undefined') {
    return 'light';
  }
  const storedMode = window.localStorage.getItem(OA_LITE_THEME_STORAGE_KEY);
  return storedMode === 'dark' ? 'dark' : 'light';
}

const tokenTheme = computed(() => {
  const algorithm =
    themeMode.value === 'dark'
      ? [theme.darkAlgorithm]
      : [theme.defaultAlgorithm];

  // antd 紧凑模式算法
  if (preferences.app.compact) {
    algorithm.push(theme.compactAlgorithm);
  }

  return {
    algorithm,
    token: {
      ...tokens,
      borderRadius: 14,
      colorBgBase: themeMode.value === 'dark' ? '#0c141d' : '#eef2f7',
      colorBgContainer: themeMode.value === 'dark' ? '#101923' : '#ffffff',
      colorBgElevated: themeMode.value === 'dark' ? '#16212d' : '#ffffff',
      colorBorder: themeMode.value === 'dark' ? '#263243' : '#d7dee8',
      colorFillSecondary: themeMode.value === 'dark' ? '#16212d' : '#f3f6fa',
      colorPrimary: themeMode.value === 'dark' ? '#7cc0ff' : '#1565c0',
      colorPrimaryHover: themeMode.value === 'dark' ? '#95cdff' : '#0b57a1',
      colorText: themeMode.value === 'dark' ? '#edf3fb' : '#17202d',
      colorTextSecondary: themeMode.value === 'dark' ? '#9eacbf' : '#4c5b70',
    },
  };
});

watchEffect(() => {
  if (typeof document === 'undefined') {
    return;
  }
  document.body.classList.add(OA_LITE_BODY_THEME_CLASS);
  document.body.classList.remove('oa-lite-theme-dark', 'oa-lite-theme-light');
  document.body.classList.add(`oa-lite-theme-${themeMode.value}`);
  document.documentElement.classList.remove('dark', 'light');
  document.documentElement.classList.add(themeMode.value);
  document.documentElement.dataset.oaLiteTheme = themeMode.value;
});

onMounted(() => {
  themeMode.value = resolveInitialThemeMode();
  window.addEventListener(OA_LITE_THEME_EVENT, handleThemeModeChange as EventListener);
  updatePreferences({
    app: {
      colorGrayMode: false,
      colorWeakMode: false,
      enableCopyPreferences: false,
      enablePreferences: false,
      enableStickyPreferencesNavigationBar: false,
      watermark: false,
      watermarkContent: '',
    },
    theme: {
      mode: themeMode.value,
      semiDarkHeader: false,
      semiDarkSidebar: false,
      semiDarkSidebarSub: false,
    },
    widget: {
      themeToggle: false,
      timezone: false,
    },
  });
  window.dispatchEvent(
    new CustomEvent(OA_LITE_THEME_EVENT, {
      detail: themeMode.value,
    }),
  );
});

onBeforeUnmount(() => {
  if (typeof window === 'undefined') {
    return;
  }
  window.removeEventListener(
    OA_LITE_THEME_EVENT,
    handleThemeModeChange as EventListener,
  );
});
</script>

<template>
  <ConfigProvider :locale="antdLocale" :theme="tokenTheme">
    <App>
      <RouterView />
    </App>
  </ConfigProvider>
</template>

<style>
html,
body,
body.oa-lite-theme {
  background: var(--oa-shell-bg);
  color: var(--oa-ink);
  font-family:
    'PingFang SC',
    'SF Pro Display',
    'SF Pro Text',
    'Microsoft YaHei',
    system-ui,
    sans-serif;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

:root {
  --oa-shell-bg: #f5f6f8;
  --oa-shell-bg-strong: #eceff3;
  --oa-shell-surface: #ffffff;
  --oa-shell-surface-muted: #f7f8fa;
  --oa-shell-surface-subtle: #f1f3f6;
  --oa-shell-surface-emphasis: #edf3fb;
  --oa-shell-surface-raised: #fbfcfe;
  --oa-shell-border: #e5e9f0;
  --oa-shell-border-strong: #d6dde8;
  --oa-shell-shadow: 0 8px 20px rgb(15 23 42 / 3%);
  --oa-shell-shadow-hover: 0 6px 14px rgb(15 23 42 / 4%);
  --oa-accent: #1677ff;
  --oa-accent-strong: #0f5fd1;
  --oa-accent-soft: #eaf3ff;
  --oa-accent-contrast: #ffffff;
  --oa-ink: #1f2329;
  --oa-ink-soft: #5f6b7a;
  --oa-ink-faint: #8a94a6;
  --oa-success-soft: #ebf8f0;
  --oa-success-text: #1d7a46;
  --oa-danger-soft: #fdeeee;
  --oa-danger-text: #c3413f;
  --oa-warning-soft: #fbf3e4;
  --oa-warning-text: #9b651b;
  --oa-info-soft: #e9f2fd;
  --oa-info-text: #175ea7;
  --oa-focus-ring: 0 0 0 3px rgb(22 119 255 / 14%);
  --oa-overlay-bg: rgb(255 255 255 / 94%);
  --oa-radius-xs: 4px;
  --oa-radius-sm: 6px;
  --oa-radius-md: 10px;
  --oa-radius-lg: 14px;
  --oa-space-page: 24px;
  --oa-topbar-height: 132px;
  --oa-grid-line: rgb(148 163 184 / 8%);
}

html.dark,
body.oa-lite-theme-dark {
  --oa-shell-bg: #0c141d;
  --oa-shell-bg-strong: #101923;
  --oa-shell-surface: #101923;
  --oa-shell-surface-muted: #16212d;
  --oa-shell-surface-subtle: #0f1a25;
  --oa-shell-surface-emphasis: #192635;
  --oa-shell-surface-raised: #182431;
  --oa-shell-border: #263243;
  --oa-shell-border-strong: #334154;
  --oa-shell-shadow: 0 12px 28px rgb(0 0 0 / 18%);
  --oa-shell-shadow-hover: 0 8px 18px rgb(0 0 0 / 20%);
  --oa-accent: #7cc0ff;
  --oa-accent-strong: #9bd0ff;
  --oa-accent-soft: rgb(124 192 255 / 14%);
  --oa-accent-contrast: #071019;
  --oa-ink: #edf3fb;
  --oa-ink-soft: #9eacbf;
  --oa-ink-faint: #718096;
  --oa-success-soft: rgb(80 173 115 / 14%);
  --oa-success-text: #7fd89f;
  --oa-danger-soft: rgb(233 96 92 / 14%);
  --oa-danger-text: #ff9894;
  --oa-warning-soft: rgb(219 160 72 / 14%);
  --oa-warning-text: #f2c47b;
  --oa-info-soft: rgb(124 192 255 / 14%);
  --oa-info-text: #9bd0ff;
  --oa-focus-ring: 0 0 0 3px rgb(124 192 255 / 16%);
  --oa-overlay-bg: rgb(10 18 28 / 96%);
  --oa-grid-line: rgb(148 163 184 / 14%);
}

body.oa-lite-theme .ant-app {
  color: var(--oa-ink);
}

body.oa-lite-theme * {
  scrollbar-width: thin;
  scrollbar-color: color-mix(in srgb, var(--oa-shell-border-strong) 88%, transparent)
    transparent;
}

body.oa-lite-theme *::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

body.oa-lite-theme *::-webkit-scrollbar-thumb {
  border: 3px solid transparent;
  border-radius: 0;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--oa-shell-border-strong) 92%, transparent),
      color-mix(in srgb, var(--oa-shell-border) 78%, transparent)
    )
    padding-box;
}

body.oa-lite-theme *::-webkit-scrollbar-track {
  background: transparent;
}

body.oa-lite-theme .ant-btn,
body.oa-lite-theme .ant-input,
body.oa-lite-theme .ant-input-affix-wrapper,
body.oa-lite-theme .ant-picker,
body.oa-lite-theme .ant-select-selector,
body.oa-lite-theme .ant-modal-content,
body.oa-lite-theme .ant-modal-header,
body.oa-lite-theme .ant-table-wrapper,
body.oa-lite-theme .ant-card,
body.oa-lite-theme .ant-pagination .ant-pagination-item,
body.oa-lite-theme .ant-pagination .ant-pagination-prev .ant-pagination-item-link,
body.oa-lite-theme .ant-pagination .ant-pagination-next .ant-pagination-item-link {
  border-radius: var(--oa-radius-sm);
}

body.oa-lite-theme .ant-input,
body.oa-lite-theme .ant-input-affix-wrapper,
body.oa-lite-theme .ant-picker,
body.oa-lite-theme .ant-select-selector {
  background: var(--oa-shell-surface) !important;
  border-color: var(--oa-shell-border) !important;
  color: var(--oa-ink) !important;
}

body.oa-lite-theme .ant-input::placeholder,
body.oa-lite-theme .ant-input-affix-wrapper input::placeholder {
  color: var(--oa-ink-faint) !important;
}

body.oa-lite-theme .ant-btn {
  height: 40px;
  padding-inline: 16px;
  font-weight: 600;
  box-shadow: none !important;
}

body.oa-lite-theme .ant-btn-default {
  border-color: var(--oa-shell-border) !important;
  color: var(--oa-ink) !important;
  background: transparent !important;
}

body.oa-lite-theme .ant-btn-default:hover,
body.oa-lite-theme .ant-btn-default:focus {
  border-color: var(--oa-accent) !important;
  color: var(--oa-accent) !important;
  background: transparent !important;
}

body.oa-lite-theme .ant-btn-primary {
  border-color: var(--oa-accent) !important;
  color: var(--oa-accent-contrast) !important;
  background: var(--oa-accent) !important;
}

body.oa-lite-theme .ant-btn-primary:hover,
body.oa-lite-theme .ant-btn-primary:focus {
  border-color: var(--oa-accent-strong) !important;
  background: var(--oa-accent-strong) !important;
}

body.oa-lite-theme .ant-card,
body.oa-lite-theme .ant-table-wrapper,
body.oa-lite-theme .vxe-grid {
  border: 0;
  background: transparent;
  box-shadow: none !important;
}

body.oa-lite-theme .ant-card {
  overflow: hidden;
}

body.oa-lite-theme .ant-card-head,
body.oa-lite-theme .ant-table-thead > tr > th,
body.oa-lite-theme .vxe-header--row {
  background: transparent !important;
}

body.oa-lite-theme .ant-card-head {
  min-height: 58px;
  padding-inline: 0;
  border-bottom-color: var(--oa-shell-border);
}

body.oa-lite-theme .ant-card-head-title,
body.oa-lite-theme .ant-table-thead > tr > th,
body.oa-lite-theme .vxe-header--column {
  color: var(--oa-ink) !important;
  font-size: 13px;
  font-weight: 600;
}

body.oa-lite-theme .ant-card-body {
  padding: 18px 0 0;
}

body.oa-lite-theme .ant-tag {
  border-radius: 0;
  border-color: var(--oa-shell-border) !important;
  font-weight: 600;
  background: transparent !important;
}

body.oa-lite-theme .ant-tag-processing,
body.oa-lite-theme .ant-tag-blue {
  color: var(--oa-info-text) !important;
  border-color: color-mix(in srgb, var(--oa-info-text) 34%, var(--oa-shell-border)) !important;
}

body.oa-lite-theme .ant-tag-success,
body.oa-lite-theme .ant-tag-green {
  color: var(--oa-success-text) !important;
  border-color: color-mix(in srgb, var(--oa-success-text) 34%, var(--oa-shell-border)) !important;
}

body.oa-lite-theme .ant-tag-warning,
body.oa-lite-theme .ant-tag-orange,
body.oa-lite-theme .ant-tag-gold {
  color: var(--oa-warning-text) !important;
  background: var(--oa-warning-soft) !important;
}

body.oa-lite-theme .ant-tag-error,
body.oa-lite-theme .ant-tag-red,
body.oa-lite-theme .ant-tag-volcano {
  color: var(--oa-danger-text) !important;
  background: var(--oa-danger-soft) !important;
}

body.oa-lite-theme .ant-table-tbody > tr > td,
body.oa-lite-theme .ant-descriptions .ant-descriptions-item-label,
body.oa-lite-theme .ant-descriptions .ant-descriptions-item-content,
body.oa-lite-theme .ant-form-item-label > label,
body.oa-lite-theme .vxe-body--column {
  color: var(--oa-ink) !important;
}

body.oa-lite-theme .ant-table-tbody > tr > td,
body.oa-lite-theme .ant-table-thead > tr > th {
  border-bottom-color: var(--oa-shell-border) !important;
}

body.oa-lite-theme .ant-form-item-label > label {
  font-size: 13px;
  font-weight: 600;
}

body.oa-lite-theme .ant-form-item-extra,
body.oa-lite-theme .ant-form-item-explain,
body.oa-lite-theme .ant-empty-description,
body.oa-lite-theme .ant-descriptions .ant-descriptions-item-label {
  color: var(--oa-ink-soft) !important;
}

body.oa-lite-theme .vxe-grid--toolbar-wrapper,
body.oa-lite-theme .vxe-table--header-wrapper,
body.oa-lite-theme .vxe-table--body-wrapper,
body.oa-lite-theme .vxe-table--main-wrapper,
body.oa-lite-theme .vxe-table--render-wrapper {
  border-color: var(--oa-shell-border) !important;
}

/*
 * Vxe 4 synchronizes header/body scrolling through native inner scrollers,
 * hides their browser scrollbars, and renders one dedicated virtual scrollbar.
 * The theme's global scrollbar rule must not reveal those inner scrollers.
 */
body.oa-lite-theme .vxe-grid--table-wrapper {
  overflow: hidden !important;
}

body.oa-lite-theme .vxe-table--header-wrapper,
body.oa-lite-theme .vxe-table--body-wrapper,
body.oa-lite-theme .vxe-table--footer-wrapper,
body.oa-lite-theme .vxe-table--fixed-left-body-wrapper,
body.oa-lite-theme .vxe-table--fixed-right-body-wrapper {
  overflow: hidden !important;
  scrollbar-width: none !important;
}

body.oa-lite-theme .vxe-table--header-inner-wrapper,
body.oa-lite-theme .vxe-table--body-inner-wrapper,
body.oa-lite-theme .vxe-table--footer-inner-wrapper {
  scrollbar-width: none !important;
  -ms-overflow-style: none;
}

body.oa-lite-theme .vxe-table--header-inner-wrapper::-webkit-scrollbar,
body.oa-lite-theme .vxe-table--body-inner-wrapper::-webkit-scrollbar,
body.oa-lite-theme .vxe-table--footer-inner-wrapper::-webkit-scrollbar {
  display: none !important;
  width: 0 !important;
  height: 0 !important;
}

body.oa-lite-theme .vxe-toolbar {
  padding: 14px 18px 10px;
}

body.oa-lite-theme .vxe-toolbar .vxe-button,
body.oa-lite-theme .vxe-toolbar .vxe-button.type--button {
  min-height: 38px;
  border-radius: 0;
  border-color: var(--oa-shell-border);
  background: transparent;
  color: var(--oa-ink);
  box-shadow: none;
}

body.oa-lite-theme .vxe-toolbar .vxe-button.type--button:hover,
body.oa-lite-theme .vxe-toolbar .vxe-button:not(.type--submit):hover {
  border-color: var(--oa-accent);
  color: var(--oa-accent);
}

body.oa-lite-theme .vxe-toolbar .vxe-button.type--submit,
body.oa-lite-theme .vxe-toolbar .vxe-button.theme--primary {
  border-color: var(--oa-accent);
  background: var(--oa-accent);
  color: var(--oa-accent-contrast);
}

body.oa-lite-theme .vxe-toolbar .vxe-button.type--submit:hover,
body.oa-lite-theme .vxe-toolbar .vxe-button.theme--primary:hover {
  border-color: var(--oa-accent-strong);
  background: var(--oa-accent-strong);
  color: var(--oa-accent-contrast);
}

body.oa-lite-theme .vxe-grid .vxe-grid--toolbar-wrapper {
  border-bottom: 1px solid var(--oa-shell-border) !important;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--oa-shell-surface) 96%, transparent),
    color-mix(in srgb, var(--oa-shell-surface-muted) 88%, transparent)
  );
}

body.oa-lite-theme .vxe-grid .vxe-table--body tr.row--hover,
body.oa-lite-theme .vxe-grid .vxe-body--row.row--hover {
  background: color-mix(in srgb, var(--oa-accent-soft) 52%, var(--oa-shell-surface))
    !important;
}

body.oa-lite-theme .vxe-pager {
  color: var(--oa-ink);
  background: var(--oa-shell-surface);
}

body.oa-lite-theme .ant-modal-mask {
  background: rgb(9 17 30 / 42%) !important;
  backdrop-filter: blur(4px);
}

body.oa-lite-theme-dark .ant-modal-mask {
  background: rgb(5 10 18 / 68%) !important;
  backdrop-filter: none;
}

body.oa-lite-theme .ant-modal-content,
body.oa-lite-theme .ant-modal-header {
  background: var(--oa-shell-surface) !important;
}

body.oa-lite-theme .ant-modal-content {
  border: 1px solid var(--oa-shell-border);
  border-radius: 0 !important;
  box-shadow: 0 12px 32px rgb(15 23 42 / 6%) !important;
}

body.oa-lite-theme .ant-modal-header {
  padding: 18px 24px 12px;
  border-bottom: 1px solid var(--oa-shell-border);
  border-radius: 0 !important;
}

body.oa-lite-theme .ant-modal-title,
body.oa-lite-theme .ant-modal-close,
body.oa-lite-theme .ant-modal-close-x,
body.oa-lite-theme .ant-modal-body {
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-dark .oa-lite-stat-pillar {
  border-color: var(--oa-shell-border) !important;
  background: linear-gradient(
    180deg,
    var(--oa-shell-surface) 0%,
    var(--oa-shell-surface-muted) 100%
  ) !important;
  box-shadow: none !important;
}

body.oa-lite-theme-dark .oa-lite-stat-item + .oa-lite-stat-item {
  border-left-color: color-mix(in srgb, var(--oa-shell-border) 76%, transparent) !important;
}

body.oa-lite-theme-dark .oa-lite-stat-item:hover {
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--oa-accent-soft) 14%, var(--oa-shell-surface)) 0%,
    color-mix(in srgb, var(--oa-accent-soft) 22%, var(--oa-shell-surface-muted)) 100%
  ) !important;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--oa-accent) 18%, transparent)
    !important;
}

body.oa-lite-theme-dark .oa-lite-stat-icon {
  border-color: color-mix(in srgb, var(--oa-shell-border) 78%, transparent) !important;
  background: linear-gradient(
    180deg,
    color-mix(in srgb, var(--oa-shell-surface-muted) 92%, black) 0%,
    color-mix(in srgb, var(--oa-shell-surface) 92%, black) 100%
  ) !important;
  color: var(--oa-ink-soft) !important;
  box-shadow: none !important;
}

body.oa-lite-theme-dark .oa-lite-settings-modal .ant-modal-content,
body.oa-lite-theme-dark .oa-lite-settings-modal .ant-modal-header,
body.oa-lite-theme-dark .oa-lite-settings-modal .ant-modal-body {
  background: var(--oa-shell-surface) !important;
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-dark .oa-lite-settings-modal .ant-modal-content {
  border-color: var(--oa-shell-border) !important;
  box-shadow: none !important;
}

body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-sidebar,
body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-content-head {
  border-color: var(--oa-shell-border) !important;
}

body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-section {
  border-color: var(--oa-shell-border) !important;
  background: linear-gradient(
    180deg,
    var(--oa-shell-surface) 0%,
    var(--oa-shell-surface-muted) 100%
  ) !important;
}

body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-row,
body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-choice {
  border-color: color-mix(in srgb, var(--oa-shell-border) 88%, transparent) !important;
  background: color-mix(in srgb, var(--oa-shell-surface-muted) 72%, var(--oa-shell-surface))
    !important;
}

body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-row:hover,
body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-choice:hover,
body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-choice.active {
  border-color: color-mix(in srgb, var(--oa-accent) 26%, var(--oa-shell-border)) !important;
  background: color-mix(in srgb, var(--oa-accent-soft) 18%, var(--oa-shell-surface-muted))
    !important;
}

body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-sidebar-tag,
body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-row-meta,
body.oa-lite-theme-dark .oa-lite-settings-modal .oa-lite-settings-choice-state {
  background: color-mix(in srgb, var(--oa-accent-soft) 24%, var(--oa-shell-surface))
    !important;
  border-color: color-mix(in srgb, var(--oa-accent) 20%, var(--oa-shell-border)) !important;
}

body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-menu-item,
body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-menu-item a,
body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-sub-menu-content {
  background: color-mix(in srgb, var(--oa-shell-surface) 94%, black) !important;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 70%, transparent)
    !important;
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-menu-item > *,
body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-sub-menu-content > * {
  background: transparent !important;
}

body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-menu-item.is-active a,
body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-menu-item.is-active,
body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-sub-menu-content.is-active {
  background: color-mix(in srgb, var(--oa-accent-soft) 28%, var(--oa-shell-surface))
    !important;
  color: var(--oa-accent) !important;
}

body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-menu-item.is-active > * {
  background: transparent !important;
}

body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-menu-item:hover,
body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-menu-item a:hover,
body.oa-lite-theme-dark .oa-lite-unified-sidebar .vben-sub-menu-content:hover {
  background: color-mix(in srgb, var(--oa-shell-surface-muted) 88%, black) !important;
}

body.oa-lite-theme .ant-dropdown,
body.oa-lite-theme .ant-select-dropdown {
  border: 1px solid var(--oa-shell-border) !important;
  border-radius: 0 !important;
  background: var(--oa-shell-surface) !important;
  box-shadow: 0 10px 24px rgb(15 23 42 / 6%) !important;
}

body.oa-lite-theme .ant-pagination .ant-pagination-item,
body.oa-lite-theme .ant-pagination .ant-pagination-prev .ant-pagination-item-link,
body.oa-lite-theme .ant-pagination .ant-pagination-next .ant-pagination-item-link,
body.oa-lite-theme .ant-pagination .ant-select-selector {
  border-color: var(--oa-shell-border) !important;
  color: var(--oa-ink) !important;
  background: var(--oa-shell-surface) !important;
}

body.oa-lite-theme .ant-pagination .ant-pagination-item-active {
  border-color: var(--oa-accent) !important;
  background: transparent !important;
}

body.oa-lite-theme .ant-pagination .ant-pagination-item-active a {
  color: var(--oa-accent) !important;
}

body.oa-lite-theme .oa-workspace-page {
  display: flex;
  min-height: 100%;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  flex-direction: column;
  gap: 18px;
}

body.oa-lite-theme .oa-workspace-page .oa-workspace-panel-body {
  min-height: 0;
  min-width: 0;
  padding-top: 8px;
}

body.oa-lite-theme .oa-workspace-page .vxe-grid--form-wrapper {
  padding-bottom: 4px;
}

body.oa-lite-theme .oa-workspace-page .vxe-grid--toolbar-wrapper {
  padding-bottom: 4px;
}

body.oa-lite-theme .oa-workspace-page .vxe-table--header-wrapper,
body.oa-lite-theme .oa-workspace-page .vxe-table--body-wrapper {
  font-size: 13px;
}

body.oa-lite-theme .oa-workspace-page .vxe-body--column,
body.oa-lite-theme .oa-workspace-page .vxe-header--column {
  padding-inline: 10px;
}

body.oa-lite-theme .oa-workspace-page .vxe-table--body-wrapper {
  min-height: calc(100vh - 456px);
  max-height: calc(100vh - 456px);
}

body.oa-lite-theme .oa-workspace-page .vxe-pager {
  padding-top: 4px;
}

body.oa-lite-theme .oa-workspace-hero {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid var(--oa-shell-border);
  border-radius: 0;
  background: transparent;
  padding: 4px 0 18px;
}

body.oa-lite-theme .oa-workspace-hero-main {
  min-width: 0;
}

@media (max-width: 1440px) {
  body.oa-lite-theme .oa-workspace-page .vxe-toolbar {
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 0 8px;
  }

  body.oa-lite-theme .oa-workspace-page .vxe-buttons--wrapper,
  body.oa-lite-theme .oa-workspace-page .vxe-tools--wrapper,
  body.oa-lite-theme .oa-workspace-page .vxe-tools--operate {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0;
    padding: 0;
  }

  body.oa-lite-theme .oa-workspace-page .vben-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  body.oa-lite-theme .oa-workspace-page .vxe-table--body-wrapper {
    min-height: calc(100vh - 492px);
    max-height: calc(100vh - 492px);
  }

  body.oa-lite-theme .oa-workspace-page .vxe-pager--wrapper {
    flex-wrap: wrap;
    gap: 10px 14px;
    justify-content: flex-end;
  }
}

@media (max-width: 1320px) {
  body.oa-lite-theme .oa-workspace-page .vben-form {
    grid-template-columns: 1fr;
  }

  body.oa-lite-theme .oa-workspace-page .vxe-table--body-wrapper {
    min-height: calc(100vh - 548px);
    max-height: calc(100vh - 548px);
  }
}

body.oa-lite-theme .oa-workspace-eyebrow {
  margin-bottom: 8px;
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

body.oa-lite-theme .oa-workspace-heading {
  margin: 0;
  color: var(--oa-ink);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.2;
}

body.oa-lite-theme .oa-workspace-copy {
  max-width: 72ch;
  margin: 10px 0 0;
  color: var(--oa-ink-soft);
  font-size: 14px;
  line-height: 1.7;
}

body.oa-lite-theme .oa-workspace-metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0;
  min-width: min(100%, 420px);
}

body.oa-lite-theme .oa-workspace-metric {
  min-width: 132px;
  padding: 0 18px;
  border-right: 1px solid color-mix(in srgb, var(--oa-shell-border) 72%, transparent);
  border-radius: 0;
  background: transparent;
}

body.oa-lite-theme .oa-workspace-metric:first-child {
  padding-left: 0;
}

body.oa-lite-theme .oa-workspace-metric:last-child {
  padding-right: 0;
  border-right: 0;
}

body.oa-lite-theme .oa-workspace-metric-label {
  color: var(--oa-ink-faint);
  font-size: 11px;
  font-weight: 600;
}

body.oa-lite-theme .oa-workspace-metric-value {
  margin-top: 6px;
  color: var(--oa-ink);
  font-size: 16px;
  font-weight: 600;
  line-height: 1.25;
  font-variant-numeric: tabular-nums;
}

body.oa-lite-theme .oa-workspace-panel {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  border: 0;
  border-radius: 0;
  background: transparent;
}

body.oa-lite-theme .oa-workspace-panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 0 0 14px;
  border-bottom: 1px solid var(--oa-shell-border);
  background: transparent;
}

body.oa-lite-theme .oa-workspace-panel:has(.oa-workspace-panel-title) {
  .oa-workspace-panel-header {
    display: none;
  }

  .oa-workspace-panel-body {
    padding-top: 0;
  }
}

body.oa-lite-theme .oa-workspace-panel-title {
  margin: 0;
  color: var(--oa-ink);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.3;
}

body.oa-lite-theme .oa-workspace-panel-desc {
  margin-top: 6px;
  color: var(--oa-ink-soft);
  font-size: 13px;
  line-height: 1.6;
}

body.oa-lite-theme .oa-workspace-panel-body {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  padding: 16px 0 0;
}

body.oa-lite-theme .oa-workspace-section-grid {
  display: grid;
  grid-template-columns: minmax(220px, 280px) minmax(0, 1fr);
  width: 100%;
  min-width: 0;
  max-width: 100%;
  gap: 18px;
  min-height: 0;
}

/*
 * Management pages share the approval-center shell. Keep the page boundary,
 * table boundary, and scroll boundary explicit so every BPM/System screen
 * inherits the same visual rhythm without copying page-local CSS.
 */
body.oa-lite-theme .oa-lite-unified-content-shell.is-management {
  --vben-content-height: 100%;
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  background: var(--oa-shell-bg);
}

body.oa-lite-theme .oa-lite-unified-content.is-management {
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

body.oa-lite-theme .oa-lite-unified-main.is-management {
  min-height: 0;
}

body.oa-lite-theme .oa-lite-unified-content-shell.is-management .oa-page-shell {
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-page-header {
  flex: none;
  min-height: 68px;
  padding: 18px 24px 14px;
  border-bottom-color: var(--oa-shell-border);
  background: var(--oa-shell-bg);
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-page-title {
  margin: 0;
  color: var(--oa-ink);
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.015em;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-page-description {
  margin-top: 6px;
  color: var(--oa-ink-soft);
  font-size: 13px;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-page-content {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: auto;
  padding: 18px 24px 24px;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-workspace-page {
  display: flex;
  min-width: 0;
  min-height: 0;
  height: 100%;
  flex: 1 1 auto;
  overflow: hidden;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-workspace-section-grid {
  height: 100%;
  min-height: 0;
  flex: 1 1 auto;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-workspace-panel {
  display: flex;
  min-height: 0;
  height: 100%;
  flex: 1 1 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--oa-shell-border);
  border-radius: var(--oa-radius-lg);
  background: var(--oa-shell-surface);
  box-shadow: 0 1px 2px rgb(15 23 42 / 2%);
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-workspace-section-grid
  > .oa-workspace-panel {
  height: auto;
  align-self: stretch;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-workspace-panel-header {
  flex: none;
  padding: 16px 18px 12px;
  border-bottom-color: var(--oa-shell-border);
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-workspace-panel-body {
  display: flex;
  min-height: 0;
  flex: 1 1 auto;
  flex-direction: column;
  overflow: hidden;
  padding: 0 16px 14px;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .oa-workspace-panel:has(.oa-workspace-panel-title)
  .oa-workspace-panel-body {
  padding-top: 0;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-grid {
  width: 100%;
  min-width: 0;
  min-height: 0;
  height: 100% !important;
  border: 0 !important;
  border-radius: var(--oa-radius-md) !important;
  background: transparent;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-grid--layout-body-content-wrapper {
  min-height: 0;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-table--body-wrapper {
  min-height: 0 !important;
  max-height: none !important;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-grid--toolbar-wrapper {
  flex: none;
  padding: 12px 0 10px;
  border-bottom: 1px solid var(--oa-shell-border) !important;
  background: transparent;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-toolbar {
  min-width: 0;
  padding: 0;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-table--header-wrapper {
  background: var(--oa-shell-surface-muted) !important;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-header--column {
  height: 42px;
  color: var(--oa-ink-soft) !important;
  font-size: 12px;
  font-weight: 650;
  letter-spacing: 0.01em;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-body--row {
  transition: background-color 0.16s ease;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-body--column {
  height: 48px;
  color: var(--oa-ink) !important;
  font-size: 13px;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-body--row.row--hover,
body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-body--row:hover {
  background: color-mix(in srgb, var(--oa-accent-soft) 52%, var(--oa-shell-surface)) !important;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .vxe-grid--pager-wrapper {
  flex: none;
  padding-top: 10px;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-card {
  border: 1px solid var(--oa-shell-border) !important;
  border-radius: var(--oa-radius-lg) !important;
  background: var(--oa-shell-surface) !important;
  box-shadow: 0 1px 2px rgb(15 23 42 / 2%) !important;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-card-head {
  min-height: 54px;
  padding-inline: 18px;
  border-bottom-color: var(--oa-shell-border) !important;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-card-body {
  padding: 18px;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-table-wrapper {
  min-width: 0;
  overflow: hidden;
  border: 1px solid var(--oa-shell-border);
  border-radius: var(--oa-radius-md);
  background: var(--oa-shell-surface);
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-table-thead
  > tr
  > th {
  background: var(--oa-shell-surface-muted) !important;
  color: var(--oa-ink-soft) !important;
  font-size: 12px;
  font-weight: 650;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-table-tbody
  > tr
  > td {
  min-width: 0;
  color: var(--oa-ink) !important;
  font-size: 13px;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-table-tbody
  > tr:hover
  > td {
  background: color-mix(in srgb, var(--oa-accent-soft) 52%, var(--oa-shell-surface)) !important;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-input,
body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-input-affix-wrapper,
body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-picker,
body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-select-selector,
body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-btn {
  border-radius: var(--oa-radius-sm) !important;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-form-item-label
  > label {
  color: var(--oa-ink-soft) !important;
  font-size: 12px;
  font-weight: 600;
}

body.oa-lite-theme
  .oa-lite-unified-content-shell.is-management
  .ant-modal-content {
  overflow: hidden;
  border-radius: var(--oa-radius-lg) !important;
}

body.oa-lite-theme
  .oa-lite-unified-main.is-management
  .oa-lite-unified-sidebar .vben-menu-item a,
body.oa-lite-theme
  .oa-lite-unified-main.is-management
  .oa-lite-unified-sidebar .vben-sub-menu-content {
  margin: 2px 10px;
  border-radius: var(--oa-radius-md);
}

body.oa-lite-theme .oa-lite-unified-topnav-item:focus {
  outline: none;
}

body.oa-lite-theme .oa-lite-unified-topnav-item:focus-visible {
  outline: none;
  box-shadow: var(--oa-focus-ring);
}

body.oa-lite-theme .oa-filter-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  padding: 14px 0;
  border-top: 1px solid var(--oa-shell-border);
  border-bottom: 1px solid var(--oa-shell-border);
  border-left: 0;
  border-right: 0;
  border-radius: 0;
  background: transparent;
}

@media (max-width: 1200px) {
  body.oa-lite-theme .oa-workspace-hero,
  body.oa-lite-theme .oa-workspace-section-grid {
    grid-template-columns: 1fr;
    flex-direction: column;
  }

  body.oa-lite-theme .oa-workspace-metrics {
    width: 100%;
    min-width: 0;
  }
}
</style>
