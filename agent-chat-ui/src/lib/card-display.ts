/**
 * Agent 卡片的面向用户字段展示与脱敏规则。
 *
 * 业务接口必须保留数字 ID 与枚举编码，供权限、持久化和写操作使用；卡片则是
 * 展示边界，不能把这些传输字段原样暴露给用户。所有映射集中在本文件，避免每个
 * 组件各自实现兜底逻辑后出现展示口径不一致。
 */

export type CardDisplayContext = {
  cardType?: string;
  domain?: "party_file" | "approval" | "meeting" | "schedule" | "generic";
};

const OPERATION_LABELS: Record<string, string> = {
  CREATE: "创建",
  UPDATE: "修改",
  CANCEL: "取消",
  DELETE: "删除",
  APPROVE: "通过",
  REJECT: "驳回",
  WITHDRAW: "撤回",
};

const APPROVAL_STATUS_LABELS: Record<string, string> = {
  PENDING: "待确认",
  APPROVED: "已确认",
  REJECTED: "已取消",
  EXPIRED: "已过期",
  SUCCESS: "已完成",
  FAILED: "处理失败",
  READY: "待执行",
  COMPLETED: "已完成",
  CANCELLED: "已取消",
  SUBMITTING: "提交中",
  WAITING_APPROVAL: "等待确认",
};

const PARTY_FILE_STATUS_LABELS: Record<string, string> = {
  "0": "已发布",
  "1": "草稿",
  PUBLISHED: "已发布",
  DRAFT: "草稿",
  READY: "可用",
  NO_MATCH: "没有匹配结果",
  PASS: "符合要求",
  OK: "符合要求",
  WARN: "需补充确认",
  BLOCK: "阻断",
  MISSING: "缺失",
};

const STORAGE_LABELS: Record<string, string> = {
  "1": "本地存储",
  "2": "可道云存储",
  LOCAL: "本地存储",
  KOD: "可道云存储",
};

const TARGET_TYPE_LABELS: Record<string, string> = {
  "1": "全员",
  "2": "指定用户",
  "3": "指定部门",
  "4": "指定角色",
  ALL: "全员",
  USER: "指定用户",
  DEPT: "指定部门",
  ROLE: "指定角色",
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  MEETING_BOOKING: "会议预约",
  MEETING: "会议预约",
  PERSONAL_SCHEDULE: "个人日程",
  SCHEDULE: "个人日程",
  PARTY_FILE: "党务文件",
  APPROVAL: "审批事项",
};

const DOCUMENT_TYPE_LABELS: Record<string, string> = {
  NOTICE: "通知公告",
  POLICY: "制度规范",
  ORGANIZATION: "组织建设",
  REPORT: "工作报告",
};

const VERDICT_LABELS: Record<string, string> = {
  PASS: "通过",
  OK: "通过",
  WARN: "需补充确认",
  BLOCK: "阻断",
  MISSING: "缺失",
  PRESENT: "已提供",
};

function normalized(value: unknown): string {
  return String(value ?? "").trim();
}

function normalizedKey(label: unknown): string {
  return normalized(label).toLowerCase().replace(/[\s_-]/g, "");
}

function code(value: unknown): string {
  return normalized(value).toUpperCase();
}

function isNumericCode(value: unknown): boolean {
  return /^-?\d+(?:\.\d+)?$/.test(normalized(value));
}

function isNumericList(value: unknown): boolean {
  const raw = normalized(value);
  return raw.length > 0 && raw.split(/[,，、\s]+/).filter(Boolean).every((item) => isNumericCode(item));
}

/** 返回业务操作的稳定中文标签，不泄露内部编码。 */
export function displayOperation(value: unknown): string {
  const raw = normalized(value);
  return OPERATION_LABELS[code(raw)] ?? (isNumericCode(raw) ? "业务操作" : raw);
}

