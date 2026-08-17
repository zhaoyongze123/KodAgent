import { describe, expect, it } from 'vitest';

import { normalizeFlowFormRulesForDisplay } from './layout';

describe('normalizeFlowFormRulesForDisplay', () => {
  it('starts an adjacent start and end time pair on the same row', () => {
    const rules = normalizeFlowFormRulesForDisplay(
      [
        { field: 'type', type: 'select' },
        { field: 'startTime', title: '开始时间', type: 'datePicker' },
        { field: 'endTime', title: '结束时间', type: 'datePicker' },
      ],
      'two-column',
    );

    expect(rules[0]?.col?.span).toBe(24);
    expect(rules[1]?.col?.span).toBe(12);
    expect(rules[2]?.col?.span).toBe(12);
  });

  it('keeps text areas and attachments on a full row in two-column forms', () => {
    const rules = normalizeFlowFormRulesForDisplay(
      [
        { field: 'reason', props: { type: 'textarea' }, type: 'input' },
        { field: 'attachmentUrls', type: 'FileUpload' },
      ],
      'two-column',
    );

    expect(rules.map((rule) => rule.col?.span)).toEqual([24, 24]);
  });

  it('does not expand two complete preceding short fields before a time pair', () => {
    const rules = normalizeFlowFormRulesForDisplay(
      [
        { field: 'type', type: 'select' },
        { field: 'outingDate', type: 'datePicker' },
        { field: 'startTime', title: '开始时间', type: 'datePicker' },
        { field: 'endTime', title: '结束时间', type: 'datePicker' },
      ],
      'two-column',
    );

    expect(rules[0]?.col).toBeUndefined();
    expect(rules[1]?.col).toBeUndefined();
    expect(rules[2]?.col?.span).toBe(12);
    expect(rules[3]?.col?.span).toBe(12);
  });
});
