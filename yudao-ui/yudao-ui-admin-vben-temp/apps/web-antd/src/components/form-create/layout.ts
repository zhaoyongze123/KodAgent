export type FlowFormLayoutMode = 'custom' | 'one-column' | 'two-column';

const ONE_COLUMN_COL = {
  span: 24,
  xs: 24,
  sm: 24,
  md: 24,
  lg: 24,
  xl: 24,
};

const TWO_COLUMN_COL = {
  span: 12,
  xs: 24,
  sm: 24,
  md: 12,
  lg: 12,
  xl: 12,
};

function isWideField(rule: any) {
  const type = String(rule?.type || '').toLowerCase();
  const inputType = String(rule?.props?.type || '').toLowerCase();
  return (
    inputType === 'textarea' ||
    [
      'editor',
      'fc-editor',
      'fileupload',
      'iframe',
      'inputtextarea',
      'tableform',
      'textarea',
      'upload',
    ].includes(type)
  );
}

/**
 * 流程表单的布局只由表单配置决定：
 * - 单列 / 两列：使用 form-create 的全局 col 配置；
 * - 自定义：保留设计器中的 Row / Col 和字段自身 col，不再覆盖。
 */
export function getFlowFormLayoutMode(
  option?: Record<string, any>,
): FlowFormLayoutMode {
  const col = option?.col;
  if (!col) {
    return 'one-column';
  }
  if (col.span === 12 || col.md === 12 || col.lg === 12 || col.xl === 12) {
    return 'two-column';
  }
  if (col.span === 24 || col.md === 24 || col.lg === 24 || col.xl === 24) {
    return 'one-column';
  }
  return 'custom';
}

export function setFlowFormLayout(
  option: Record<string, any> = {},
  mode: FlowFormLayoutMode,
) {
  const nextOption = { ...option };
  if (mode === 'custom') {
    delete nextOption.col;
    return nextOption;
  }
  return {
    ...nextOption,
    col: mode === 'two-column' ? TWO_COLUMN_COL : ONE_COLUMN_COL,
    row: {
      ...(nextOption.row || {}),
      gutter: 16,
    },
  };
}

/**
 * 两列表单中，文本域、附件、富文本等本来就不适合被压缩成半列。
 * 仅在字段未自行配置 col 时补默认值，设计器保存的自定义栅格始终优先。
 */
export function normalizeFlowFormRulesForDisplay(
  rules: any[],
  mode: FlowFormLayoutMode,
) {
  if (mode !== 'two-column') {
    return rules;
  }
  return rules.map((rule) => {
    if (rule?.col || !isWideField(rule)) {
      return rule;
    }
    return {
      ...rule,
      col: ONE_COLUMN_COL,
    };
  });
}