/** 返回审批、工作流或党务文件卡片的面向用户状态。 */
export function displayStatus(value: unknown, context?: CardDisplayContext): string {
  const raw = normalized(value);
  const key = code(raw);
  if (context?.domain === "party_file" || context?.cardType?.startsWith("party_file")) {
    return PARTY_FILE_STATUS_LABELS[key] ?? (isNumericCode(raw) ? "状态待确认" : raw);
  }
  return APPROVAL_STATUS_LABELS[key] ?? (isNumericCode(raw) ? "状态待确认" : raw);
}

export function displayVerdict(value: unknown): string {
  const raw = normalized(value);
  return VERDICT_LABELS[code(raw)] ?? (isNumericCode(raw) ? "校验结果待确认" : raw || "需补充确认");
}

export function displayStorageType(value: unknown): string {
  const raw = normalized(value);
  return STORAGE_LABELS[code(raw)] ?? (isNumericCode(raw) ? "存储方式待确认" : raw);
}

export function displayTargetType(value: unknown): string {
  const raw = normalized(value);
  return TARGET_TYPE_LABELS[code(raw)] ?? (isNumericCode(raw) ? "分发对象待确认" : raw);
}

/** 返回日历和报表中来源/类型编码的中文标签。 */
export function displaySourceType(value: unknown): string {
  const raw = normalized(value);
  const key = code(raw);
  return SOURCE_TYPE_LABELS[key] ?? (isNumericCode(raw) ? "来源类型待确认" : raw);
}

/** 返回党务文件类型编码的中文标签。 */
export function displayDocumentType(value: unknown): string {
  const raw = normalized(value);
  const key = code(raw);
  return DOCUMENT_TYPE_LABELS[key] ?? (isNumericCode(raw) ? "文件类型待确认" : raw);
}

/**
 * 展示分组或维度字段的值。
 *
 * 维度通常由部门、分类或会议室的数字 ID 支撑，必须和表单字段一样经过展示边界，
 * 不能直接插入卡片。
 */
export function displayDimensionValue(value: unknown, dimension = "分组"): string {
  const raw = normalized(value);
  if (!raw) return `${dimension}待确认`;
  const key = normalizedKey(dimension);
  if (key.includes("来源") || key.includes("source")) {
    return displaySourceType(raw);
  }
  if (key.includes("分类") || key.includes("category")) {
    return isNumericCode(raw) ? "分类名称待确认" : raw;
  }
  if (key.includes("部门") || key.includes("department")) {
    return isNumericCode(raw) ? "部门名称待确认" : raw;
  }
  if (key.includes("会议室") || key.includes("房间") || key.includes("room")) {
    return isNumericCode(raw) ? "会议室名称待确认" : raw;
  }
  if (key.includes("流程") || key.includes("process")) {
    return isNumericCode(raw) ? "审批流程名称待确认" : raw;
  }
  if (key.includes("状态") || key.includes("status")) {
    return displayStatus(raw);
  }
  if (key.includes("名称") || key.includes("name")) {
    return isNumericCode(raw) ? "名称待确认" : raw;
  }
  return isNumericCode(raw) ? `${dimension}待确认` : raw;
}

/**
 * 隐藏技术标识，同时保留用户可理解的业务说明。
 *
 * ID 仍保留在动作请求载荷中，但确认卡片故意不展示它们。
 */
function displayTechnicalValue(label: string): string | undefined {
  const key = normalizedKey(label);
  if (
    key === "id" ||
    key.endsWith("id") ||
    key.includes("uuid") ||
    key.includes("token") ||
    key.includes("流水号") ||
    key.includes("编号") ||
    key.includes("文件id") ||
    key.includes("任务id") ||
    key.includes("预约编号") ||
    key.includes("bookingid") ||
    key.includes("draftid") ||
    key.includes("approvalid") ||
    key.includes("流程实例") ||
    key.includes("processinstanceid")
  ) {
    return "已关联业务记录";
  }
  return undefined;
}

