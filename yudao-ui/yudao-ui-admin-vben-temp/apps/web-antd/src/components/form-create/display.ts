import { formatDate, formatDateTime } from '@vben/utils';
import { getDictLabel } from '@vben/hooks';

export interface FlowFormDisplayOption {
  id?: number | string;
  name?: string;
  nickname?: string;
}

export interface FlowFormDisplayContext {
  depts?: FlowFormDisplayOption[];
  users?: FlowFormDisplayOption[];
}

function parseSerializedValue(value: unknown): unknown {
  if (typeof value !== 'string') {
    return value;
  }
  const trimmed = value.trim();
  if (!trimmed || !['[', '{'].includes(trimmed[0] || '')) {
    return value;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function getRuleOptions(rule: any) {
  const options =
    rule?.options || rule?.props?.options || rule?.props?.fieldProps?.options;
  return Array.isArray(options) ? options : [];
}

function getOptionLabel(rule: any, value: unknown) {
  const matched = getRuleOptions(rule).find(
    (option: any) => String(option?.value) === String(value),
  );
  return matched?.label ?? matched?.name;
}

function getDictOptionLabel(rule: any, value: unknown) {
  const dictType = String(rule?.props?.dictType || rule?.dictType || '').trim();
  return dictType ? getDictLabel(dictType, value) : '';
}

export function isMillisecondTimestamp(value: unknown) {
  return /^\d{12,}$/.test(String(value));
}

function normalizeDateValue(value: unknown) {
  return isMillisecondTimestamp(value) ? new Date(Number(value)) : (value as any);
}

export function formatFlowFormDate(value: unknown) {
  return value ? formatDate(normalizeDateValue(value)) : '';
}

export function formatFlowFormDateTime(value: unknown) {
  return value ? formatDateTime(normalizeDateValue(value)) : '';
}

function findUserName(value: unknown, context: FlowFormDisplayContext) {
  return context.users?.find((item) => String(item.id) === String(value))
    ?.nickname;
}

function findDeptName(value: unknown, context: FlowFormDisplayContext) {
  return context.depts?.find((item) => String(item.id) === String(value))
    ?.name;
}

/**
 * Flowable stores form values in their raw form so process conditions remain
 * stable. This adapter is only for read-only views and resolves IDs/timestamps
 * into values a user can read.
 */
export function formatFlowFormValue(
  rule: any,
  value: unknown,
  context: FlowFormDisplayContext = {},
): string {
  const parsed = parseSerializedValue(value);
  if (Array.isArray(parsed)) {
    return parsed
      .map((item) => formatFlowFormValue(rule, item, context))
      .filter(Boolean)
      .join('、');
  }
  if (parsed && typeof parsed === 'object') {
    const item = parsed as Record<string, any>;
    return String(item.label || item.name || item.nickname || item.value || '');
  }
  if (parsed === true && String(rule?.type).toLowerCase().includes('switch')) {
    return '是';
  }
  if (parsed === false && String(rule?.type).toLowerCase().includes('switch')) {
    return '否';
  }
  const optionLabel = getOptionLabel(rule, parsed);
  if (optionLabel !== undefined) {
    return String(optionLabel);
  }
  const dictOptionLabel = getDictOptionLabel(rule, parsed);
  if (dictOptionLabel) {
    return dictOptionLabel;
  }
  const ruleType = String(rule?.type || '').toLowerCase();
  if (ruleType === 'userselect') {
    return findUserName(parsed, context) || String(parsed ?? '');
  }
  if (ruleType === 'deptselect') {
    return findDeptName(parsed, context) || String(parsed ?? '');
  }
  if (ruleType.includes('date') || ruleType.includes('time')) {
    return formatFlowFormDateTime(parsed);
  }
  return parsed === undefined || parsed === null ? '' : String(parsed);
}
