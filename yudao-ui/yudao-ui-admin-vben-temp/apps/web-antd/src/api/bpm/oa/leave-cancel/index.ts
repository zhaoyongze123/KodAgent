import type { PageParam } from '@vben/request';

import {
  createOARecord,
  getOARecord,
  getOARecordPage,
  type BpmOACommonApi,
} from '../common';

export namespace BpmOALeaveCancelApi {
  export type LeaveCancel = BpmOACommonApi.OARecord;
}

export async function createLeaveCancel(data: BpmOALeaveCancelApi.LeaveCancel) {
  return createOARecord('leaveCancel', data);
}

export async function getLeaveCancel(id: number) {
  return getOARecord('leaveCancel', id);
}

export async function getLeaveCancelPage(params: PageParam) {
  return getOARecordPage('leaveCancel', params);
}
