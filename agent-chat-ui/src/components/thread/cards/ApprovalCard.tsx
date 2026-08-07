import {
  Building2,
  CalendarDays,
  Check,
  CheckCircle2,
  ClipboardCheck,
  Loader2,
  Users,
  X,
} from "lucide-react";
import { useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  buildApprovalDecisionRequest,
  buildApprovalResumeMetadata,
  getResumeIdempotencyKey,
  shouldRecordResumeAudit,
} from "@/lib/approval-actions";
import { useStreamContext } from "@/providers/Stream";
import type { ApprovalField, ApprovalPayload } from "@/types/agent-block";
import { createAgentStreamOptions } from "@/lib/agent-stream-options";
import {
  getInterruptAction,
  isApprovalInterruptAction,
  isCurrentActionableApproval,
} from "@/lib/meeting-approval-card";
import { displayFieldValue } from "@/lib/card-display";

type ApprovalCardProps = {
  payload?: ApprovalPayload;
  interrupt?: unknown;
};

function fieldsFromDraft(draft?: Record<string, unknown>): ApprovalField[] {
  if (!draft) return [];
  const names = Array.isArray(draft.attendeeUserNames)
    ? draft.attendeeUserNames.map(String).join(", ")
    : Array.isArray(draft.attendeeUserIds)
      ? draft.attendeeUserIds.length > 0
        ? `已关联参会人（${draft.attendeeUserIds.length} 人）`
        : "未提供"
      : "未提供";
  const meetingRoomName =
    typeof draft.meetingRoomName === "string" && draft.meetingRoomName.trim()
      ? draft.meetingRoomName
      : draft.meetingRoomId != null
        ? "已关联会议室"
        : "未提供";
  return [
    { label: "主题", value: String(draft.subject ?? "") },
    {
      label: "会议室",
      value: String(meetingRoomName ?? ""),
    },
    {
      label: "时间",
      value: [draft.startTime, draft.endTime]
        .filter(Boolean)
        .map(String)
        .join(" - "),
    },
    { label: "参会人", value: names },
  ];
}

function FieldIcon({ label }: { label: string }) {
  if (label === "会议室") return <Building2 className="size-4 shrink-0" />;
  if (label === "时间") return <CalendarDays className="size-4 shrink-0" />;
  if (label === "参会人") return <Users className="size-4 shrink-0" />;
  return <span className="size-4 shrink-0" />;
}

function approvalTitle(payload?: ApprovalPayload, actionName?: string) {
  if (payload?.title) return payload.title;
  if (payload?.cardType === "meeting_booking") return "预约会议室";
  if (payload?.cardType === "approval_task") return payload.title || "确认审批";
  if (payload?.cardType === "approval_request") return payload.title || "确认审批申请";
  if (payload?.cardType === "approval_withdraw") return payload.title || "确认撤回审批";
  if (payload?.cardType === "approval_withdraw") return payload.title || "确认撤回审批";
  if (payload?.cardType === "party_file_approval") return "确认党务文件操作";
  if (actionName === "confirm_meeting_booking") return "预约会议室";
  if (actionName === "confirm_create_party_file") return "发布党务文件";
  if (actionName === "confirm_update_party_file") return "更新党务文件";
  if (actionName === "confirm_delete_party_file") return "删除党务文件";
  return "待确认操作";
}

