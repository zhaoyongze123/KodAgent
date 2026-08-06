"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { toast } from "sonner";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  CloudCog,
  Download,
  KeyRound,
  Loader2,
  PlugZap,
  RefreshCw,
  Save,
  Settings2,
  Trash2,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { modelSupportsAgentTools } from "@/lib/model-capabilities";

type Provider = {
  id: number;
  name: string;
  provider_type?: string;
  base_url?: string;
  source?: string;
  enabled?: boolean;
  credential_status?: string;
};

type Model = {
  id: number;
  provider_id?: number;
  provider_name?: string;
  model_name?: string;
  display_name?: string;
  capabilities?: Record<string, boolean> | string;
  enabled?: boolean;
};

function supportsAgentCapabilities(model: Model): boolean {
  return modelSupportsAgentTools(model.capabilities);
}

type Binding = {
  id: number;
  user_id?: number | null;
  agent_name?: string;
  model_id?: number;
  model_name?: string;
  display_name?: string;
  provider_name?: string;
};

type ProviderForm = {
  id?: number;
  name: string;
  providerType: string;
  baseUrl: string;
  apiKey: string;
  enabled: boolean;
};

const emptyProvider: ProviderForm = {
  name: "",
  providerType: "OPENAI_COMPATIBLE",
  baseUrl: "https://api.openai.com/v1",
  apiKey: "",
  enabled: true,
};

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  const body = await response.json().catch(() => ({}));
  // Yudao's global response handler returns HTTP 200 for business errors and
  // puts the real status in `code`. Normalize the envelope here so every
  // settings API gets the same error handling and data shape.
  if (!response.ok || (typeof body?.code === "number" && body.code !== 0)) {
    throw new Error(
      body?.message ??
        body?.msg ??
        body?.error ??
        body?.detail ??
        `请求失败（${response.status}）`,
    );
  }
  if (body && typeof body === "object" && "data" in body) {
    return body.data as T;
  }
  return body as T;
}

function providerStatus(provider: Provider) {
  if (provider.credential_status === "VALID") return "连接正常";
  if (provider.credential_status === "INVALID") return "连接失败";
  return provider.credential_status === "UNKNOWN" ? "待测试" : "未配置 Key";
}

