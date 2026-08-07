import {
  isResultKind,
  type ResultEnvelope,
  type ResultPresentation,
} from "./result-presentation.ts";

export type AgentErrorCode =
  | "SESSION_EXPIRED"
  | "PERMISSION_DENIED"
  | "EMPTY_RESULT"
  | "UPSTREAM_TIMEOUT"
  | "UPSTREAM_BAD_REQUEST"
  | "MODEL_NOT_SUPPORTED"
  | "CLIPBOARD_UNAVAILABLE"
  | "VALIDATION_FAILED"
  | "UNKNOWN";

export type ApprovalField = {
  label: string;
  value: string;
  icon?: string;
};

export type ApprovalPayload = {
  approvalId: string;
  draftId: string;
  operationId?: string;
  threadId?: string;
  runId?: string;
  originRunId?: string;
  resumeRunId?: string;
  messageId?: string;
  action: string;
  status: "PENDING" | "APPROVED" | "REJECTED" | "EXPIRED";
  fields: ApprovalField[];
  allowedActions: Array<"approve" | "reject">;
  cardType?: string;
  title?: string;
  approveLabel?: string;
  rejectLabel?: string;
  expiresAt?: string;
  draft?: Record<string, unknown>;
};

export type CalendarEventItem = {
  sourceType?: string;
  title?: string;
  startTime?: string;
  endTime?: string;
  location?: string;
  meetingRoomName?: string;
  attendeeUserNicknames?: string[];
  editable?: boolean;
};

export type CalendarPayload = {
  events: CalendarEventItem[];
};

export type TodoItem = {
  taskId?: string;
  name?: string;
  processDefinitionName?: string;
  startUserName?: string;
  createdTime?: string;
};

export type TodoPayload = {
  total: number;
  items: TodoItem[];
};

export type ApprovalInboxItem = {
  taskId?: string;
  name?: string;
  processDefinitionName?: string;
  processDefinitionKey?: string;
  startUserName?: string;
  departmentName?: string;
  amount?: number;
  createdTime?: string;
  pendingDays?: number;
  exclusionReasons?: string[];
};

/** Read-only result of Java-side deterministic approval inbox filtering. */
export type ApprovalInboxPayload = {
  totalPending: number;
  scannedCount: number;
  matchedCount: number;
  candidates: ApprovalInboxItem[];
  excludedCount: number;
  exclusions: ApprovalInboxItem[];
  exclusionReasonCounts: Record<string, number>;
  truncated: boolean;
};

export type ApprovalBatchPayload = {
  previewId?: string;
  confirmationToken?: string;
  batchId?: string;
  action?: string;
  reason?: string;
  taskCount?: number;
  tasks?: ApprovalInboxItem[];
  results?: Array<{ taskId?: string; status?: string; message?: string }>;
  status?: string;
};
export type ApprovalInsightPayload = {
  scannedCount?: number;
  summary?: string;
  anomalies?: Array<{ taskId?: string; processName?: string; startUserName?: string; departmentName?: string; amount?: number; reasons?: string[] }>;
  groups?: Array<{ key?: string; count?: number; totalAmount?: number; maxPendingDays?: number }>;
};

export type ApprovalWorkflowPayload = {
  title: string;
  fields: ApprovalField[];
  statusText?: string;
};

export type PartyFileItem = {
  id?: string;
  title?: string;
  categoryId?: string;
  categoryName?: string;
  summary?: string;
  content?: string;
  publishTime?: string;
  status?: string;
  readStatus?: boolean;
  attachments?: PartyFileAttachment[];
  attachmentStatus?: "AVAILABLE" | "NONE" | "UNKNOWN" | string;
  attachmentCount?: number;
  attachmentMessage?: string;
};

export type PartyFileAttachment = {
  id?: string;
  name?: string;
  type?: string;
  size?: number;
};

export type PartyFilePayload = {
  total: number;
  items: PartyFileItem[];
  view?: "list" | "detail" | "attachments";
};

export type PartyFileCitation = {
  documentId?: string;
  chunkId?: string;
  section?: string;
  ordinal?: number;
};

export type PartyFileKnowledgeDocument = {
  id?: string;
  title?: string;
  docType?: string;
  status?: string;
  origin?: string;
  publishTime?: string;
};

export type PartyFileKnowledgeHit = {
  score?: number;
  document: PartyFileKnowledgeDocument;
  citation?: PartyFileCitation;
  content?: string;
};

