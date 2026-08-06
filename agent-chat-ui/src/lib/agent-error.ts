import type { AgentError } from "@/types/agent-block";

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (!error || typeof error !== "object") return String(error ?? "");
  const value = error as Record<string, unknown>;
  return [value.message, value.detail, value.error, value.code]
    .filter((item) => typeof item === "string")
    .join(" ");
}

/** Convert SDK/provider failures into stable user-facing business errors. */
export function normalizeAgentError(error: unknown): AgentError {
  const raw = errorText(error);
  const lower = raw.toLowerCase();

  if (
    lower.includes("function call is not supported") ||
    lower.includes("tool_choice") ||
    lower.includes("function_call") ||
    lower.includes("20037")
  ) {
    return {
      code: "MODEL_NOT_SUPPORTED",
      message: "当前模型不支持 KodAgent 所需的工具调用。",
      detail:
        "这个模型可以进行普通对话，但不能调用待办、日程、会议室和党务文件等业务工具，因此本次 Agent 任务无法继续。请在输入框底部切换到支持 Function Calling / Tool Calling 的模型。",
      retryable: false,
      action: { type: "retry", label: "切换模型" },
    };
  }

  if (lower.includes("401") || lower.includes("unauthorized")) {
    return {
      code: "SESSION_EXPIRED",
      message: "模型供应商认证失败。",
      detail: "请到设置中检查该供应商的 API Key 和访问地址。",
      retryable: true,
      action: { type: "retry", label: "检查模型设置" },
    };
  }

  if (lower.includes("timeout") || lower.includes("timed out")) {
    return {
      code: "UPSTREAM_TIMEOUT",
      message: "模型供应商响应超时。",
      detail: "业务数据没有被提交。请稍后重试，或切换到响应更快的模型。",
      retryable: true,
    };
  }

  if (lower.includes("400") || lower.includes("badrequest")) {
    return {
      code: "UPSTREAM_BAD_REQUEST",
      message: "模型供应商拒绝了本次请求。",
      detail: "通常是模型参数或模型能力不匹配。请检查模型设置，或换一个支持 Agent 工具调用的模型。",
      retryable: false,
      action: { type: "retry", label: "切换模型" },
    };
  }

  return {
    code: "UNKNOWN",
    message: "Agent 处理请求时发生异常。",
    detail: "请求没有完成，业务数据未提交。请稍后重试；如果持续出现，请联系管理员并提供发生时间。",
    retryable: true,
  };
}