function providerForm(provider: Provider): ProviderForm {
  return {
    id: provider.id,
    name: provider.name,
    providerType: provider.provider_type ?? "OPENAI_COMPATIBLE",
    baseUrl: provider.base_url ?? "",
    // 后端永远不会回传明文 Key；空值表示保存时保留原 Key。
    apiKey: "",
    enabled: provider.enabled !== false,
  };
}

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [models, setModels] = useState<Model[]>([]);
  const [bindings, setBindings] = useState<Binding[]>([]);
  const [form, setForm] = useState<ProviderForm>(emptyProvider);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [syncingId, setSyncingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [bindingSaving, setBindingSaving] = useState(false);
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const initialLoadStarted = useRef(false);

  const restartLogin = () => {
    const currentPath = `${window.location.pathname}${window.location.search}`;
    window.location.replace(
      `/auth/kod-sso?tenantId=1&redirectPath=${encodeURIComponent(currentPath)}`,
    );
  };

  const ensureAgentSession = useCallback(async () => {
    const response = await fetch("/api/auth/kod-sso/session", {
      cache: "no-store",
    });
    if (response.status === 401) {
      return false;
    }
    if (!response.ok) {
      throw new Error("登录状态暂时无法确认，请稍后重试");
    }
    const body = await response.json().catch(() => ({}));
    if (body?.authenticated !== true) {
      throw new Error("登录状态无效，请重新登录");
    }
    return true;
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      if (!(await ensureAgentSession())) return;
      const results = await Promise.allSettled([
        requestJson<Provider[]>("/api/agent-settings/providers"),
        requestJson<Model[]>("/api/agent-settings/models"),
        requestJson<Binding[]>("/api/agent-settings/bindings"),
      ]);
      const firstFailure = results.find(
        (result): result is PromiseRejectedResult =>
          result.status === "rejected",
      );
      if (firstFailure) throw firstFailure.reason;
      const [providerResult, modelResult, bindingResult] = results;
      const providerRows =
        providerResult.status === "fulfilled" ? providerResult.value : [];
      const modelRows =
        modelResult.status === "fulfilled" ? modelResult.value : [];
      const bindingRows =
        bindingResult.status === "fulfilled" ? bindingResult.value : [];
      const agentModelRows = (Array.isArray(modelRows) ? modelRows : []).filter(
        supportsAgentCapabilities,
      );
      setProviders(Array.isArray(providerRows) ? providerRows : []);
      setModels(agentModelRows);
      setBindings(Array.isArray(bindingRows) ? bindingRows : []);
      const defaultBinding = (
        Array.isArray(bindingRows) ? bindingRows : []
      ).find(
        (binding) =>
          binding.user_id == null &&
          binding.agent_name === "oa-main-agent" &&
          agentModelRows.some((model) => model.id === binding.model_id),
      );
      setSelectedModelId(
        defaultBinding?.model_id ? String(defaultBinding.model_id) : "",
      );
    } catch (error) {
      const message = error instanceof Error ? error.message : "设置加载失败";
      setLoadError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [ensureAgentSession]);

  useEffect(() => {
    if (initialLoadStarted.current) return;
    initialLoadStarted.current = true;
    void loadData();
  }, [loadData]);

  const updateForm = <K extends keyof ProviderForm>(
    key: K,
    value: ProviderForm[K],
  ) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const saveProvider = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.name.trim() || !form.baseUrl.trim()) {
      toast.error("请填写供应商名称和中转地址");
      return;
    }
    if (!form.id && !form.apiKey.trim()) {
      toast.error("新增供应商时必须填写 API Key");
      return;
    }
    setSaving(true);
    try {
      await requestJson("/api/agent-settings/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      toast.success(form.id ? "供应商配置已更新" : "供应商已添加");
      setForm(emptyProvider);
      await loadData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
      setSaving(false);
    }
  };

  const testProvider = async (id: number) => {
    setTestingId(id);
    try {
      const result = await requestJson<{
        success?: boolean;
        count?: number;
        error?: string;
        endpoint?: string;
        latencyMs?: number;
      }>(`/api/agent-settings/providers/${id}/test`, { method: "POST" });
      if (result.success)
        toast.success(
          `连接成功 · ${result.count ?? 0} 个模型 · ${result.latencyMs ?? 0} ms`,
        );
      else toast.error(result.error ?? "供应商连接失败");
      await loadData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "连接测试失败");
    } finally {
      setTestingId(null);
    }
  };

  const syncProvider = async (id: number) => {
    setSyncingId(id);
    try {
      const result = await requestJson<{ count?: number }>(
        `/api/agent-settings/providers/${id}/sync`,
        { method: "POST" },
      );
      toast.success(`模型同步完成 · 已写入 ${result.count ?? 0} 个模型`);
      await loadData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "模型同步失败");
    } finally {
      setSyncingId(null);
    }
  };

  const deleteProvider = async (id: number) => {
    if (!window.confirm("停用这个供应商？已同步的模型将不再作为可选模型。"))
      return;
    setDeletingId(id);
    try {
      await requestJson(`/api/agent-settings/providers/${id}`, {
        method: "DELETE",
      });
      toast.success("供应商已停用");
      if (form.id === id) setForm(emptyProvider);
      await loadData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "停用失败");
    } finally {
      setDeletingId(null);
    }
  };

  const saveBinding = async () => {
    if (!selectedModelId) {
      toast.error("请先选择一个默认模型");
      return;
    }
    setBindingSaving(true);
    try {
      await requestJson("/api/agent-settings/bindings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agentName: "oa-main-agent",
          userId: null,
          modelId: Number(selectedModelId),
          enabled: true,
        }),
      });
      toast.success("oa-main-agent 默认模型已保存");
      await loadData();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "默认模型保存失败");
    } finally {
      setBindingSaving(false);
    }
  };

  return (
    <main className="bg-background text-foreground min-h-dvh px-5 py-6 md:px-10 md:py-10">
      <div className="mx-auto max-w-6xl">
        <header className="mb-8 flex items-start justify-between gap-4">
          <div>
            <Button
              asChild
              variant="ghost"
              className="text-muted-foreground mb-4 -ml-3 gap-2"
            >
              <Link href="/">
                <ArrowLeft className="size-4" />
                返回对话
              </Link>
            </Button>
            <div className="flex items-center gap-3">
              <div className="bg-muted/40 flex size-10 items-center justify-center rounded-lg border">
                <Settings2 className="size-5" />
              </div>
              <div>
                <h1 className="text-2xl font-semibold tracking-tight">
                  模型设置
                </h1>
                <p className="text-muted-foreground mt-1 text-sm">
                  管理供应商、模型同步和 KodAgent 默认模型。
                </p>
              </div>
            </div>
          </div>
          <Button
            variant="outline"
            onClick={() => void loadData()}
            disabled={loading}
            aria-label="刷新模型设置"
          >
            <RefreshCw className={loading ? "size-4 animate-spin" : "size-4"} />
            刷新
          </Button>
        </header>

        {loading ? (
          <div className="space-y-5">
            <Skeleton className="h-64 w-full" />
            <Skeleton className="h-72 w-full" />
          </div>
        ) : (
          <div className="space-y-6">
            {loadError ? (
              <div
                role="alert"
                className="border-destructive/30 bg-destructive/5 flex flex-col gap-2 rounded-lg border px-4 py-3 text-sm"
              >
                <span className="font-medium">设置数据暂时无法加载</span>
                <span className="text-muted-foreground">
                  {loadError}。请确认已登录并检查 Java Agent 服务是否运行。
                </span>
                <div>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => void loadData()}
                  >
                    重新加载
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="ml-2"
                    onClick={restartLogin}
                  >
                    重新登录
                  </Button>
                </div>
              </div>
            ) : null}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <CloudCog className="size-5" />
                  模型供应商
                </CardTitle>
                <CardDescription>
                  配置 OpenAI 兼容接口或企业内部中转站。API Key
                  会由后端加密保存。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <form
                  onSubmit={saveProvider}
                  className="bg-muted/20 grid gap-4 rounded-lg border p-4 md:grid-cols-2"
                >
                  <div className="space-y-2">
                    <Label htmlFor="provider-name">供应商名称</Label>
                    <Input
                      id="provider-name"
                      value={form.name}
                      onChange={(e) => updateForm("name", e.target.value)}
                      placeholder="例如：公司模型中转站"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="provider-type">协议类型</Label>
                    <Input
                      id="provider-type"
                      value={form.providerType}
                      onChange={(e) =>
                        updateForm("providerType", e.target.value)
                      }
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="provider-url">中转地址</Label>
                    <Input
                      id="provider-url"
                      type="url"
                      value={form.baseUrl}
                      onChange={(e) => updateForm("baseUrl", e.target.value)}
                      placeholder="https://example.com/v1"
                    />
                  </div>
                  <div className="space-y-2 md:col-span-2">
                    <Label htmlFor="provider-key">
                      API Key{" "}
                      {form.id ? (
                        <span className="text-muted-foreground font-normal">
                          （留空则保留原 Key）
                        </span>
                      ) : null}
                    </Label>
                    <div className="relative">
                      <KeyRound className="text-muted-foreground absolute top-2.5 left-3 size-4" />
                      <Input
                        id="provider-key"
                        type="password"
                        className="pl-9"
                        value={form.apiKey}
                        onChange={(e) => updateForm("apiKey", e.target.value)}
                        placeholder={form.id ? "已配置，不回显" : "sk-..."}
                        autoComplete="new-password"
                      />
                    </div>
                  </div>
                  <div className="flex items-center gap-3">
                    <Switch
                      id="provider-enabled"
                      checked={form.enabled}
                      onCheckedChange={(value) => updateForm("enabled", value)}
                    />
                    <Label htmlFor="provider-enabled">启用供应商</Label>
                  </div>
                  <div className="flex items-end justify-end gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => setForm(emptyProvider)}
                    >
                      清空
                    </Button>
                    <Button
                      type="submit"
                      disabled={saving}
                    >
                      {saving ? (
                        <Loader2 className="size-4 animate-spin" />
                      ) : (
                        <Save className="size-4" />
                      )}
                      {saving
                        ? "保存中"
                        : form.id
                          ? "更新供应商"
                          : "添加供应商"}
                    </Button>
                  </div>
                </form>

                {providers.length === 0 ? (
                  <div className="text-muted-foreground rounded-lg border border-dashed p-8 text-center text-sm">
                    还没有供应商配置。填写上面的表单，添加第一个模型供应商。
                  </div>
                ) : (
                  <div className="divide-y rounded-lg border">
                    {providers.map((provider) => (
                      <div
                        key={provider.id}
                        className="flex flex-col gap-4 p-4 md:flex-row md:items-center md:justify-between"
                      >
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="font-medium">{provider.name}</span>
                            <span className="bg-muted rounded-full px-2 py-0.5 text-xs">
                              {providerStatus(provider)}
                            </span>
                            {provider.enabled === false ? (
                              <span className="text-muted-foreground text-xs">
                                已停用
                              </span>
                            ) : null}
                          </div>
                          <p className="text-muted-foreground mt-1 truncate text-sm">
                            {provider.base_url}
                          </p>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setForm(providerForm(provider))}
                          >
                            编辑
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void testProvider(provider.id)}
                            disabled={testingId === provider.id}
                          >
                            {testingId === provider.id ? (
                              <Loader2 className="size-4 animate-spin" />
                            ) : (
                              <PlugZap className="size-4" />
                            )}
                            测试连接
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => void syncProvider(provider.id)}
                            disabled={syncingId === provider.id}
                          >
                            {syncingId === provider.id ? (
                              <Loader2 className="size-4 animate-spin" />
                            ) : (
                              <Download className="size-4" />
                            )}
                            同步模型
                          </Button>
                          <Button
                            size="sm"
                            variant="ghost"
                            className="text-destructive hover:text-destructive"
                            onClick={() => void deleteProvider(provider.id)}
                            disabled={deletingId === provider.id}
                            aria-label={`停用 ${provider.name}`}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Download className="size-5" />
                  已同步模型
                </CardTitle>
                <CardDescription>
                  模型列表来自供应商的 /models
                  接口。先测试连接，再点击同步模型。
                </CardDescription>
              </CardHeader>
              <CardContent>
                {models.length === 0 ? (
                  <div className="text-muted-foreground rounded-lg border border-dashed p-8 text-center text-sm">
                    暂无模型。请先配置供应商并同步模型。
                  </div>
                ) : (
                  <div className="grid gap-3 md:grid-cols-2">
                    {models.map((model) => {
                      const capabilities =
                        typeof model.capabilities === "string"
                          ? (() => {
                              try {
                                return JSON.parse(model.capabilities) as Record<
                                  string,
                                  boolean
                                >;
                              } catch {
                                return {};
                              }
                            })()
                          : (model.capabilities ?? {});
                      return (
                        <div
                          key={model.id}
                          className="rounded-lg border p-4"
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="truncate font-medium">
                                {model.display_name ?? model.model_name}
                              </p>
                              <p className="text-muted-foreground mt-1 text-xs">
                                {model.provider_name} · {model.model_name}
                              </p>
                            </div>
                            <span className="text-muted-foreground text-xs">
                              #{model.id}
                            </span>
                          </div>
                          <div className="mt-3 flex flex-wrap gap-1.5">
                            {Object.entries(capabilities)
                              .filter(([, enabled]) => enabled)
                              .map(([name]) => (
                                <span
                                  key={name}
                                  className="bg-muted rounded px-2 py-0.5 text-xs"
                                >
                                  {name}
                                </span>
                              ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Check className="size-5" />
                  默认模型绑定
                </CardTitle>
                <CardDescription>
                  当前先配置租户级 oa-main-agent
                  默认模型；显式选择模型的对话仍可单独切换。
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
                  <div className="space-y-2">
                    <Label htmlFor="default-model">
                      oa-main-agent 默认模型
                    </Label>
                    <div className="relative">
                      <select
                        id="default-model"
                        value={selectedModelId}
                        onChange={(e) => setSelectedModelId(e.target.value)}
                        className="border-input bg-background ring-offset-background focus-visible:ring-ring flex h-9 w-full appearance-none rounded-md border px-3 pr-9 text-sm outline-none focus-visible:ring-2 focus-visible:ring-offset-2"
                      >
                        <option value="">选择模型</option>
                        {models.map((model) => (
                          <option
                            key={model.id}
                            value={model.id}
                          >
                            {model.provider_name} /{" "}
                            {model.display_name ?? model.model_name}
                          </option>
                        ))}
                      </select>
                      <ChevronDown className="text-muted-foreground pointer-events-none absolute top-2.5 right-3 size-4" />
                    </div>
                  </div>
                  <Button
                    onClick={() => void saveBinding()}
                    disabled={bindingSaving || !models.length}
                  >
                    {bindingSaving ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Save className="size-4" />
                    )}
                    保存默认模型
                  </Button>
                </div>
                <Separator />
                {bindings.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    尚未保存默认模型绑定。
                  </p>
                ) : (
                  <div className="text-muted-foreground text-sm">
                    当前绑定：
                    <span className="text-foreground font-medium">
                      {
                        bindings.find(
                          (binding) =>
                            binding.user_id == null &&
                            binding.agent_name === "oa-main-agent",
                        )?.provider_name
                      }{" "}
                      /{" "}
                      {bindings.find(
                        (binding) =>
                          binding.user_id == null &&
                          binding.agent_name === "oa-main-agent",
                      )?.display_name ??
                        bindings.find(
                          (binding) =>
                            binding.user_id == null &&
                            binding.agent_name === "oa-main-agent",
                        )?.model_name}
                    </span>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        )}
      </div>
    </main>
  );
}
