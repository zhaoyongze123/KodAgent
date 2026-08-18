import type { PageParam } from '@vben/request';

import {
  createOARecord,
  getOARecord,
  getOARecordPage,
  type BpmOACommonApi,
} from '../common';

export namespace BpmOAOvertimeApi {
  export type Overtime = BpmOACommonApi.OARecord;
}

export async function createOvertime(data: BpmOAOvertimeApi.Overtime) {
  return createOARecord('overtime', data);
}

export async function getOvertime(id: number) {
  return getOARecord('overtime', id);
}

export async function getOvertimePage(params: PageParam) {
  return getOARecordPage('overtime', params);
}