export type PartyFileKnowledgePayload = {
  query?: string;
  total: number;
  hits: PartyFileKnowledgeHit[];
  status?: string;
  question?: string;
  document?: PartyFileKnowledgeDocument;
  content?: string;
  evidence: Array<{ citation?: PartyFileCitation; quote?: string }>;
};

export type PartyFileComparePayload = {
  status?: string;
  left: PartyFileKnowledgeDocument;
  right: PartyFileKnowledgeDocument;
  added: string[];
  removed: string[];
  changedLineCount: number;
};

export type PartyFileComplianceCheck = {
  requirement?: string;
  status?: string;
  evidence?: string;
  citation?: PartyFileCitation;
};

export type PartyFileCompliancePayload = {
  verdict?: string;
  canSubmit?: boolean;
  taskId?: string;
  document?: PartyFileKnowledgeDocument;
  checks: PartyFileComplianceCheck[];
  requirements: string[];
  missingMaterials: string[];
};

export type BusinessReportPayload = {
  reportType?: "meeting" | "schedule" | "party_file" | string;
  startTime?: string;
  endTime?: string;
  total?: number;
  totalMinutes?: number;
  busyMinutes?: number;
  conflictCount?: number;
  totalAmount?: number;
  amountCount?: number;
  readCount?: number;
  unreadCount?: number;
  byDay?: Record<string, number>;
  byRoom?: Record<string, number>;
  bySource?: Record<string, number>;
  byCategory?: Record<string, number>;
  byProcess?: Record<string, number>;
  byDepartment?: Record<string, number>;
  items?: Array<Record<string, unknown>>;
  events?: Array<Record<string, unknown>>;
};

export type AgentCard =
  | { type: "approval"; payload: ApprovalPayload }
  | { type: "approval_workflow"; payload: ApprovalWorkflowPayload }
  | { type: "calendar"; payload: CalendarPayload }
  | { type: "todo"; payload: TodoPayload }
  | { type: "approval_inbox"; payload: ApprovalInboxPayload }
  | { type: "approval_batch_preview"; payload: ApprovalBatchPayload }
  | { type: "approval_batch_result"; payload: ApprovalBatchPayload }
  | { type: "approval_insights"; payload: ApprovalInsightPayload }
  | { type: "party_file"; payload: PartyFilePayload }
  | { type: "party_file_knowledge"; payload: PartyFileKnowledgePayload }
  | { type: "party_file_compare"; payload: PartyFileComparePayload }
  | { type: "party_file_compliance"; payload: PartyFileCompliancePayload }
  | { type: "business_report"; payload: BusinessReportPayload };

export type ToolPresentation = {
  blockType?: "narration" | "process" | "card" | "error";
  /** Canonical result contract. `cardType` remains a compatibility adapter. */
  resultKind?: ResultPresentation["resultKind"];
  sourceResultId?: string;
  resultGroupId?: string;
  primaryResult?: boolean;
  title?: string;
  summary?: string;
  headline?: string;
  displayPolicy?: ResultPresentation["displayPolicy"];
  cardType?: "approval" | "approval_template" | "approval_preview" | "approval_submission" | "approval_task" | "approval_request" | "approval_withdraw" | "approval_request_result" | "approval_inbox" | "approval_applications" | "approval_application" | "approval_history" | "approval_batch_preview" | "approval_batch_result" | "approval_batch" | "approval_insights" | "business_report" | "calendar" | "todo" | "party_file" | "party_file_approval" | "party_file_knowledge" | "party_file_compare" | "party_file_compliance";
};

export type AgentError = {
  code: AgentErrorCode;
  message: string;
  detail?: string;
  retryable: boolean;
  action?: {
    type: "login" | "retry" | "open_oa";
    label: string;
  };
};

export type AgentBlock =
  | { kind: "narration"; markdown: string }
  | { kind: "process"; events: unknown[] }
  | { kind: "card"; card: AgentCard }
  | { kind: "result"; result: ResultEnvelope }
  | { kind: "error"; error: AgentError };

export type NormalizedToolResponse = {
  ok: boolean;
  data?: unknown;
  error?: { code?: string; message?: string } | null;
  presentation?: ToolPresentation;
  resultKind?: ResultPresentation["resultKind"];
  sourceResultId?: string;
  resultGroupId?: string;
  primaryResult?: boolean;
};

export function isApprovalPayload(value: unknown): value is ApprovalPayload {
  if (!value || typeof value !== "object") return false;
  const payload = value as Partial<ApprovalPayload>;
  return (
    typeof payload.approvalId === "string" &&
    typeof payload.draftId === "string" &&
    typeof payload.action === "string" &&
    Array.isArray(payload.fields)
  );
}

