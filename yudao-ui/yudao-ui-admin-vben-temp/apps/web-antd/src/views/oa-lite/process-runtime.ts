export interface RuntimeAssignee {
  nickname?: string;
}

export interface RuntimeTask {
  assigneeUser?: RuntimeAssignee;
  name?: string;
}

export interface RuntimeProcessLike {
  status?: number;
  tasks?: RuntimeTask[];
}

export interface SelectFieldOption {
  label: string;
  value: number | string;
}

const TERMINAL_PROCESS_STATUSES = new Set([2, 3, 4]);

export function getCurrentStageLabel(
  process?: null | RuntimeProcessLike,
): string {
  const assignees = (process?.tasks || [])
    .map((task) => task.assigneeUser?.nickname?.trim())
    .filter(isNonEmptyString);
  const uniqueAssignees = [...new Set(assignees)];
  if (uniqueAssignees.length > 0) {
    return uniqueAssignees.join('、');
  }
  if ((process?.tasks || []).length > 0 && process?.status === 1) {
    return '待分配';
  }
  switch (process?.status) {
    case 1: {
      return '处理中';
    }
    case 2: {
      return '已通过';
    }
    case 3: {
      return '已驳回';
    }
    case 4: {
      return '已取消';
    }
    default: {
      return '-';
    }
  }
}

export function getProcessEndTime(status?: number, endTime?: string) {
  return status !== undefined && TERMINAL_PROCESS_STATUSES.has(status)
    ? endTime
    : undefined;
}

export function getSelectFieldOptions(fields?: unknown[]): SelectFieldOption[] {
  if (!Array.isArray(fields)) {
    return [];
  }
  for (const rawField of fields) {
    const field: Record<string, any> | undefined =
      typeof rawField === 'string'
        ? safelyParseJson<Record<string, any>>(rawField)
        : (rawField && typeof rawField === 'object'
            ? (rawField as Record<string, any>)
            : undefined);
    if (!field || field.field !== 'type' || !Array.isArray(field.options)) {
      continue;
    }
    return field.options.filter(
      (option: any): option is SelectFieldOption =>
        typeof option?.label === 'string' &&
        ['number', 'string'].includes(typeof option.value),
    );
  }
  return [];
}

function isNonEmptyString(value: string | undefined): value is string {
  return typeof value === 'string' && value.length > 0;
}

function safelyParseJson<T>(value: string): T | undefined {
  try {
    return JSON.parse(value) as T;
  } catch {
    return undefined;
  }
}