/**
 * 按字段语义格式化字段值。
 *
 * 金额、数量、时长等非枚举业务数字必须原样保留；只转换内部 ID、枚举和状态码。
 */
export function displayFieldValue(
  label: unknown,
  value: unknown,
  context?: CardDisplayContext,
): string {
  const fieldLabel = normalized(label);
  if (value == null || normalized(value) === "") return "未提供";

  const technical = displayTechnicalValue(fieldLabel);

  const key = normalizedKey(fieldLabel);
  // 分类 ID 是唯一例外：它可用于解析分类名称，未知数字分类在下方显示安全占位。
  // 其他技术性 *Id/code* 字段必须先隐藏，再进行宽泛语义匹配，避免把 targetId
  // 误判为 targetType。
  if (technical && !key.includes("categoryid")) return technical;
  if (key.includes("分类") || key.includes("category")) {
    return isNumericCode(value) ? "分类名称待确认" : String(value);
  }
  if (key.includes("来源") || key.includes("sourcetype")) return displaySourceType(value);
  if (key.includes("审批类型")) {
    return isNumericCode(value) ? "审批类型待确认" : String(value);
  }
  if (key.includes("文件类型") || key === "doctype" || key.includes("documenttype")) {
    return displayDocumentType(value);
  }
  if (key.includes("部门")) return displayDimensionValue(value, "部门名称");
  if (key.includes("会议室") || key.includes("房间")) return displayDimensionValue(value, "会议室名称");
  if (key.includes("参会人") || key.includes("用户") || key.includes("人员") || key.includes("发起人") || key.includes("申请人")) {
    return isNumericCode(value) || isNumericList(value) ? "人员信息待确认" : String(value);
  }
  if (key.includes("名称") || key.endsWith("name")) {
    return isNumericCode(value) ? "名称待确认" : String(value);
  }
  if (key === "地点" || key === "location") {
    return isNumericCode(value) ? "地点待确认" : String(value);
  }
  if (key.includes("存储") || key === "storagetype") return displayStorageType(value);
  if (key.includes("目标类型") || key.includes("分发类型") || key === "targettype") return displayTargetType(value);
  if (key.includes("操作") || key === "action" || key === "operation") return displayOperation(value);
  if (key.includes("状态") || key === "status" || key === "state") return displayStatus(value, context);
  if (key === "type" || key.endsWith("type")) return displayDimensionValue(value, "类型");
  if (key.includes("分发") || key.includes("distribution") || key === "targettype" || key.endsWith("targettype")) return displayTargetType(value);
  if (key.includes("结论") || key.includes("校验结果") || key === "verdict") return displayVerdict(value);
  if (key === "code" || key.endsWith("code")) return isNumericCode(value) ? "编码待确认" : String(value);
  if (technical) return technical;

  if (typeof value === "object") {
    return displayStructuredValue(value, context);
  }
  if (typeof value === "string" && /^[{[]/.test(value.trim())) {
    try {
      return displayStructuredValue(JSON.parse(value), context);
    } catch {
      // 以括号开头的普通文本仍可能是合法业务值；不是 JSON 时保持原样。
    }
  }
  return String(value);
}

/** 通用审批表单的嵌套值也要递归脱敏枚举和 ID 字段。 */
export function displayStructuredValue(value: unknown, context?: CardDisplayContext): string {
  const normalize = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(normalize);
    if (item && typeof item === "object") {
      return Object.fromEntries(
        Object.entries(item as Record<string, unknown>).map(([key, raw]) => [
          key,
          displayFieldValue(key, raw, context),
        ]),
      );
    }
    return item;
  };
  try {
    return JSON.stringify(normalize(value), null, 2);
  } catch {
    return "已提供";
  }
}

export function displayBatchStatus(value: unknown): string {
  return displayStatus(value, { domain: "approval", cardType: "approval_batch" });
}
