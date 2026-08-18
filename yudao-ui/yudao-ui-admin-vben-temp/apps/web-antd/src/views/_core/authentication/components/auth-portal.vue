<script lang="ts" setup>
import type { AuthApi } from '#/api/core/auth';

import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Verification } from '@vben/common-ui';
import { isCaptchaEnable, isTenantEnable } from '@vben/hooks';
import { IconifyIcon } from '@vben/icons';
import { useAccessStore } from '@vben/stores';

import { message } from 'ant-design-vue';

import {
  checkCaptcha,
  getCaptcha,
  getTenantByWebsite,
  getTenantSimpleList,
  sendSmsCode,
  socialAuthRedirect,
} from '#/api/core/auth';
import { useAuthStore } from '#/store';

import AntigravityBackground from './antigravity-background.vue';

const props = withDefaults(
  defineProps<{
    initialMode?: 'account' | 'mobile';
  }>(),
  {
    initialMode: 'account',
  },
);

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const accessStore = useAccessStore();
const tenantEnable = isTenantEnable();
const captchaEnable = isCaptchaEnable();

const verifyRef = ref();
const loginMode = ref<'account' | 'mobile'>(props.initialMode);
const tenantList = ref<AuthApi.TenantResult[]>([]);
const countdown = ref(0);
const tenantLoading = ref(false);
const sendingCode = ref(false);
const loading = computed(
  () => authStore.loginLoading || sendingCode.value || tenantLoading.value,
);

const accountForm = reactive({
  password: import.meta.env.VITE_APP_DEFAULT_PASSWORD ?? '',
  remember: true,
  tenantId: '',
  username: import.meta.env.VITE_APP_DEFAULT_USERNAME ?? '',
});

const mobileForm = reactive({
  code: '',
  mobile: '',
  tenantId: '',
});

const errors = reactive({
  account: '',
  mobile: '',
});

const tilt = reactive({
  rotateX: 0,
  rotateY: 0,
});
let targetRotateX = 0;
let targetRotateY = 0;
let animationFrameId = 0;
let countdownTimer: number | null = null;

watch(
  () => props.initialMode,
  (value) => {
    loginMode.value = value;
  },
);

function setTenantId(value: string) {
  if (!value) {
    return;
  }
  const id = Number(value);
  accountForm.tenantId = value;
  mobileForm.tenantId = value;
  accessStore.setTenantId(Number.isNaN(id) ? null : id);
}

async function fetchTenantList() {
  if (!tenantEnable) {
    return;
  }
  try {
    tenantLoading.value = true;
    const websiteTenantPromise = getTenantByWebsite(window.location.hostname);
    tenantList.value = await getTenantSimpleList();

    let tenantId: null | number = null;
    const websiteTenant = await websiteTenantPromise.catch(() => null);
    if (websiteTenant?.id) {
      tenantId = websiteTenant.id;
    }
    if (!tenantId && accessStore.tenantId) {
      tenantId = accessStore.tenantId;
    }
    if (!tenantId && tenantList.value[0]?.id) {
      tenantId = tenantList.value[0].id;
    }
    if (tenantId) {
      setTenantId(String(tenantId));
    }
  } catch (error) {
    console.error('获取租户列表失败', error);
  } finally {
    tenantLoading.value = false;
  }
}

function validateAccountForm() {
  if (tenantEnable && !accountForm.tenantId) {
    errors.account = '请选择租户';
    return false;
  }
  if (!accountForm.username || !accountForm.password) {
    errors.account = '请输入账号和密码';
    return false;
  }
  errors.account = '';
  return true;
}

function validateMobileForm() {
  if (tenantEnable && !mobileForm.tenantId) {
    errors.mobile = '请选择租户';
    return false;
  }
  if (!/^1[3-9]\d{9}$/.test(mobileForm.mobile)) {
    errors.mobile = '请输入正确的手机号';
    return false;
  }
  if (!mobileForm.code) {
    errors.mobile = '请输入验证码';
    return false;
  }
  errors.mobile = '';
  return true;
}

async function submitAccountLogin(captchaVerification?: string) {
  await authStore.authLogin('username', {
    password: accountForm.password,
    username: accountForm.username,
    tenantId: accountForm.tenantId || undefined,
    ...(captchaVerification ? { captchaVerification } : {}),
  });
}

