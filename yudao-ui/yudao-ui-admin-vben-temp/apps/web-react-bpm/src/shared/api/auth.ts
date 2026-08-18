import { http } from '@/shared/api/http';

export interface LoginParams {
  captchaVerification?: string;
  password: string;
  socialCode?: string;
  socialState?: string;
  socialType?: number;
  username: string;
}

export interface LoginResult {
  accessToken: string;
  expiresTime: number;
  refreshToken: string;
  userId: number;
}

export interface PermissionInfo {
  menus: Array<Record<string, unknown>>;
  permissions: string[];
  roles: string[];
  user: {
    avatar?: string;
    deptName?: string;
    id: number;
    nickname: string;
  };
}

export interface TenantOption {
  id: number;
  name: string;
}

export interface CaptchaPayload {
  captchaVerification: string;
}

export interface CaptchaChallenge {
  jigsawImageBase64?: string;
  originalImageBase64?: string;
  pointJson?: string;
  secretKey?: string;
  token?: string;
  captchaType?: string;
  [key: string]: unknown;
}

interface CaptchaResponse<T> {
  repCode: string;
  repData?: T;
  repMsg?: string;
  success?: boolean;
}

export interface SmsSendParams {
  captchaVerification?: string;
  mobile: string;
  scene: number;
}

export interface SmsLoginParams {
  code: string;
  mobile: string;
}

export interface SocialLoginParams {
  code: string;
  state: string;
  type: number;
}

export function login(data: LoginParams) {
  return http.post<LoginResult>('/system/auth/login', data);
}

export function getPermissionInfo() {
  return http.get<PermissionInfo>('/system/auth/get-permission-info');
}

export function getTenantSimpleList() {
  return http.get<TenantOption[]>('/system/tenant/simple-list');
}

export function getTenantByWebsite(website: string) {
  return http.get<TenantOption | null>('/system/tenant/get-by-website', {
    params: { website },
  });
}

export function getCaptcha(data: Record<string, unknown>) {
  return fetchCaptcha<CaptchaChallenge>('/system/captcha/get', data);
}

export function checkCaptcha(data: Record<string, unknown>) {
  return fetchCaptcha<CaptchaPayload>('/system/captcha/check', data);
}

export function sendSmsCode(data: SmsSendParams) {
  return http.post<boolean>('/system/auth/send-sms-code', data);
}

export function smsLogin(data: SmsLoginParams) {
  return http.post<LoginResult>('/system/auth/sms-login', data);
}

export function socialAuthRedirect(type: number, redirectUri: string) {
  return http.get<string>('/system/auth/social-auth-redirect', {
    params: {
      redirectUri,
      type,
    },
  });
}

export function socialLogin(data: SocialLoginParams) {
  return http.post<LoginResult>('/system/auth/social-login', data);
}

export function kodSsoExchange(code: string) {
  return http.post<LoginResult>(
    `/system/auth/kod-sso/exchange?code=${encodeURIComponent(code)}`,
  );
}

async function fetchCaptcha<T>(path: string, data: Record<string, unknown>) {
  const response = await fetch(`/admin-api${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });

  if (!response.ok) {
    throw new Error(`验证码接口请求失败：${response.status}`);
  }

  const result = (await response.json()) as CaptchaResponse<T>;
  if (result.repCode !== '0000') {
    throw new Error(result.repMsg || '验证码接口返回失败');
  }
  return result.repData as T;
}
