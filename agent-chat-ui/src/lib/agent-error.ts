import type { AgentError } from "@/types/agent-block";
import type { PersistedRunFailure } from "@/components/thread/process-events";

function errorText(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (!error || typeof error !== "object") return String(error ?? "");
  const value = error as Record<string, unknown>;
  return [value.message, value.detail, value.error, value.code]
    .filter((item) => typeof item === "string")
    .join(" ");
}

/** 将 SDK/模型供应商异常转换为稳定、面向用户的业务错误。 */
export function normalizeAgentError(error: unknown): AgentError {
  const raw = errorText(error);
  const lower = raw.toLowerCase();

  if (
    lower.includes("model_tool_history_invalid") ||
    lower.includes("同一 tool_call_id 对应多条 toolmessage")
  ) {
    return {
      code: "CONVERSATION_HISTORY_INVALID",
      message: "当前对话的历史记录无法继续使用。",
      detail: "这是旧对话中的工具调用记录异常，不是模型供应商故障。请新建对话后重新发起请求。",
      retryable: false,
    };
  }

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

/** Convert a backend terminal failure fact into a structured UI error card. */
export function normalizePersistedRunFailure(
  failure: PersistedRunFailure,
): AgentError {
  const code = failure.code.toUpperCase();
  if (code === "MODEL_TOOL_HISTORY_INVALID") {
    return {
      code: "CONVERSATION_HISTORY_INVALID",
      message: "当前对话的历史记录无法继续使用。",
      detail: "这是旧对话中的工具调用记录异常，不是模型供应商故障。请新建对话后重新发起请求。",
      retryable: false,
    };
  }
  if (
    code.startsWith("MODEL_") ||
    code === "SYNTHESIS_TOOL_CALL_BLOCKED"
  ) {
    return {
      code: "MODEL_OUTPUT_INVALID",
      message: "当前模型未能生成符合展示约束的回复。",
      detail: failure.message,
      retryable: true,
      action: { type: "retry", label: "重试" },
    };
  }
  return {
    code: "UNKNOWN",
    message: "本次请求未能完成。",
    detail: failure.message,
    retryable: true,
    action: { type: "retry", label: "重试" },
  };
}