async function handleAccountLogin() {
  if (!validateAccountForm()) {
    return;
  }
  if (captchaEnable) {
    verifyRef.value?.show();
    return;
  }
  try {
    await submitAccountLogin();
  } catch (error: any) {
    errors.account = error?.message || '登录失败，请稍后重试';
  }
}

async function handleVerifySuccess({
  captchaVerification,
}: {
  captchaVerification: string;
}) {
  try {
    await submitAccountLogin(captchaVerification);
  } catch (error: any) {
    errors.account = error?.message || '登录失败，请稍后重试';
  }
}

async function handleSendCode() {
  if (tenantEnable && !mobileForm.tenantId) {
    errors.mobile = '请选择租户';
    return;
  }
  if (!/^1[3-9]\d{9}$/.test(mobileForm.mobile)) {
    errors.mobile = '请输入正确的手机号';
    return;
  }
  try {
    sendingCode.value = true;
    errors.mobile = '';
    await sendSmsCode({ mobile: mobileForm.mobile, scene: 21 });
    message.success('验证码发送成功');
    countdown.value = 60;
    countdownTimer = window.setInterval(() => {
      if (countdown.value <= 1) {
        if (countdownTimer) {
          window.clearInterval(countdownTimer);
          countdownTimer = null;
        }
        countdown.value = 0;
        return;
      }
      countdown.value -= 1;
    }, 1000);
  } catch (error: any) {
    errors.mobile = error?.message || '发送验证码失败';
  } finally {
    sendingCode.value = false;
  }
}

async function handleMobileLogin() {
  if (!validateMobileForm()) {
    return;
  }
  try {
    await authStore.authLogin('mobile', {
      code: mobileForm.code,
      mobile: mobileForm.mobile,
      tenantId: mobileForm.tenantId || undefined,
    });
  } catch (error: any) {
    errors.mobile = error?.message || '登录失败，请检查短信验证码';
  }
}

async function handleSocialLogin(type: number) {
  try {
    const redirect = route.query?.redirect || '/';
    const redirectUri = `${location.origin}/auth/social-login?${encodeURIComponent(
      `type=${type}&redirect=${redirect}`,
    )}`;
    window.location.href = await socialAuthRedirect(type, redirectUri);
  } catch (error: any) {
    message.error(error?.message || '无法发起第三方登录');
  }
}

function goForgetPassword() {
  router.push('/auth/forget-password');
}

function syncTilt(event: MouseEvent) {
  const { innerHeight, innerWidth } = window;
  const xIndex = (event.clientX / innerWidth - 0.5) * 2;
  const yIndex = -(event.clientY / innerHeight - 0.5) * 2;
  targetRotateX = yIndex * 9;
  targetRotateY = xIndex * 9;
}

function animateTilt() {
  tilt.rotateX += (targetRotateX - tilt.rotateX) * 0.05;
  tilt.rotateY += (targetRotateY - tilt.rotateY) * 0.05;
  animationFrameId = window.requestAnimationFrame(animateTilt);
}

onMounted(async () => {
  await fetchTenantList();
  window.addEventListener('mousemove', syncTilt);
  animateTilt();
  await nextTick();
});

onBeforeUnmount(() => {
  window.cancelAnimationFrame(animationFrameId);
  window.removeEventListener('mousemove', syncTilt);
  if (countdownTimer) {
    window.clearInterval(countdownTimer);
    countdownTimer = null;
  }
});
</script>

