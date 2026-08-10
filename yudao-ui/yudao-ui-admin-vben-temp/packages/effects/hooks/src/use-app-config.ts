import type {
  ApplicationConfig,
  VbenAdminProAppConfigRaw,
} from '@vben/types/global';

/**
 * 由 vite-inject-app-config 注入的全局配置
 */
export function useAppConfig(
  env: Record<string, any>,
  isProduction: boolean,
): ApplicationConfig {
  // 生产环境下，直接使用 window._VBEN_ADMIN_PRO_APP_CONF_ 全局变量
  const config = isProduction
    ? window._VBEN_ADMIN_PRO_APP_CONF_
    : (env as VbenAdminProAppConfigRaw);
  const runtimeConfig = isProduction ? window.__OA_RUNTIME_CONFIG__ : undefined;

  const {
    VITE_GLOB_API_URL,
    VITE_GLOB_FILE_PREVIEW_URL,
    VITE_GLOB_FILE_PREVIEW_FETCH_ORIGIN,
    VITE_GLOB_AUTH_DINGDING_CORP_ID,
    VITE_GLOB_AUTH_DINGDING_CLIENT_ID,
  } = config;
  const runtimeApiEncrypt = runtimeConfig?.apiEncrypt;

  const applicationConfig: ApplicationConfig = {
    apiURL: VITE_GLOB_API_URL,
    filePreviewURL:
      runtimeConfig?.filePreviewURL ||
      (isProduction ? '' : VITE_GLOB_FILE_PREVIEW_URL || ''),
    filePreviewFetchOrigin:
      runtimeConfig?.filePreviewFetchOrigin ||
      (isProduction ? '' : VITE_GLOB_FILE_PREVIEW_FETCH_ORIGIN || ''),
    captchaEnable:
      runtimeConfig?.captchaEnable ??
      (isProduction
        ? false
        : import.meta.env.VITE_APP_CAPTCHA_ENABLE === 'true'),
    intranetDeployment:
      runtimeConfig?.intranetDeployment ??
      (isProduction
        ? false
        : import.meta.env.VITE_INTRANET_DEPLOYMENT === 'true'),
    apiEncrypt: {
      enable:
        runtimeApiEncrypt?.enable ??
        (isProduction
          ? false
          : config.VITE_APP_API_ENCRYPT_ENABLE === 'true'),
      header:
        runtimeApiEncrypt?.header ||
        (isProduction ? '' : config.VITE_APP_API_ENCRYPT_HEADER || ''),
      algorithm:
        runtimeApiEncrypt?.algorithm ||
        (isProduction ? '' : config.VITE_APP_API_ENCRYPT_ALGORITHM || 'AES'),
      requestKey:
        runtimeApiEncrypt?.requestKey ||
        (isProduction ? '' : config.VITE_APP_API_ENCRYPT_REQUEST_KEY || ''),
      responseKey:
        runtimeApiEncrypt?.responseKey ||
        (isProduction ? '' : config.VITE_APP_API_ENCRYPT_RESPONSE_KEY || ''),
    },
    storeSecureKey:
      runtimeConfig?.storeSecureKey ||
      (isProduction ? '' : config.VITE_APP_STORE_SECURE_KEY || ''),
    baiduMapKey:
      runtimeConfig?.baiduMapKey ||
      (isProduction ? '' : config.VITE_BAIDU_MAP_KEY || ''),
    baiduAnalyticsCode:
      runtimeConfig?.baiduAnalyticsCode ||
      (isProduction ? '' : config.VITE_APP_BAIDU_CODE || ''),
    auth: {},
  };
  if (VITE_GLOB_AUTH_DINGDING_CORP_ID && VITE_GLOB_AUTH_DINGDING_CLIENT_ID) {
    applicationConfig.auth.dingding = {
      clientId: VITE_GLOB_AUTH_DINGDING_CLIENT_ID,
      corpId: VITE_GLOB_AUTH_DINGDING_CORP_ID,
    };
  }

  return applicationConfig;
}

export function isTenantEnable(): boolean {
  return import.meta.env.VITE_APP_TENANT_ENABLE === 'true';
}

export function isCaptchaEnable(): boolean {
  return (
    window.__OA_RUNTIME_CONFIG__?.captchaEnable ??
    (import.meta.env.PROD
      ? false
      : import.meta.env.VITE_APP_CAPTCHA_ENABLE === 'true')
  );
}

export function isIntranetDeployment(): boolean {
  return (
    window.__OA_RUNTIME_CONFIG__?.intranetDeployment ??
    (import.meta.env.PROD
      ? false
      : import.meta.env.VITE_INTRANET_DEPLOYMENT === 'true')
  );
}

export function isDocAlertEnable(): boolean {
  return false;
}