function formatDateTime(value: unknown): string {
  return typeof value === "string" ? value : value == null ? "" : String(value);
}

/** Build the calendar card payload from a tool result's `data` object. */
export function calendarPayloadFromData(
  data: unknown,
): CalendarPayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const events = (data as { events?: unknown }).events;
  if (!Array.isArray(events)) return undefined;
  return {
    events: events.map((raw) => {
      const item = (raw ?? {}) as Record<string, unknown>;
      const names = Array.isArray(item.attendeeUserNicknames)
        ? item.attendeeUserNicknames.map(String)
        : [];
      return {
        sourceType:
          typeof item.sourceType === "string" ? item.sourceType : undefined,
        title: typeof item.title === "string" ? item.title : undefined,
        startTime: formatDateTime(item.startTime) || undefined,
        endTime: formatDateTime(item.endTime) || undefined,
        location: typeof item.location === "string" ? item.location : undefined,
        meetingRoomName:
          typeof item.meetingRoomName === "string"
            ? item.meetingRoomName
            : undefined,
        attendeeUserNicknames: names,
        editable:
          typeof item.editable === "boolean" ? item.editable : undefined,
      };
    }),
  };
}

/** Build the pending-approvals card payload from a tool result's `data` object. */
export function todoPayloadFromData(data: unknown): TodoPayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as { total?: unknown; list?: unknown };
  const list = Array.isArray(record.list) ? record.list : undefined;
  if (!list) return undefined;
  const total = typeof record.total === "number" ? record.total : list.length;
  return {
    total,
    items: list.map((raw) => {
      const item = (raw ?? {}) as Record<string, unknown>;
      return {
        taskId: typeof item.taskId === "string" ? item.taskId : undefined,
        name: typeof item.name === "string" ? item.name : undefined,
        processDefinitionName:
          typeof item.processDefinitionName === "string"
            ? item.processDefinitionName
            : undefined,
        startUserName:
          typeof item.startUserName === "string"
            ? item.startUserName
            : undefined,
        createdTime: formatDateTime(item.createdTime) || undefined,
      };
    }),
  };
}

function approvalInboxItemFromData(raw: unknown): ApprovalInboxItem {
  const item = (raw ?? {}) as Record<string, unknown>;
  const result: ApprovalInboxItem = {};
  if (typeof item.taskId === "string") result.taskId = item.taskId;
  if (typeof item.name === "string") result.name = item.name;
  if (typeof item.processDefinitionName === "string") {
    result.processDefinitionName = item.processDefinitionName;
  }
  if (typeof item.processDefinitionKey === "string") {
    result.processDefinitionKey = item.processDefinitionKey;
  }
  if (typeof item.startUserName === "string") result.startUserName = item.startUserName;
  if (typeof item.departmentName === "string") result.departmentName = item.departmentName;

  const amount = typeof item.amount === "number"
    ? item.amount
    : typeof item.amount === "string" && item.amount.trim() !== "" && Number.isFinite(Number(item.amount))
      ? Number(item.amount)
      : undefined;
  if (amount !== undefined) result.amount = amount;

  const createdTime = formatDateTime(item.createdTime);
  if (createdTime) result.createdTime = createdTime;
  if (typeof item.pendingDays === "number") result.pendingDays = item.pendingDays;
  if (Array.isArray(item.exclusionReasons)) {
    result.exclusionReasons = item.exclusionReasons.filter(
      (reason): reason is string => typeof reason === "string",
    );
  }
  return result;
}

/** Convert the read-only Java inbox-filter contract without exposing raw form variables. */
export function approvalInboxPayloadFromData(data: unknown): ApprovalInboxPayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as Record<string, unknown>;
  const candidates = Array.isArray(record.candidates) ? record.candidates : undefined;
  if (!candidates) return undefined;
  const exclusions = Array.isArray(record.exclusions) ? record.exclusions : [];
  const reasonCounts = record.exclusionReasonCounts && typeof record.exclusionReasonCounts === "object"
    ? Object.fromEntries(Object.entries(record.exclusionReasonCounts as Record<string, unknown>)
      .filter((entry): entry is [string, number] => typeof entry[1] === "number"))
    : {};
  return {
    totalPending: typeof record.totalPending === "number" ? record.totalPending : candidates.length,
    scannedCount: typeof record.scannedCount === "number" ? record.scannedCount : candidates.length,
    matchedCount: typeof record.matchedCount === "number" ? record.matchedCount : candidates.length,
    candidates: candidates.map(approvalInboxItemFromData),
    excludedCount: typeof record.excludedCount === "number" ? record.excludedCount : exclusions.length,
    exclusions: exclusions.map(approvalInboxItemFromData),
    exclusionReasonCounts: reasonCounts,
    truncated: record.truncated === true,
  };
}

