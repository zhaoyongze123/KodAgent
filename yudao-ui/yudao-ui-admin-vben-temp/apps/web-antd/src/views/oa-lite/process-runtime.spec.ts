import { describe, expect, it } from 'vitest';

import {
  getCurrentStageLabel,
  getProcessEndTime,
  getSelectFieldOptions,
} from './process-runtime';

describe('OA process runtime presentation', () => {
  it('uses active assignee names instead of the configured node name', () => {
    expect(
      getCurrentStageLabel({
        status: 1,
        tasks: [
          {
            name: '严己自选审批人',
            assigneeUser: { nickname: '张龄' },
          },
        ],
      }),
    ).toBe('张龄');
  });

  it('does not expose an end time while the process is running', () => {
    expect(getProcessEndTime(1, '2026-08-17 10:00:00')).toBeUndefined();
    expect(getProcessEndTime(2, '2026-08-17 10:00:00')).toBe(
      '2026-08-17 10:00:00',
    );
  });

  it('shows the real terminal result when a process has no active task', () => {
    expect(getCurrentStageLabel({ status: 2, tasks: [] })).toBe('已通过');
    expect(getCurrentStageLabel({ status: 3, tasks: [] })).toBe('已驳回');
    expect(getCurrentStageLabel({ status: 4, tasks: [] })).toBe('已取消');
  });

  it('extracts Chinese options from the selected process form', () => {
    expect(
      getSelectFieldOptions([
        JSON.stringify({
          field: 'type',
          type: 'select',
          options: [
            { label: '事假', value: 1 },
            { label: '病假', value: 2 },
          ],
        }),
      ]),
    ).toEqual([
      { label: '事假', value: 1 },
      { label: '病假', value: 2 },
    ]);
  });

  it('does not expose boolean switches as process type filters', () => {
    expect(
      getSelectFieldOptions([
        {
          field: 'type',
          options: [
            { label: '差旅费', value: 1 },
            { label: '是否紧急', value: true },
          ],
        },
      ]),
    ).toEqual([{ label: '差旅费', value: 1 }]);
  });
});