export function ApprovalCard({ payload, interrupt }: ApprovalCardProps) {
  const thread = useStreamContext();
  const action = getInterruptAction(interrupt);
  const draftId = payload?.draftId;
  const approvalId = payload?.approvalId;
  // Keep the Card and InterruptSlot on one protocol whitelist. Otherwise a
  // newly supported ApprovalCard action could render in one place but be
  // reported as malformed or non-actionable in the other.
  const isCurrentInterrupt = isApprovalInterruptAction(interrupt);
  const isBatchApproval = payload?.cardType === "approval_batch";
  const canSubmit = isCurrentActionableApproval(payload, interrupt);
  const draft = payload?.draft;
  // React state updates are asynchronous. This ref closes the same-event-loop
  // gap where a rapid second click could otherwise start another resume.
  const resumeSubmittingRef = useRef(false);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<
    "idle" | "approved" | "rejected" | "error"
  >("idle");
  const [errorText, setErrorText] = useState("");
  const [resumeAuditStatus, setResumeAuditStatus] = useState<
    "idle" | "pending" | "recorded" | "failed"
  >("idle");
  const [resumeAuditError, setResumeAuditError] = useState("");
  const effectiveStatus =
    status !== "idle"
      ? status
      : payload?.status === "APPROVED"
        ? "approved"
        : payload?.status === "REJECTED"
          ? "rejected"
          : payload?.status === "EXPIRED"
            ? "expired"
            : "idle";
  const settled =
    effectiveStatus === "approved" ||
    effectiveStatus === "rejected" ||
    effectiveStatus === "expired";

  const fields = useMemo(
    () => (payload?.fields?.length ? payload.fields : fieldsFromDraft(draft)),
    [draft, payload?.fields],
  );
  const actionName = payload?.action || action?.name;

  const recordResumeAudit = async () => {
    if (!canSubmit || !approvalId) {
      throw new Error("审批记录不存在，无法记录 Agent resume");
    }
    const response = await fetch(
      `/api/agent-approvals/${encodeURIComponent(approvalId)}/resume`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resumeIdempotencyKey: getResumeIdempotencyKey(approvalId),
        }),
        cache: "no-store",
      },
    );
    if (!response.ok) {
      const detail = await response
        .json()
        .then(
          (body) =>
            (body?.msg ?? body?.message ?? body?.error) as string | undefined,
        )
        .catch(() => undefined);
      throw new Error(detail || "Agent resume 审计记录失败");
    }
  };

  const retryResumeAudit = async () => {
    if (
      submitting ||
      status !== "approved" ||
      !shouldRecordResumeAudit("approve")
    ) {
      return;
    }
    setSubmitting(true);
    setResumeAuditStatus("pending");
    setResumeAuditError("");
    try {
      await recordResumeAudit();
      setResumeAuditStatus("recorded");
      toast.success("审计记录已补齐", { richColors: true, closeButton: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : "请稍后重试";
      setResumeAuditStatus("failed");
      setResumeAuditError(message);
      toast.error("审计记录仍未完成", {
        description: "预约业务已经执行，不会重复提交；可稍后重试记录。",
        richColors: true,
        closeButton: true,
      });
    } finally {
      setSubmitting(false);
    }
  };

  const resume = async (type: "approve" | "reject") => {
    if (resumeSubmittingRef.current || submitting || settled) return;
    resumeSubmittingRef.current = true;
    const approveLabel = payload?.approveLabel || "确认";
    const rejectLabel = payload?.rejectLabel || "取消";
    setSubmitting(true);
    setErrorText("");
    let approvalPersisted = false;
    try {
      if (!canSubmit || !approvalId || !draftId) {
        throw new Error("当前审批上下文不完整，无法提交；请重新生成预约审批");
      }
      const decisionRequest = buildApprovalDecisionRequest(
        {
          approvalId,
          draftId,
          operationId: payload?.operationId,
          threadId: payload?.threadId,
          runId: payload?.runId,
          messageId: payload?.messageId,
          cardType: payload?.cardType,
        },
        type,
      );
      const response = await fetch(decisionRequest.url, decisionRequest.init);
      if (!response.ok) {
        const detail = await response
          .json()
          .then((body) => (body?.msg ?? body?.message) as string | undefined)
          .catch(() => undefined);
        throw new Error(detail || "操作未生效，请稍后重试");
      }
      approvalPersisted = true;
      const resumeMetadata = buildApprovalResumeMetadata({
        approvalId,
        draftId,
        operationId: payload?.operationId,
        threadId: payload?.threadId,
        runId: payload?.originRunId || payload?.runId,
        messageId: payload?.messageId,
      });
      const resumeAuditBeforeGraph =
        shouldRecordResumeAudit(type) && !isBatchApproval;
      if (resumeAuditBeforeGraph) {
        // Every non-batch write executor requires this durable proof before
        // the resumed graph can claim its Effect. Recording it after submit
        // is too late for meeting, schedule, file, request, and task writes.
        setResumeAuditStatus("pending");
        await recordResumeAudit();
        setResumeAuditStatus("recorded");
      }
      // The Java approval record is durable.  LangGraph is resumed exactly
      // once by this action; the separate Java resume endpoint below only
      // records the audit fact and never resumes the graph again.
      await thread.submit(
        {},
        createAgentStreamOptions({
          metadata: resumeMetadata,
          command: { resume: { decisions: [{ type }] } },
        }),
      );
      if (!shouldRecordResumeAudit(type) || isBatchApproval) {
        setStatus(type === "reject" ? "rejected" : "approved");
        toast.success(type === "reject" ? `已${rejectLabel}` : `已${approveLabel}`, {
          description: type === "reject" ? "该操作已取消，不会产生后续影响。" : "批量审批已提交执行。",
          richColors: true,
          closeButton: true,
        });
        return;
      }

      // The Java approval and resume facts were written before this call. The
      // graph now owns the remaining business execution and its outcome.
      setStatus("approved");
      toast.success(`已${approveLabel}`, {
        description: isBatchApproval
          ? "批量审批已提交执行。"
          : "审批与 Agent resume 审计记录均已保存。",
        richColors: true,
        closeButton: true,
      });
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "操作失败，请稍后重试";
      // The decision write is idempotent. Keep the card in an actionable error
      // state when resume fails so the inline retry/error explanation remains
      // visible and a retry cannot create a second business decision.
      setStatus("error");
      setErrorText(
        approvalPersisted
          ? `审批状态已记录，但 Agent 尚未恢复：${message}。请点击重试。`
          : message,
      );
      toast.error(message, {
        description: approvalPersisted
          ? "审批记录已保存，当前只需重新恢复 Agent。"
          : "本次操作未生效，请重试或稍后再操作。",
        richColors: true,
        closeButton: true,
      });
    } finally {
      resumeSubmittingRef.current = false;
      setSubmitting(false);
    }
  };

  return (
    <div
      className={
        "my-2 w-full max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm transition-opacity" +
        (settled ? " opacity-75" : "")
      }
    >
      <div className="mb-4 flex items-center gap-2 text-base font-semibold">
        {payload?.cardType === "meeting_booking" ||
        actionName === "confirm_meeting_booking" ? (
          <CalendarDays className="size-5 text-slate-600" />
        ) : (
          <ClipboardCheck className="size-5 text-slate-600" />
        )}
        <span>{approvalTitle(payload, actionName)}</span>
        {!canSubmit && (
          <span className="text-muted-foreground ml-auto text-xs font-normal">
            仅供查看
          </span>
        )}
      </div>
      <div className="grid gap-3 text-sm text-slate-700">
        {fields.map((field) => (
          <div
            className="flex items-start gap-3"
            key={field.label}
          >
            <FieldIcon label={field.label} />
            <span className="w-16 shrink-0 text-slate-500">{field.label}</span>
            <span>
              {displayFieldValue(field.label, field.value, {
                cardType: payload?.cardType,
                domain:
                  payload?.cardType?.startsWith("party_file")
                    ? "party_file"
                    : payload?.cardType === "meeting_booking"
                      ? "meeting"
                      : payload?.cardType === "personal_schedule"
                        ? "schedule"
                        : "approval",
              })}
            </span>
          </div>
        ))}
      </div>
      {settled ? (
        <div className="mt-5 border-t border-slate-100 pt-4">
          <div className="flex items-center gap-2 text-sm font-medium text-emerald-700">
            <CheckCircle2 className="size-4 shrink-0" />
            <span>
              {effectiveStatus === "approved"
                ? `已${payload?.approveLabel || "确认"}`
                : effectiveStatus === "rejected"
                  ? `已${payload?.rejectLabel || "取消"}`
                  : "审批已过期"}
            </span>
          </div>
          {effectiveStatus === "approved" && resumeAuditStatus === "failed" && (
            <div className="mt-3 flex items-start justify-between gap-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <div>
                <div className="font-medium">审计记录待补齐</div>
                <div className="mt-1">
                  预约业务已经执行，不会重复提交。
                  {resumeAuditError ? `（${resumeAuditError}）` : ""}
                </div>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={submitting}
                onClick={retryResumeAudit}
              >
                {submitting ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : null}
                重试审计记录
              </Button>
            </div>
          )}
          {effectiveStatus === "approved" &&
            resumeAuditStatus === "pending" && (
              <div className="mt-2 text-xs text-slate-500">
                正在保存 resume 审计记录…
              </div>
            )}
        </div>
      ) : !canSubmit ? (
        <div className="mt-5 border-t border-slate-100 pt-4 text-xs text-slate-500">
          {isCurrentInterrupt
            ? "当前确认上下文不完整，无法操作。请重新生成待确认草稿。"
            : "历史审批记录仅供查看，当前不可操作。"}
        </div>
      ) : (
        <div className="mt-5 border-t border-slate-100 pt-4">
          {status === "error" && errorText && (
            <div className="mb-3 flex items-start gap-2 rounded-md bg-red-50 px-3 py-2 text-xs text-red-700">
              <X className="mt-0.5 size-3.5 shrink-0" />
              <span>{errorText}</span>
            </div>
          )}
          <div className="flex gap-2">
            <Button
              type="button"
              disabled={
                submitting ||
                !canSubmit ||
                payload?.allowedActions?.includes("approve") === false
              }
              onClick={() => resume("approve")}
            >
              {submitting ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Check className="size-4" />
              )}
              {status === "error" ? "重试" : payload?.approveLabel || "确认"}
            </Button>
            <Button
              type="button"
              variant="outline"
              disabled={
                submitting ||
                !canSubmit ||
                payload?.allowedActions?.includes("reject") === false
              }
              onClick={() => resume("reject")}
            >
              <X className="size-4" />
              {payload?.rejectLabel || "取消"}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
