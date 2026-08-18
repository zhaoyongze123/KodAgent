import type { PageParam } from '@vben/request';

import {
  createOARecord,
  getOARecord,
  getOARecordPage,
  type BpmOACommonApi,
} from '../common';

export namespace BpmOAExpenseApi {
  export type Expense = BpmOACommonApi.OARecord;
}

export async function createExpense(data: BpmOAExpenseApi.Expense) {
  return createOARecord('expense', data);
}

export async function getExpense(id: number) {
  return getOARecord('expense', id);
}

export async function getExpensePage(params: PageParam) {
  return getOARecordPage('expense', params);
}