export function approvalBatchPayloadFromData(data: unknown): ApprovalBatchPayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as Record<string, unknown>;
  const payload: ApprovalBatchPayload = {};
  for (const key of ["previewId", "confirmationToken", "batchId", "action", "reason", "status"] as const) {
    if (typeof record[key] === "string") payload[key] = record[key] as string;
  }
  if (typeof record.taskCount === "number") payload.taskCount = record.taskCount;
  if (Array.isArray(record.tasks)) payload.tasks = record.tasks.map(approvalInboxItemFromData);
  if (Array.isArray(record.results)) {
    payload.results = record.results.map((raw) => {
      const item = (raw ?? {}) as Record<string, unknown>;
      return {
        taskId: typeof item.taskId === "string" ? item.taskId : undefined,
        status: typeof item.status === "string" ? item.status : undefined,
        message: typeof item.message === "string" ? item.message : undefined,
      };
    });
  }
  return payload;
}

export function approvalInsightPayloadFromData(data: unknown): ApprovalInsightPayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as Record<string, unknown>;
  return {
    scannedCount: typeof record.scannedCount === "number" ? record.scannedCount : undefined,
    summary: typeof record.summary === "string" ? record.summary : undefined,
    anomalies: Array.isArray(record.anomalies) ? record.anomalies as ApprovalInsightPayload["anomalies"] : [],
    groups: Array.isArray(record.groups) ? record.groups as ApprovalInsightPayload["groups"] : [],
  };
}

export function partyFilePayloadFromData(
  data: unknown,
): PartyFilePayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as {
    total?: unknown;
    list?: unknown;
    id?: unknown;
    attachmentStatus?: unknown;
    attachmentCount?: unknown;
  };
  const rawItems = Array.isArray(record.list)
    ? record.list
    : record.id == null
      ? undefined
      : [record];
  if (!rawItems) return undefined;

  const itemFromData = (raw: unknown): PartyFileItem => {
    const item = (raw ?? {}) as Record<string, unknown>;
    const attachments = Array.isArray(item.attachments)
      ? item.attachments.map((rawAttachment) => {
          const attachment = (rawAttachment ?? {}) as Record<string, unknown>;
          return {
            id: attachment.id == null ? undefined : String(attachment.id),
            name:
              typeof attachment.name === "string"
                ? attachment.name
                : undefined,
            type:
              typeof attachment.type === "string"
                ? attachment.type
                : undefined,
            size:
              typeof attachment.size === "number"
                ? attachment.size
                : undefined,
          };
        })
      : undefined;
    const result: PartyFileItem = {};
    if (item.id != null) result.id = String(item.id);
    if (typeof item.title === "string") result.title = item.title;
    if (item.categoryId != null) result.categoryId = String(item.categoryId);
    if (typeof item.categoryName === "string") result.categoryName = item.categoryName;
    if (typeof item.summary === "string") result.summary = item.summary;
    if (typeof item.content === "string") result.content = item.content;
    const publishTime = formatDateTime(item.publishTime);
    if (publishTime) result.publishTime = publishTime;
    if (item.status != null) result.status = String(item.status);
    if (typeof item.readStatus === "boolean") result.readStatus = item.readStatus;
    if (attachments) result.attachments = attachments;
    if (typeof item.attachmentStatus === "string") result.attachmentStatus = item.attachmentStatus;
    if (typeof item.attachmentCount === "number") result.attachmentCount = item.attachmentCount;
    if (typeof item.attachmentMessage === "string") result.attachmentMessage = item.attachmentMessage;
    return result;
  };
  return {
    total: typeof record.total === "number" ? record.total : rawItems.length,
    items: rawItems.map(itemFromData),
    view: Array.isArray(record.list)
      ? "list"
      : record.attachmentStatus != null || record.attachmentCount != null
        ? "attachments"
        : "detail",
  };
}

