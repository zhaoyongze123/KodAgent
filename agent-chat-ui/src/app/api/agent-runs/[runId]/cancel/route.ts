import { NextRequest, NextResponse } from "next/server";
import {
  getOaAgentErrorStatus,
  getOaAgentHeaders,
} from "@/lib/oa-agent-request";

export const runtime = "nodejs";

/**
 * 安全读取上游响应正文。
 *
 * LangGraph 和 Java 的错误响应不保证都是 JSON；取消链路需要把原始信息
 * 返回给浏览器用于诊断，但不能因解析失败而掩盖真实 HTTP 状态。
 */
async function readResponseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

/**
 * 取消 LangGraph Run，再记录 Java 审计事实。
 *
 * 参数：
 * - request：浏览器请求，携带 HttpOnly 的 OA 身份 Cookie。
 * - runId：要取消的 LangGraph Run 标识。
 * - threadId：Run 所属会话标识，LangGraph 取消接口必填。
 *
 * 职责边界：LangGraph 是 Run 是否真正中断的事实源；Java 仅记录审计事件。
 * 所以绝不能在 LangGraph 拒绝取消（例如已完成或不存在）时把 Java Run
 * 标记为 CANCELLED。
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ runId: string }> },
) {
  const { runId } = await params;
  const body = (await request.json().catch(() => ({}))) as Record<
    string,
    unknown
  >;
  const threadId = String(body.threadId ?? "").trim();
  if (!threadId) {
    return NextResponse.json(
      {
        status: "NOT_CANCELLED",
        error: "THREAD_ID_REQUIRED",
        detail: "取消运行必须提供 threadId。",
      },
      { status: 400 },
    );
  }

  const langGraphBaseUrl =
    process.env.LANGGRAPH_API_URL ?? "http://127.0.0.1:2024";
  const langSmithApiKey = process.env.LANGSMITH_API_KEY;
  const identity = request.cookies.get("oa_agent_identity")?.value;
  const baseUrl = process.env.OA_AGENT_BASE_URL ?? "http://127.0.0.1:48080";
  let langGraphCancelled = false;
  let cancelledRun: unknown = null;

  try {
    // 先请求 LangGraph 真正中断后台执行。身份必须与普通 LangGraph 请求一致，
    // 否则会把用户 A 的停止请求错误地作用在用户 B 的会话上。
    const langGraphResponse = await fetch(
      `${langGraphBaseUrl.replace(/\/$/, "")}/threads/${encodeURIComponent(threadId)}/runs/${encodeURIComponent(runId)}/cancel?wait=true&action=interrupt`,
      {
        method: "POST",
        headers: {
          Accept: "application/json",
          ...(langSmithApiKey ? { "x-api-key": langSmithApiKey } : {}),
          // 与 agent-state 路由一致，传入 OA Cookie 中编码后的用户身份。
          ...(identity
            ? { "X-Agent-Identity": decodeURIComponent(identity) }
            : {}),
        },
        cache: "no-store",
      },
    );
    const langGraphBody = await readResponseBody(langGraphResponse);

    // 已结束或不存在的 Run 不能被写成 CANCELLED。原样保留上游状态，
    // 让前端重新同步真实 Run，而不是覆盖成一个虚假的本地终态。
    if (!langGraphResponse.ok) {
      return NextResponse.json(
        {
          status: "NOT_CANCELLED",
          error: "LANGGRAPH_RUN_NOT_CANCELLABLE",
          langgraphStatus: langGraphResponse.status,
          detail: langGraphBody,
        },
        {
          status: langGraphResponse.status,
          headers: { "Cache-Control": "no-store, max-age=0" },
        },
      );
    }
    langGraphCancelled = true;
    cancelledRun = langGraphBody;

    // 只有 LangGraph 确认中断后，才追加 Java 审计。Java 不是执行控制面，
    // 因而不能放在这个请求之前。
    const headers = await getOaAgentHeaders("agent:audit");
    const auditResponse = await fetch(
      `${baseUrl}/agent/runs/${encodeURIComponent(runId)}/cancel`,
      {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({
          threadId,
          messageId: String(body.messageId ?? ""),
        }),
        cache: "no-store",
      },
    );
    const auditBody = await readResponseBody(auditResponse);
    if (!auditResponse.ok) {
      // 执行已经在 LangGraph 中中断，不能误报为“仍在运行”。同时给出明确
      // 信号，方便后续补偿审计事件，避免把 Java 失败伪装成完整成功。
      return NextResponse.json(
        {
          status: "CANCELLED_AUDIT_PENDING",
          cancelled: true,
          langgraph: langGraphBody,
          auditStatus: auditResponse.status,
          auditDetail: auditBody,
        },
        { status: 502, headers: { "Cache-Control": "no-store, max-age=0" } },
      );
    }

    return NextResponse.json(
      {
        status: "CANCELLED",
        cancelled: true,
        langgraph: langGraphBody,
        audit: auditBody,
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  } catch (error) {
    if (langGraphCancelled) {
      // LangGraph 已是事实上的取消结果，后续审计调用抛错也不能退回成
      // NOT_CANCELLED；调用方应停止恢复该 Run，并由运维补齐审计。
      return NextResponse.json(
        {
          status: "CANCELLED_AUDIT_PENDING",
          cancelled: true,
          langgraph: cancelledRun,
          auditDetail: error instanceof Error ? error.message : String(error),
        },
        { status: 502, headers: { "Cache-Control": "no-store, max-age=0" } },
      );
    }
    return NextResponse.json(
      {
        status: "NOT_CANCELLED",
        error: "Agent run cancellation service is unavailable",
        detail: error instanceof Error ? error.message : String(error),
      },
      { status: getOaAgentErrorStatus(error) },
    );
  }
}