<template>
  <div class="auth-portal">
    <AntigravityBackground />
    <div class="auth-portal__inner">
      <section class="auth-shell">
        <aside class="auth-shell__intro">
          <div
            class="auth-intro-card"
            :style="{
              transform: `perspective(1200px) rotateX(${(tilt.rotateX * 0.45).toFixed(2)}deg) rotateY(${(tilt.rotateY * 0.45).toFixed(2)}deg) translateZ(4px)`,
            }"
          >
            <div class="auth-intro-card__badge">
              <span class="auth-intro-card__badge-icon">
                <IconifyIcon icon="carbon:task-asset-view" />
              </span>
              <span>OA 审批工作台</span>
            </div>
            <h1>工作台入口</h1>
          </div>
        </aside>

        <section class="auth-panel">
          <div class="auth-panel__header">
            <div class="auth-panel__logo">
              <IconifyIcon icon="solar:shield-keyhole-outline" />
            </div>
            <div>
              <h2>进入工作台</h2>
            </div>
          </div>

          <div class="auth-mode-switch">
            <button
              :class="{ active: loginMode === 'account' }"
              type="button"
              @click="loginMode = 'account'"
            >
              账号密码
            </button>
            <button
              :class="{ active: loginMode === 'mobile' }"
              type="button"
              @click="loginMode = 'mobile'"
            >
              手机验证码
            </button>
          </div>

          <form
            v-if="loginMode === 'account'"
            class="auth-form"
            @submit.prevent="handleAccountLogin"
          >
            <div v-if="errors.account" class="auth-form__error">
              <IconifyIcon icon="solar:danger-triangle-outline" />
              <span>{{ errors.account }}</span>
            </div>

            <label v-if="tenantEnable && tenantList.length" class="auth-field">
              <span class="auth-field__icon">
                <IconifyIcon icon="solar:buildings-2-outline" />
              </span>
              <select
                :value="accountForm.tenantId"
                @change="setTenantId(($event.target as HTMLSelectElement).value)"
              >
                <option disabled value="">请选择租户</option>
                <option
                  v-for="tenant in tenantList"
                  :key="tenant.id"
                  :value="String(tenant.id)"
                >
                  {{ tenant.name }}
                </option>
              </select>
            </label>

            <label class="auth-field">
              <span class="auth-field__icon">
                <IconifyIcon icon="solar:user-outline" />
              </span>
              <input
                v-model="accountForm.username"
                autocomplete="username"
                placeholder="请输入账号"
                type="text"
              />
            </label>

            <label class="auth-field">
              <span class="auth-field__icon">
                <IconifyIcon icon="solar:lock-password-outline" />
              </span>
              <input
                v-model="accountForm.password"
                autocomplete="current-password"
                placeholder="请输入密码"
                type="password"
              />
            </label>

            <div class="auth-form__actions">
              <label class="auth-checkbox">
                <input v-model="accountForm.remember" type="checkbox" />
                <span>记住账号</span>
              </label>
              <button type="button" @click="goForgetPassword">忘记密码</button>
            </div>

            <button class="auth-submit" :disabled="loading" type="submit">
              {{ loading ? '正在验证身份...' : '登录并进入工作台' }}
            </button>

            <div class="auth-social">
              <span>其他登录方式</span>
              <div class="auth-social__buttons">
                <button type="button" @click="handleSocialLogin(20)">
                  <IconifyIcon icon="ri:dingtalk-line" />
                </button>
                <button type="button" @click="handleSocialLogin(10)">
                  <IconifyIcon icon="ri:wechat-line" />
                </button>
              </div>
            </div>
          </form>

          <form v-else class="auth-form" @submit.prevent="handleMobileLogin">
            <div v-if="errors.mobile" class="auth-form__error">
              <IconifyIcon icon="solar:danger-triangle-outline" />
              <span>{{ errors.mobile }}</span>
            </div>

            <label v-if="tenantEnable && tenantList.length" class="auth-field">
              <span class="auth-field__icon">
                <IconifyIcon icon="solar:buildings-2-outline" />
              </span>
              <select
                :value="mobileForm.tenantId"
                @change="setTenantId(($event.target as HTMLSelectElement).value)"
              >
                <option disabled value="">请选择租户</option>
                <option
                  v-for="tenant in tenantList"
                  :key="tenant.id"
                  :value="String(tenant.id)"
                >
                  {{ tenant.name }}
                </option>
              </select>
            </label>

            <label class="auth-field">
              <span class="auth-field__icon">
                <IconifyIcon icon="solar:phone-outline" />
              </span>
              <input
                v-model="mobileForm.mobile"
                maxlength="11"
                placeholder="请输入手机号"
                type="text"
              />
            </label>

            <div class="auth-code-row">
              <label class="auth-field auth-field--code">
                <span class="auth-field__icon">
                  <IconifyIcon icon="solar:chat-round-check-outline" />
                </span>
                <input
                  v-model="mobileForm.code"
                  maxlength="6"
                  placeholder="请输入验证码"
                  type="text"
                />
              </label>
              <button
                class="auth-code-btn"
                :disabled="sendingCode || countdown > 0"
                type="button"
                @click="handleSendCode"
              >
                {{ countdown > 0 ? `${countdown}s 后重发` : '获取验证码' }}
              </button>
            </div>

            <button class="auth-submit" :disabled="loading" type="submit">
              {{ loading ? '正在校验...' : '登录并进入工作台' }}
            </button>
          </form>
        </section>
      </section>
    </div>

    <Verification
      v-if="captchaEnable"
      ref="verifyRef"
      :captcha-type="'blockPuzzle'"
      :check-captcha-api="checkCaptcha"
      :get-captcha-api="getCaptcha"
      :img-size="{ width: '400px', height: '200px' }"
      mode="pop"
      @on-success="handleVerifySuccess"
    />
  </div>
