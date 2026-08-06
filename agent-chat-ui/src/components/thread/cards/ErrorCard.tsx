import { AlertCircle, ExternalLink, LogIn, RefreshCw, Settings2 } from "lucide-react";
import type { AgentError } from "@/types/agent-block";

const ERROR_COPY: Record<
  AgentError["code"],
  { title: string; action?: AgentError["action"] }
> = {
  SESSION_EXPIRED: {
    title: "登录已过期",
    action: { type: "login", label: "重新登录" },
  },
  PERMISSION_DENIED: {
    title: "你没有执行该操作的权限",
    action: { type: "open_oa", label: "打开 OA" },
  },
  EMPTY_RESULT: { title: "没有找到相关数据" },
  UPSTREAM_TIMEOUT: {
    title: "业务系统暂时没有响应",
  },
  UPSTREAM_BAD_REQUEST: { title: "模型请求参数不兼容" },
  MODEL_NOT_SUPPORTED: { title: "当前模型不支持 Agent 工具调用" },
  CLIPBOARD_UNAVAILABLE: { title: "当前环境不允许复制到剪贴板" },
  VALIDATION_FAILED: { title: "请求信息不完整或不合法" },
  UNKNOWN: { title: "处理请求时发生异常" },
};

export function ErrorCard({
  error,
  onAction,
}: {
  error: AgentError;
  onAction?: (action: NonNullable<AgentError["action"]>) => void;
}) {
  const copy = ERROR_COPY[error.code] ?? ERROR_COPY.UNKNOWN;
  const action = error.action ?? copy.action;

  const handleAction = () => {
    if (action?.type === "login") {
      window.location.assign("/auth/kod-sso");
    } else if (action?.type === "open_oa") {
      window.open("/", "_blank", "noopener,noreferrer");
    } else if (action) {
      onAction?.(action);
    }
  };

  const ActionIcon =
    action?.type === "login"
      ? LogIn
      : action?.type === "open_oa"
        ? ExternalLink
      : action?.type === "retry"
        ? Settings2
        : RefreshCw;

  return (
    <div className="my-2 w-full max-w-xl rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900">
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 size-4 shrink-0 text-red-600" />
        <div className="min-w-0 flex-1">
          <div className="font-medium">{copy.title}</div>
          {error.message && error.message !== copy.title && (
            <div className="mt-1 text-red-800/90">{error.message}</div>
          )}
          {error.detail && (
            <div className="text-pretty mt-2 text-xs leading-5 text-red-800/75">
              {error.detail}
            </div>
          )}
          {action && (
            <button
              type="button"
              className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-red-300 bg-white px-2.5 py-1.5 text-xs font-medium hover:bg-red-100"
              onClick={handleAction}
            >
              <ActionIcon className="size-3.5" />
              {action.label}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
