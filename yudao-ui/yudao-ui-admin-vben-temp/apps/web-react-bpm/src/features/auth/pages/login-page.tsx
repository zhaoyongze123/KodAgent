import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useState, type FormEvent } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import CryptoJS from 'crypto-js';

import { cn } from '@/shared/lib/cn';
import { useSessionStore } from '@/features/auth/store/session-store';
import {
  checkCaptcha,
  getCaptcha,
  getPermissionInfo,
  getTenantByWebsite,
  getTenantSimpleList,
  login,
  sendSmsCode,
  smsLogin,
  socialAuthRedirect,
} from '@/shared/api/auth';

type LoginMode = 'account' | 'mobile';
type CaptchaIntent = 'account-login' | 'send-sms';

const captchaEnabled =
  String(import.meta.env.VITE_APP_CAPTCHA_ENABLE ?? 'false').toLowerCase() ===
  'true';

const socialEntryList = [
  { label: 'Gitee', type: 10 },
  { label: '钉钉', type: 20 },
  { label: '企业微信', type: 30 },
];

export function LoginPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setSession = useSessionStore((state) => state.setSession);
  const setTokens = useSessionStore((state) => state.setTokens);
  const setTenantContext = useSessionStore((state) => state.setTenantContext);
  const savedTenantId = useSessionStore((state) => state.tenantId);

  const [loginMode, setLoginMode] = useState<LoginMode>('account');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [mobile, setMobile] = useState('');
  const [smsCode, setSmsCode] = useState('');
  const [tenantId, setTenantId] = useState('');
  const [captchaVerification, setCaptchaVerification] = useState('');
  const [captchaImage, setCaptchaImage] = useState('');
  const [captchaJigsawImage, setCaptchaJigsawImage] = useState('');
  const [captchaSecretKey, setCaptchaSecretKey] = useState('');
  const [captchaToken, setCaptchaToken] = useState('');
  const [captchaOffset, setCaptchaOffset] = useState(0);
  const [captchaDragging, setCaptchaDragging] = useState(false);
  const [errorText, setErrorText] = useState('');
  const [countdown, setCountdown] = useState(0);

  const tenantListQuery = useQuery({
    queryKey: ['auth-tenants'],
    queryFn: getTenantSimpleList,
  });
  const websiteTenantQuery = useQuery({
    queryKey: ['auth-tenant-website', window.location.hostname],
    queryFn: () => getTenantByWebsite(window.location.hostname),
  });

  const captchaQuery = useQuery({
    queryKey: ['auth-captcha'],
    queryFn: async () => {
      const result = await getCaptcha({ captchaType: 'blockPuzzle' });
      setCaptchaImage(String(result.originalImageBase64 || ''));
      setCaptchaJigsawImage(String(result.jigsawImageBase64 || ''));
      setCaptchaSecretKey(String(result.secretKey || ''));
      setCaptchaToken(String(result.token || ''));
      setCaptchaOffset(0);
      setCaptchaVerification('');
      return result;
    },
    enabled: captchaEnabled,
  });

  useEffect(() => {
    const timer = countdown
      ? window.setTimeout(() => setCountdown((current) => current - 1), 1000)
      : null;
    return () => {
      if (timer) {
        window.clearTimeout(timer);
      }
    };
  }, [countdown]);

  useEffect(() => {
    const websiteTenantId = websiteTenantQuery.data?.id
      ? String(websiteTenantQuery.data.id)
      : '';
    const storedTenantId = savedTenantId ? String(savedTenantId) : '';
    const firstTenantId = tenantListQuery.data?.[0]?.id
      ? String(tenantListQuery.data[0].id)
      : '';
    const resolvedTenantId = websiteTenantId || storedTenantId || firstTenantId;
    if (!tenantId && resolvedTenantId) {
      setTenantId(resolvedTenantId);
      setTenantContext({
        tenantId: Number(resolvedTenantId),
        visitTenantId: Number(resolvedTenantId),
      });
    }
  }, [
    savedTenantId,
    setTenantContext,
    tenantId,
    tenantListQuery.data,
    websiteTenantQuery.data,
  ]);

  async function finalizeSession(loginResult: {
    accessToken: string;
    refreshToken: string;
  }) {
    setTokens({
      accessToken: loginResult.accessToken,
      refreshToken: loginResult.refreshToken,
    });
    const permissionInfo = await getPermissionInfo();
    setSession({
      accessToken: loginResult.accessToken,
      permissionInfo,
      refreshToken: loginResult.refreshToken,
    });
    navigate(searchParams.get('redirect') || '/workspace');
  }

  const accountMutation = useMutation({
    mutationFn: async (verification: string) => {
      setTenantContext({
        tenantId: Number(tenantId),
        visitTenantId: Number(tenantId),
      });
      const loginResult = await login({
        captchaVerification: verification,
        password,
        username,
      });
      await finalizeSession(loginResult);
    },
    onError: (error) => {
      setErrorText(error instanceof Error ? error.message : '登录失败');
    },
  });

  const smsMutation = useMutation({
    mutationFn: async () => {
      setTenantContext({
        tenantId: Number(tenantId),
        visitTenantId: Number(tenantId),
      });
      const loginResult = await smsLogin({
        code: smsCode,
        mobile,
      });
      await finalizeSession(loginResult);
    },
    onError: (error) => {
      setErrorText(error instanceof Error ? error.message : '短信登录失败');
    },
  });

  const sendCodeMutation = useMutation({
    mutationFn: async (verification: string) => {
      setTenantContext({
        tenantId: Number(tenantId),
        visitTenantId: Number(tenantId),
      });
      await sendSmsCode({
        captchaVerification: verification.trim() || undefined,
        mobile,
        scene: 21,
      });
    },
    onError: (error) => {
      setErrorText(error instanceof Error ? error.message : '发送验证码失败');
    },
    onSuccess: () => {
      setCountdown(60);
    },
  });

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorText('');
    if (loginMode === 'account') {
      if (!captchaEnabled) {
        accountMutation.mutate('');
        return;
      }
      void verifyCaptcha('account-login');
      return;
    }
    smsMutation.mutate();
  }

  async function handleSocialLogin(type: number) {
    setTenantContext({
      tenantId: Number(tenantId),
      visitTenantId: Number(tenantId),
    });
    const redirect = searchParams.get('redirect') || '/workspace';
    const redirectUri = `${location.origin}/social-login?type=${type}&redirect=${encodeURIComponent(redirect)}`;
    const redirectUrl = await socialAuthRedirect(type, redirectUri);
    window.location.href = redirectUrl;
  }

  function aesEncrypt(data: string, key: string) {
    const keyUtf8 = CryptoJS.enc.Utf8.parse(key);
    return CryptoJS.AES.encrypt(data, keyUtf8, {
      mode: CryptoJS.mode.ECB,
      padding: CryptoJS.pad.Pkcs7,
    }).toString();
  }

  async function verifyCaptcha(nextIntent: CaptchaIntent) {
    if (!captchaToken || !captchaSecretKey) {
      setErrorText('验证码尚未准备完成，请刷新后重试');
      return;
    }

    try {
      const moveLeftDistance = (captchaOffset * 310) / 260;
      const point = { x: moveLeftDistance, y: 5 };
      const pointJson = aesEncrypt(JSON.stringify(point), captchaSecretKey);
      await checkCaptcha({
        captchaType: 'blockPuzzle',
        pointJson,
        token: captchaToken,
      });
      const nextVerification = aesEncrypt(
        `${captchaToken}---${JSON.stringify(point)}`,
        captchaSecretKey,
      );
      setCaptchaVerification(nextVerification);
      setErrorText('');
      if (nextIntent === 'account-login') {
        accountMutation.mutate(nextVerification);
        return;
      }
      sendCodeMutation.mutate(nextVerification);
    } catch (error) {
      setCaptchaVerification('');
      setErrorText(error instanceof Error ? error.message : '验证码校验失败');
      captchaQuery.refetch();
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center bg-[#f4f7fb] px-6">
      <div className="grid w-full max-w-6xl grid-cols-1 overflow-hidden border border-[var(--line)] bg-white lg:grid-cols-[1.2fr_0.8fr]">
        <section className="border-b border-[var(--line)] bg-[linear-gradient(180deg,#f7fafc_0%,#eef3f8_100%)] p-10 lg:border-b-0 lg:border-r">
          <div className="hairline-title">DingTalk Style Approval Workspace</div>
          <h1 className="mt-4 max-w-xl text-4xl font-semibold text-balance">
            统一认证入口承接账号、短信、社交与 SSO 登录。
          </h1>
          <div className="mt-4 max-w-2xl text-sm leading-7 text-[var(--text-muted)] text-pretty">
            这个入口已经接入真实租户识别与后端权限初始化链路，登录成功后会直接把用户带入统一审批工作面。
          </div>

          <div className="mt-8 grid gap-4 text-sm text-[var(--text-muted)] md:grid-cols-3">
            <div className="border-t border-[var(--line)] bg-white/70 px-4 py-4 pt-5">
              多租户依赖 `tenant-id` 请求头进入后端上下文，而不是前端只做下拉框展示。
            </div>
            <div className="border-t border-[var(--line)] bg-white/70 px-4 py-4 pt-5">
              账号密码、短信验证码、社交登录与可道云 SSO 共用同一认证入口。
            </div>
            <div className="border-t border-[var(--line)] bg-white/70 px-4 py-4 pt-5">
              登录成功后立即拉取权限信息，决定管理员与普通用户看到哪些入口。
            </div>
          </div>

          <div className="mt-10 border-t border-[var(--line)] pt-5">
            <div className="mb-3 text-sm font-medium">当前已接入的认证路径</div>
            <div className="grid gap-3 text-sm text-[var(--text-muted)] md:grid-cols-2">
              <div className="border border-[var(--line)] bg-white px-4 py-3">
                `/system/auth/login` + `/system/auth/get-permission-info`
              </div>
              <div className="border border-[var(--line)] bg-white px-4 py-3">
                `/system/auth/send-sms-code` + `/system/auth/sms-login`
              </div>
              <div className="border border-[var(--line)] bg-white px-4 py-3">
                `/system/auth/social-auth-redirect` + `/system/auth/social-login`
              </div>
              <div className="border border-[var(--line)] bg-white px-4 py-3">
                `/system/auth/kod-sso/start` + `/system/auth/kod-sso/exchange`
              </div>
            </div>
          </div>
        </section>

        <section className="p-10">
          <div className="hairline-title">登录</div>
          <div className="mt-2 text-sm text-[var(--text-muted)]">
            接入租户、验证码、短信登录、社交登录与可道云 SSO
          </div>

          <div className="mt-6 flex gap-2">
            {[
              { key: 'account', label: '账号登录' },
              { key: 'mobile', label: '短信登录' },
            ].map((item) => (
              <button
                key={item.key}
                className={cn(
                  'border px-3 py-2 text-sm',
                  loginMode === item.key
                    ? 'border-[var(--line-strong)] bg-white text-[var(--text)]'
                    : 'border-transparent bg-[var(--panel-muted)] text-[var(--text-muted)]',
                )}
                type="button"
                onClick={() => {
                  setErrorText('');
                  setLoginMode(item.key as LoginMode);
                }}
              >
                {item.label}
              </button>
            ))}
          </div>

          <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="mb-2 block text-sm font-medium">租户</label>
              <select
                className="w-full border border-[var(--line)] bg-[var(--panel)] px-3 py-3 outline-none"
                value={tenantId}
                onChange={(event) => {
                  setTenantId(event.target.value);
                  setTenantContext({
                    tenantId: event.target.value ? Number(event.target.value) : null,
                    visitTenantId: event.target.value
                      ? Number(event.target.value)
                      : null,
                  });
                }}
              >
                <option value="">请选择租户</option>
                {(tenantListQuery.data || []).map((item) => (
                  <option key={item.id} value={String(item.id)}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>

            {loginMode === 'account' ? (
              <>
                <div>
                  <label className="mb-2 block text-sm font-medium">用户名</label>
                  <input
                    className="w-full border border-[var(--line)] bg-[var(--panel)] px-3 py-3 outline-none"
                    value={username}
                    onChange={(event) => setUsername(event.target.value)}
                    placeholder="请输入用户名"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-medium">密码</label>
                  <input
                    className="w-full border border-[var(--line)] bg-[var(--panel)] px-3 py-3 outline-none"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="请输入密码"
                  />
                </div>
                {captchaEnabled ? (
                  <div>
                    <label className="mb-2 block text-sm font-medium">滑块验证码</label>
                    <div className="space-y-3 border border-[var(--line)] bg-[var(--panel)] p-3">
                      <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
                        <span>账号登录前先完成一次后端验证码校验</span>
                        <button
                          className="border border-[var(--line)] bg-white px-2 py-1 text-xs"
                          type="button"
                          onClick={() => {
                            setErrorText('');
                            captchaQuery.refetch();
                          }}
                        >
                          刷新验证码
                        </button>
                      </div>
                      {captchaImage ? (
                        <div className="space-y-3">
                          <div className="relative h-40 overflow-hidden border border-[var(--line)] bg-white">
                            <img
                              alt="captcha-background"
                              className="h-full w-full object-cover select-none"
                              draggable={false}
                              src={`data:image/png;base64,${captchaImage}`}
                            />
                            {captchaJigsawImage ? (
                              <img
                                alt="captcha-jigsaw"
                                className="pointer-events-none absolute top-2 h-16 w-16 select-none opacity-90"
                                draggable={false}
                                src={`data:image/png;base64,${captchaJigsawImage}`}
                                style={{ left: `${captchaOffset}px` }}
                              />
                            ) : null}
                          </div>
                          <div className="space-y-2">
                            <input
                              className="w-full accent-[var(--accent)]"
                              max={260}
                              min={0}
                              type="range"
                              value={captchaOffset}
                              onChange={(event) => {
                                setCaptchaOffset(Number(event.target.value));
                                setCaptchaDragging(true);
                                setCaptchaVerification('');
                              }}
                              onMouseUp={() => setCaptchaDragging(false)}
                              onTouchEnd={() => setCaptchaDragging(false)}
                            />
                            <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
                              <span>
                                {captchaDragging
                                  ? '拖动中，松手后点击“校验并登录”'
                                  : '拖动滑块对齐缺口后提交'}
                              </span>
                              {captchaVerification ? (
                                <span className="text-[#0f766e]">已通过校验</span>
                              ) : null}
                            </div>
                          </div>
                        </div>
                      ) : (
                        <div className="text-xs text-[var(--text-muted)]">
                          {captchaQuery.isLoading
                            ? '正在获取验证码...'
                            : '当前未获取到验证码图片'}
                        </div>
                      )}
                    </div>
                  </div>
                ) : null}
              </>
            ) : (
              <>
                <div>
                  <label className="mb-2 block text-sm font-medium">手机号</label>
                  <input
                    className="w-full border border-[var(--line)] bg-[var(--panel)] px-3 py-3 outline-none"
                    value={mobile}
                    onChange={(event) => setMobile(event.target.value)}
                    placeholder="请输入手机号"
                  />
                </div>
                <div>
                  <label className="mb-2 block text-sm font-medium">短信验证码</label>
                  <div className="grid grid-cols-[minmax(0,1fr)_120px] gap-3">
                    <input
                      className="w-full border border-[var(--line)] bg-[var(--panel)] px-3 py-3 outline-none"
                      value={smsCode}
                      onChange={(event) => setSmsCode(event.target.value)}
                      placeholder="请输入短信验证码"
                    />
                    <button
                      className="border border-[var(--line)] bg-white px-3 py-3 text-sm"
                      disabled={countdown > 0 || sendCodeMutation.isPending}
                      type="button"
                      onClick={() => {
                        setErrorText('');
                        verifyCaptcha('send-sms');
                      }}
                    >
                      {countdown > 0 ? `${countdown}s` : '发送验证码'}
                    </button>
                  </div>
                </div>
              </>
            )}

            {loginMode === 'mobile' && captchaEnabled ? (
              <div>
                <label className="mb-2 block text-sm font-medium">短信验证码校验串</label>
                <div className="space-y-3 border border-[var(--line)] bg-[var(--panel)] p-3">
                  <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
                    <span>短信发送依赖后端验证码校验，不再手工粘贴校验串</span>
                    <button
                      className="border border-[var(--line)] bg-white px-2 py-1 text-xs"
                      type="button"
                      onClick={() => {
                        setErrorText('');
                        captchaQuery.refetch();
                      }}
                    >
                      刷新验证码
                    </button>
                  </div>
                  {captchaImage ? (
                    <div className="space-y-3">
                      <div className="relative h-40 overflow-hidden border border-[var(--line)] bg-white">
                        <img
                          alt="captcha-background"
                          className="h-full w-full object-cover select-none"
                          draggable={false}
                          src={`data:image/png;base64,${captchaImage}`}
                        />
                        {captchaJigsawImage ? (
                          <img
                            alt="captcha-jigsaw"
                            className="pointer-events-none absolute top-2 h-16 w-16 select-none opacity-90"
                            draggable={false}
                            src={`data:image/png;base64,${captchaJigsawImage}`}
                            style={{ left: `${captchaOffset}px` }}
                          />
                        ) : null}
                      </div>
                      <input
                        className="w-full accent-[var(--accent)]"
                        max={260}
                        min={0}
                        type="range"
                        value={captchaOffset}
                        onChange={(event) => {
                          setCaptchaOffset(Number(event.target.value));
                          setCaptchaVerification('');
                        }}
                      />
                    </div>
                  ) : (
                    <div className="text-xs text-[var(--text-muted)]">
                      {captchaQuery.isLoading ? '正在获取验证码...' : '当前未获取到验证码图片'}
                    </div>
                  )}
                  <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
                    <span>拖动滑块对齐缺口，再点击发送验证码</span>
                    {captchaVerification ? (
                      <span className="text-[#0f766e]">已生成可提交校验串</span>
                    ) : null}
                  </div>
                </div>
              </div>
            ) : null}

            {errorText ? (
              <div className="border border-[#efc3bd] bg-[#fff6f4] px-3 py-2 text-sm text-[var(--danger)]">
                {errorText}
              </div>
            ) : null}

            <button
              className="w-full border border-[#0f56a6] bg-[var(--accent)] px-4 py-3 text-sm font-medium text-white disabled:opacity-60"
              disabled={accountMutation.isPending || smsMutation.isPending}
              type="submit"
            >
              {accountMutation.isPending || smsMutation.isPending
                ? '登录中...'
                : loginMode === 'account'
                  ? captchaEnabled
                    ? '校验并登录'
                    : '进入审批系统'
                  : '进入审批系统'}
            </button>
          </form>

          <div className="mt-6 border-t border-[var(--line)] pt-5">
            <div className="mb-3 text-sm font-medium">其他登录方式</div>
            <div className="grid gap-2 md:grid-cols-2">
              {socialEntryList.map((item) => (
                <button
                  key={item.type}
                  className="border border-[var(--line)] bg-white px-3 py-3 text-sm"
                  type="button"
                  onClick={() => handleSocialLogin(item.type)}
                >
                  {item.label}登录
                </button>
              ))}
              <button
                className="border border-[var(--line)] bg-white px-3 py-3 text-sm"
                type="button"
                onClick={() => {
                  setTenantContext({
                    tenantId: Number(tenantId),
                    visitTenantId: Number(tenantId),
                  });
                  window.location.href = `/admin-api/system/auth/kod-sso/start?redirectUri=${encodeURIComponent(
                    `${location.origin}/kod-sso-login?tenantId=${tenantId}`,
                  )}`;
                }}
              >
                可道云 SSO 登录
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
