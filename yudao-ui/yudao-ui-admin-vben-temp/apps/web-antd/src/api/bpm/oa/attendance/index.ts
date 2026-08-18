import type { PageParam } from '@vben/request';

import {
  createOARecord,
  getOARecord,
  getOARecordPage,
  type BpmOACommonApi,
} from '../common';

export namespace BpmOAAttendanceApi {
  export type Attendance = BpmOACommonApi.OARecord;
}

export async function createAttendance(data: BpmOAAttendanceApi.Attendance) {
  return createOARecord('attendance', data);
}

export async function getAttendance(id: number) {
  return getOARecord('attendance', id);
}

export async function getAttendancePage(params: PageParam) {
  return getOARecordPage('attendance', params);
}
