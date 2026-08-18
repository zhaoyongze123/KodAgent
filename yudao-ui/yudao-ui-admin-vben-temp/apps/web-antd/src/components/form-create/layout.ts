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

function isTimeRangePair(startRule: any, endRule: any) {
  const startField = String(startRule?.field || '');
  const endField = String(endRule?.field || '');
  const startTitle = String(startRule?.title || '');
  const endTitle = String(endRule?.title || '');
  return (
    (/^(start|begin)(time|date)?$/i.test(startField) &&
      /^(end|finish)(time|date)?$/i.test(endField)) ||
    (startTitle.includes('开始') && endTitle.includes('结束'))
  );
}

function getRuleColumnSpan(rule: any) {
  const col = rule?.col;
  if (!col) {
    return 12;
  }
  const span = Number(col.span ?? col.md ?? col.lg ?? col.xl ?? 12);
  return span > 0 && span <= 24 ? span : 12;
}

function getOccupiedColumns(rules: any[], endExclusive: number) {
  let occupied = 0;
  for (let index = 0; index < endExclusive; index += 1) {
    const span = getRuleColumnSpan(rules[index]);
    if (occupied + span > 24) {
      occupied = 0;
    }
    occupied += span;
    if (occupied === 24) {
      occupied = 0;
    }
  }
  return occupied;
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
      ...nextOption.row,
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

  const normalizedRules = rules.map((rule) => {
    if (rule?.col || !isWideField(rule)) {
      return rule;
    }
    return {
      ...rule,
      col: ONE_COLUMN_COL,
    };
  });

  for (let index = 0; index < normalizedRules.length - 1; index += 1) {
    const startRule = normalizedRules[index];
    const endRule = normalizedRules[index + 1];
    if (!isTimeRangePair(startRule, endRule)) {
      continue;
    }

    // The stored form usually defaults every short field to half width. When a
    // preceding single field occupies a half row, start/end would otherwise split.
    const previousRule = normalizedRules[index - 1];
    if (
      getOccupiedColumns(normalizedRules, index) === 12 &&
      previousRule &&
      !previousRule.col &&
      !isWideField(previousRule)
    ) {
      normalizedRules[index - 1] = {
        ...previousRule,
        col: ONE_COLUMN_COL,
      };
    }
    if (!startRule.col) {
      normalizedRules[index] = {
        ...startRule,
        col: TWO_COLUMN_COL,
      };
    }
    if (!endRule.col) {
      normalizedRules[index + 1] = {
        ...endRule,
        col: TWO_COLUMN_COL,
      };
    }
  }

  return normalizedRules;
}