function partyFileCitationFromData(value: unknown): PartyFileCitation | undefined {
  if (!value || typeof value !== "object") return undefined;
  const record = value as Record<string, unknown>;
  const result: PartyFileCitation = {};
  if (record.documentId != null) result.documentId = String(record.documentId);
  if (record.chunkId != null) result.chunkId = String(record.chunkId);
  if (typeof record.section === "string") result.section = record.section;
  if (typeof record.ordinal === "number") result.ordinal = record.ordinal;
  return Object.keys(result).length > 0 ? result : undefined;
}

function partyFileKnowledgeDocumentFromData(value: unknown): PartyFileKnowledgeDocument {
  const record = value && typeof value === "object" ? value as Record<string, unknown> : {};
  const result: PartyFileKnowledgeDocument = {};
  const id = record.docId ?? record.id;
  if (id != null) result.id = String(id);
  if (typeof record.title === "string") result.title = record.title;
  if (typeof record.docType === "string") result.docType = record.docType;
  if (record.status != null) result.status = String(record.status);
  if (typeof record.origin === "string") result.origin = record.origin;
  const publishTime = formatDateTime(record.publishDate ?? record.publishTime);
  if (publishTime) result.publishTime = publishTime;
  return result;
}

function partyFileStringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string")
    : [];
}

export function partyFileKnowledgePayloadFromData(
  data: unknown,
): PartyFileKnowledgePayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as Record<string, unknown>;
  const rawHits = Array.isArray(record.hits) ? record.hits : [];
  const rawEvidence = Array.isArray(record.evidence) ? record.evidence : [];
  const hasUnderstandingResult = record.document != null || typeof record.content === "string";
  if (!Array.isArray(record.hits) && !hasUnderstandingResult) return undefined;

  return {
    query: typeof record.query === "string" ? record.query : undefined,
    total: typeof record.total === "number" ? record.total : rawHits.length,
    hits: rawHits.map((raw) => {
      const hit = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
      return {
        score: typeof hit.score === "number" ? hit.score : undefined,
        document: partyFileKnowledgeDocumentFromData(hit.document),
        citation: partyFileCitationFromData(hit.citation),
        content: typeof hit.content === "string" ? hit.content : undefined,
      };
    }),
    status: record.status == null ? undefined : String(record.status),
    question: typeof record.question === "string" ? record.question : undefined,
    document: record.document == null ? undefined : partyFileKnowledgeDocumentFromData(record.document),
    content: typeof record.content === "string" ? record.content : undefined,
    evidence: rawEvidence.map((raw) => {
      const evidence = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
      return {
        citation: partyFileCitationFromData(evidence.citation ?? {
          documentId: evidence.documentId,
          section: evidence.section,
        }),
        quote: typeof evidence.quote === "string" ? evidence.quote : undefined,
      };
    }),
  };
}

export function partyFileComparePayloadFromData(
  data: unknown,
): PartyFileComparePayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as Record<string, unknown>;
  if (record.left == null || record.right == null) return undefined;
  return {
    status: record.status == null ? undefined : String(record.status),
    left: partyFileKnowledgeDocumentFromData(record.left),
    right: partyFileKnowledgeDocumentFromData(record.right),
    added: partyFileStringList(record.added),
    removed: partyFileStringList(record.removed),
    changedLineCount: typeof record.changedLineCount === "number" ? record.changedLineCount : 0,
  };
}

export function partyFileCompliancePayloadFromData(
  data: unknown,
): PartyFileCompliancePayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as Record<string, unknown>;
  if (!Array.isArray(record.checks) && !Array.isArray(record.missingMaterials)) return undefined;
  const rawChecks = Array.isArray(record.checks) ? record.checks : [];
  return {
    verdict: record.verdict == null ? undefined : String(record.verdict),
    canSubmit: typeof record.canSubmit === "boolean" ? record.canSubmit : undefined,
    taskId: record.taskId == null ? undefined : String(record.taskId),
    document: record.document == null ? undefined : partyFileKnowledgeDocumentFromData(record.document),
    checks: rawChecks.map((raw) => {
      const check = raw && typeof raw === "object" ? raw as Record<string, unknown> : {};
      return {
        requirement: typeof check.requirement === "string" ? check.requirement : undefined,
        status: check.status == null ? undefined : String(check.status),
        evidence: typeof check.evidence === "string" ? check.evidence : undefined,
        citation: partyFileCitationFromData(check.citation),
      };
    }),
    requirements: partyFileStringList(record.requirements),
    missingMaterials: partyFileStringList(record.missingMaterials),
  };
}

function stringField(label: string, value: unknown): ApprovalField {
  return { label, value: value == null ? "未提供" : String(value) };
}