</template>

<style scoped>
.auth-portal {
  min-height: 100vh;
  overflow: hidden;
  position: relative;
  background:
    radial-gradient(circle at 12% 16%, rgb(21 101 192 / 9%), transparent 18%),
    radial-gradient(circle at 88% 6%, rgb(11 87 161 / 8%), transparent 18%),
    linear-gradient(180deg, #f2f6fb 0%, #eaf0f7 100%);
}

.auth-portal__inner {
  position: relative;
  width: min(1180px, calc(100vw - 48px));
  margin: 0 auto;
  padding: 56px 0;
  z-index: 1;
}

.auth-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.12fr) minmax(400px, 460px);
  gap: 28px;
  align-items: stretch;
}

.auth-shell__intro {
  display: flex;
  align-items: stretch;
}

.auth-intro-card,
.auth-panel {
  border: 1px solid rgb(215 222 232 / 94%);
  border-radius: 32px;
  background: rgb(255 255 255 / 88%);
  box-shadow: 0 24px 60px rgb(15 23 42 / 10%);
  backdrop-filter: blur(18px);
}

.auth-intro-card {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  width: 100%;
  min-height: 100%;
  padding: 34px 34px 30px;
  transition: transform 0.24s ease-out;
}

.auth-intro-card__badge {
  display: inline-flex;
  width: fit-content;
  gap: 10px;
  align-items: center;
  padding: 8px 12px;
  border: 1px solid rgb(21 101 192 / 14%);
  border-radius: 999px;
  color: #1565c0;
  background: rgb(231 241 251 / 88%);
  font-size: 13px;
  font-weight: 600;
}

.auth-intro-card__badge-icon {
  display: inline-flex;
  font-size: 16px;
}

.auth-intro-card h1 {
  margin: 24px 0 0;
  color: #17202d;
  font-size: clamp(34px, 5vw, 48px);
  font-weight: 600;
  line-height: 1.06;
  letter-spacing: -0.04em;
  text-wrap: balance;
}

.auth-panel {
  align-self: center;
  padding: 28px 26px 24px;
}

.auth-panel__header {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 16px;
  align-items: center;
  margin-bottom: 28px;
}

.auth-panel__logo {
  align-items: center;
  background:
    linear-gradient(180deg, rgb(255 255 255 / 24%), rgb(255 255 255 / 0%)),
    linear-gradient(180deg, #1565c0 0%, #0b57a1 100%);
  border-radius: 18px;
  box-shadow: inset 0 1px 0 rgb(255 255 255 / 28%);
  color: #fff;
  display: inline-flex;
  font-size: 22px;
  height: 56px;
  justify-content: center;
  width: 56px;
}

.auth-panel__header h2 {
  margin: 0;
  color: #17202d;
  font-size: 28px;
  font-weight: 600;
  letter-spacing: -0.03em;
}

.auth-mode-switch {
  display: flex;
  gap: 8px;
  margin-bottom: 22px;
  padding: 6px;
  border: 1px solid #d7dee8;
  border-radius: 18px;
  background: #f3f6fa;
}

.auth-mode-switch button {
  flex: 1;
  padding: 12px 0;
  border: 0;
  border-radius: 14px;
  color: #4c5b70;
  background: transparent;
  font-size: 14px;
  font-weight: 600;
  transition:
    background-color 0.2s ease,
    color 0.2s ease,
    box-shadow 0.2s ease;
}

.auth-mode-switch button.active {
  color: #17202d;
  background: #fff;
  box-shadow: 0 8px 20px rgb(15 23 42 / 8%);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.auth-form__error {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px 14px;
  border: 1px solid #f0c7c5;
  border-radius: 16px;
  color: #c3413f;
  background: #fdeeee;
  font-size: 13px;
}

.auth-field {
  display: flex;
  align-items: center;
  padding: 0 16px;
  border: 1px solid #d7dee8;
  border-radius: 18px;
  background: #fff;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    background-color 0.2s ease;
}

.auth-field:focus-within {
  border-color: #1565c0;
  background: #fff;
  box-shadow: 0 0 0 4px rgb(21 101 192 / 10%);
}

.auth-field__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  color: #7d8a9b;
  font-size: 18px;
}

.auth-field input,
.auth-field select {
  flex: 1;
  padding: 16px 0 16px 12px;
  border: 0;
  color: #17202d;
  background: transparent;
  font-size: 14px;
  outline: none;
}

.auth-field input::placeholder {
  color: #7d8a9b;
}

.auth-field select {
  appearance: none;
  cursor: pointer;
}

.auth-form__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 4px 0;
}

.auth-form__actions button,
.auth-checkbox {
  color: #4c5b70;
  font-size: 13px;
}

.auth-form__actions button {
  border: 0;
  background: transparent;
  transition: color 0.2s ease;
}

.auth-form__actions button:hover {
  color: #1565c0;
}

.auth-checkbox {
  display: inline-flex;
  gap: 8px;
  align-items: center;
}

.auth-checkbox input {
  accent-color: #1565c0;
}

.auth-submit {
  padding: 15px 0;
  border: 0;
  border-radius: 18px;
  color: #fff;
  background: linear-gradient(180deg, #1565c0 0%, #0b57a1 100%);
  box-shadow: 0 18px 36px rgb(21 101 192 / 22%);
  font-size: 14px;
  font-weight: 600;
  transition:
    transform 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease;
}

.auth-submit:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 22px 42px rgb(21 101 192 / 26%);
}

.auth-submit:disabled,
.auth-code-btn:disabled {
  cursor: not-allowed;
  opacity: 0.58;
}

.auth-social {
  margin-top: 6px;
  padding-top: 22px;
  border-top: 1px solid #e5ebf3;
  text-align: center;
}

.auth-social > span {
  color: #7d8a9b;
  font-size: 12px;
}

.auth-social__buttons {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 14px;
}

.auth-social__buttons button,
.auth-code-btn {
  border: 1px solid #d7dee8;
  background: #fff;
  box-shadow: none;
  transition:
    border-color 0.18s ease,
    color 0.18s ease,
    background-color 0.18s ease;
}

.auth-social__buttons button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 999px;
  color: #4c5b70;
  font-size: 20px;
}

.auth-social__buttons button:hover,
.auth-code-btn:hover:not(:disabled) {
  border-color: #1565c0;
  color: #1565c0;
  background: #f7fbff;
}

.auth-code-row {
  display: flex;
  gap: 12px;
}

.auth-field--code {
  flex: 1;
}

.auth-code-btn {
  min-width: 124px;
  padding: 0 18px;
  border-radius: 18px;
  color: #17202d;
  font-size: 13px;
  font-weight: 600;
}

@media (max-width: 1024px) {
  .auth-shell {
    grid-template-columns: 1fr;
  }

  .auth-shell__intro {
    display: none;
  }
}

@media (max-width: 640px) {
  .auth-portal__inner {
    width: min(100vw - 24px, 1180px);
    padding: 24px 0;
  }

  .auth-panel {
    padding: 22px 18px 18px;
    border-radius: 28px;
  }

  .auth-panel__header {
    grid-template-columns: 1fr;
  }

  .auth-panel__logo {
    width: 52px;
    height: 52px;
  }

  .auth-panel__header h2 {
    font-size: 24px;
  }

  .auth-code-row {
    flex-direction: column;
  }

  .auth-code-btn {
    min-height: 54px;
  }
}
</style>