export function approvalWorkflowPayloadFromData(
  cardType: string | undefined,
  data: unknown,
): ApprovalWorkflowPayload | undefined {
  if (!data || typeof data !== "object") return undefined;
  const record = data as Record<string, unknown>;
  if (cardType === "approval_template") {
    const templates = Array.isArray(record.templates) ? record.templates : [];
    return {
      title: "可发起审批",
      fields: templates.map((raw) => {
        const item = (raw ?? {}) as Record<string, unknown>;
        return stringField(String(item.processDefinitionName ?? "审批模板"), item.description ?? item.category ?? "");
      }),
    };
  }
  if (cardType === "approval_preview") {
    const request = (record.request ?? {}) as Record<string, unknown>;
    const preview = (record.preview ?? {}) as Record<string, unknown>;
    return {
      title: "审批链预览",
      fields: [
        stringField("类型", request.requestType === "leave" ? "请假" : request.requestType === "trip" ? "出差" : request.requestType),
        stringField("时间", [request.startTime, request.endTime].filter(Boolean).join(" - ")),
        stringField("原因", request.reason),
        stringField("审批链", preview.normalizedSummary),
      ],
      statusText: preview.requiresApprovalSelection === true ? "流程要求选择审批人，请转 OA 页面完成。" : "请确认信息后再提交。",
    };
  }
  if (cardType === "approval_submission") {
    return {
      title: "审批已提交",
      fields: [stringField("状态", "已提交"), stringField("结果", record.message ?? "提交成功")],
    };
  }
  if (cardType === "approval_request" || cardType === "approval_withdraw" || cardType === "approval_request_result") {
    const draft = (record.draft ?? record) as Record<string, unknown>;
    const isWithdraw = cardType === "approval_withdraw" || String(draft.operation ?? "") === "WITHDRAW";
    return {
      title: isWithdraw ? "审批撤回" : cardType === "approval_request_result" ? "审批申请结果" : "审批申请确认",
      fields: isWithdraw
        ? [stringField("操作", "撤回审批流程"), stringField("撤回原因", draft.reason)]
        : [stringField("类型", draft.requestType === "leave" ? "请假" : draft.requestType === "trip" ? "出差" : draft.requestType), stringField("时间", [draft.startTime, draft.endTime].filter(Boolean).join(" - ")), stringField("原因", draft.reason), stringField("结果", record.message)],
      statusText: typeof record.message === "string" ? record.message : undefined,
    };
  }
  if (cardType === "approval_task") {
    return {
      title: "待办审批详情",
      fields: [
        stringField("任务", record.name),
        stringField("发起人", record.startUserName),
        stringField("流程", record.processDefinitionName),
      ],
      statusText: record.reasonRequire === true ? "审批意见必填。" : undefined,
    };
  }
  if (cardType === "approval_applications" || cardType === "approval_history" || cardType === "approval_application") {
    const items = Array.isArray(record.items) ? record.items : [];
    const source = cardType === "approval_application" ? record : (items[0] ?? {}) as Record<string, unknown>;
    const rows = items.length > 0 ? items : [source];
    const fields = rows.slice(0, 8).map((raw, index) => {
      const item = (raw ?? {}) as Record<string, unknown>;
      const label = item.name ?? item.processDefinitionName ?? item.taskDefinitionKey ?? `记录 ${index + 1}`;
      const value = item.startTime ?? item.createTime ?? item.endTime;
      if (value != null) return stringField("时间", value);
      if (item.status != null) return stringField("状态", item.status);
      return stringField("记录", label);
    });
    return {
      title: cardType === "approval_applications" ? "我发起的审批" : cardType === "approval_history" ? "已办审批历史" : "审批流程详情",
      fields,
      statusText: typeof record.total === "number" ? `共 ${record.total} 条记录` : undefined,
    };
  }
  return undefined;
}

function toolResponse(value: unknown): NormalizedToolResponse | undefined {
  if (value && typeof value === "object") {
    const response = value as Partial<NormalizedToolResponse>;
    if (typeof response.ok === "boolean")
      return response as NormalizedToolResponse;
  }
  if (typeof value !== "string") return undefined;
  try {
    const parsed = JSON.parse(value) as Partial<NormalizedToolResponse>;
    return typeof parsed?.ok === "boolean"
      ? (parsed as NormalizedToolResponse)
      : undefined;
  } catch {
    return undefined;
  }
}

/** Read the canonical result contract from either envelope or data metadata. */
export function resultEnvelopeFromToolResult(
  content: unknown,
  messageId?: string,
): ResultEnvelope | undefined {
  const response = toolResponse(content);
  if (!response?.ok) return undefined;
  const data = response.data;
  const dataRecord = data && typeof data === "object" ? data as Record<string, unknown> : {};
  const nested = dataRecord.presentation && typeof dataRecord.presentation === "object"
    ? dataRecord.presentation as Record<string, unknown>
    : undefined;
  const source = response.presentation ?? (response.resultKind ? response : undefined) ?? nested;
  // Approval drafts are projected by the HITL interrupt card. Older persisted
  // messages may still contain a synthesized resultKind, so suppress that
  // legacy result before it can render as an empty generic result panel.
  if (
    source &&
    typeof source === "object" &&
    (source as Record<string, unknown>).cardType === "party_file_approval"
  ) {
    return undefined;
  }
  const rawKind = source && typeof source === "object"
    ? (source as Record<string, unknown>).resultKind
    : undefined;
  if (typeof rawKind !== "string" || !rawKind.trim()) return undefined;
  const presentation: ResultPresentation = {
    resultKind: isResultKind(rawKind) ? rawKind : "rich_text",
    sourceResultId: typeof (source as Record<string, unknown>).sourceResultId === "string"
      ? String((source as Record<string, unknown>).sourceResultId)
      : typeof response.sourceResultId === "string"
        ? response.sourceResultId
        : typeof dataRecord.sourceResultId === "string"
          ? dataRecord.sourceResultId
          : undefined,
    resultGroupId: typeof (source as Record<string, unknown>).resultGroupId === "string"
      ? String((source as Record<string, unknown>).resultGroupId)
      : typeof response.resultGroupId === "string" ? response.resultGroupId : undefined,
    title: typeof (source as Record<string, unknown>).title === "string" ? String((source as Record<string, unknown>).title) : undefined,
    summary: typeof (source as Record<string, unknown>).summary === "string"
      ? String((source as Record<string, unknown>).summary)
      : undefined,
    headline: typeof (source as Record<string, unknown>).headline === "string"
      ? String((source as Record<string, unknown>).headline)
      : typeof (source as Record<string, unknown>).summary === "object" && (source as Record<string, unknown>).summary !== null && typeof ((source as Record<string, unknown>).summary as Record<string, unknown>).headline === "string"
        ? String(((source as Record<string, unknown>).summary as Record<string, unknown>).headline)
        : undefined,
    displayPolicy: (source as Record<string, unknown>).displayPolicy as ResultPresentation["displayPolicy"] | undefined,
    primary: (source as Record<string, unknown>).primaryResult === true || response.primaryResult === true,
  };
  return {
    presentation,
    data,
    sourceResultId: presentation.sourceResultId,
    resultGroupId: presentation.resultGroupId,
    messageId,
  };
}

/**
 * Convert one tool result into the stable UI block contract.
 * Tool names are only a compatibility fallback for older Python tools. New
 * tools should set data.presentation explicitly.
 */
export function agentBlockFromToolResult(
  toolName: string | null | undefined,
  content: unknown,
  messageId?: string,
): AgentBlock | undefined {
  const response = toolResponse(content);
  if (!response) return undefined;
  if (!response.ok) {
    return {
      kind: "error",
      error: {
        code: String(response.error?.code ?? "UNKNOWN") as AgentErrorCode,
        message: String(response.error?.message ?? "工具执行失败"),
        retryable: false,
      },
    };
  }

  const result = resultEnvelopeFromToolResult(content, messageId);
  if (result) return { kind: "result", result };

  const presentation = response.presentation;
  const cardType = presentation?.cardType;
  if (presentation?.blockType === "card" || cardType) {
    if (cardType === "approval_request" || cardType === "approval_withdraw") {
      const record = response.data && typeof response.data === "object" ? response.data as Record<string, unknown> : {};
      const draft = record.draft && typeof record.draft === "object" ? record.draft as Record<string, unknown> : undefined;
      const withdrawal = cardType === "approval_withdraw";
      const fields: ApprovalField[] = withdrawal
        ? [stringField("操作", "撤回审批流程"), stringField("原因", draft?.reason)]
        : [stringField("类型", draft?.requestType === "leave" ? "请假" : draft?.requestType === "trip" ? "出差" : draft?.requestType), stringField("时间", [draft?.startTime, draft?.endTime].filter(Boolean).join(" - ")), stringField("原因", draft?.reason), stringField("审批链", (draft?.preview as Record<string, unknown> | undefined)?.normalizedSummary)];
      return {
        kind: "card",
        card: { type: "approval", payload: {
          approvalId: String(record.approvalId ?? ""), draftId: String(record.draftId ?? ""), action: withdrawal ? "confirm_approval_withdraw_action" : "confirm_approval_request_action", status: "PENDING", fields, allowedActions: ["approve", "reject"], cardType, title: withdrawal ? "确认撤回审批流程" : "确认发起审批", approveLabel: withdrawal ? "确认撤回" : "确认提交", rejectLabel: "取消操作", expiresAt: record.expiresAt == null ? undefined : String(record.expiresAt), draft,
        } },
      };
    }
    const approvalWorkflow = approvalWorkflowPayloadFromData(cardType, response.data);
    if (approvalWorkflow) {
      return { kind: "card", card: { type: "approval_workflow", payload: approvalWorkflow } };
    }
    if (cardType === "calendar") {
      const payload = calendarPayloadFromData(response.data);
      if (payload) return { kind: "card", card: { type: "calendar", payload } };
    }
    if (cardType === "todo") {
      const payload = todoPayloadFromData(response.data);
      if (payload) return { kind: "card", card: { type: "todo", payload } };
    }
    if (cardType === "approval_inbox") {
      const payload = approvalInboxPayloadFromData(response.data);
      if (payload) return { kind: "card", card: { type: "approval_inbox", payload } };
    }
    if (cardType === "approval_batch_preview" || cardType === "approval_batch_result") {
      const payload = approvalBatchPayloadFromData(response.data);
      return payload ? { kind: "card", card: { type: cardType, payload } } : undefined;
    }
    if (cardType === "approval_insights") {
      const payload = approvalInsightPayloadFromData(response.data);
      if (payload) return { kind: "card", card: { type: "approval_insights", payload } };
    }
    if (cardType === "approval_applications" || cardType === "approval_application" || cardType === "approval_history") {
      const payload = approvalWorkflowPayloadFromData(cardType, response.data);
      if (payload) return { kind: "card", card: { type: "approval_workflow", payload } };
    }
    if (cardType === "business_report") {
      const payload = response.data && typeof response.data === "object" ? response.data as BusinessReportPayload : undefined;
      if (payload) return { kind: "card", card: { type: "business_report", payload } };
    }
    if (cardType === "party_file") {
      const payload = partyFilePayloadFromData(response.data);
      if (payload) {
        return { kind: "card", card: { type: "party_file", payload } };
      }
    }
    if (cardType === "party_file_knowledge") {
      const payload = partyFileKnowledgePayloadFromData(response.data);
      if (payload) return { kind: "card", card: { type: "party_file_knowledge", payload } };
    }
    if (cardType === "party_file_compare") {
      const payload = partyFileComparePayloadFromData(response.data);
      if (payload) return { kind: "card", card: { type: "party_file_compare", payload } };
    }
    if (cardType === "party_file_compliance") {
      const payload = partyFileCompliancePayloadFromData(response.data);
      if (payload) return { kind: "card", card: { type: "party_file_compliance", payload } };
    }
  }

  // Backward compatibility for existing tools until all Python handlers emit
  // the presentation metadata above.
  if (toolName === "get_my_calendar") {
    const payload = calendarPayloadFromData(response.data);
    if (payload) return { kind: "card", card: { type: "calendar", payload } };
  }
  if (toolName === "list_my_pending_approvals") {
    const payload = todoPayloadFromData(response.data);
    if (payload) return { kind: "card", card: { type: "todo", payload } };
  }
  if (toolName === "search_party_files") {
    const payload = partyFilePayloadFromData(response.data);
    if (payload) return { kind: "card", card: { type: "party_file", payload } };
  }
  if (toolName === "search_party_knowledge" || toolName === "run_party_file_understanding") {
    const payload = partyFileKnowledgePayloadFromData(response.data);
    if (payload) return { kind: "card", card: { type: "party_file_knowledge", payload } };
  }
  if (toolName === "run_party_file_compare") {
    const payload = partyFileComparePayloadFromData(response.data);
    if (payload) return { kind: "card", card: { type: "party_file_compare", payload } };
  }
  if (toolName === "check_approval_against_party_file") {
    const payload = partyFileCompliancePayloadFromData(response.data);
    if (payload) return { kind: "card", card: { type: "party_file_compliance", payload } };
  }
  return { kind: "narration", markdown: "" };
}
