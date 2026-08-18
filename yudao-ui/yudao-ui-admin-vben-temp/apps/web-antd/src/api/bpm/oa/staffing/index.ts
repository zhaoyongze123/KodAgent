import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace BpmOAStaffingApi {
  export interface Staffing {
    id?: number;
    applicantName?: string;
    createTime?: string;
    deptId?: number;
    deptName?: string;
    expectedWorkPeriod: string;
    memberIds: number[] | string;
    memberNames?: string;
    processInstanceId?: string;
    projectName: string;
    reason: string;
    remark?: string;
    startUserSelectAssignees?: Record<string, number[]>;
    status?: number;
    targetUnit: string;
    transferTime: number | string;
  }
}

export async function createStaffing(data: BpmOAStaffingApi.Staffing) {
  return requestClient.post('/bpm/oa/staffing/create', data);
}

export async function getStaffing(id: number) {
  return requestClient.get<BpmOAStaffingApi.Staffing>(`/bpm/oa/staffing/get?id=${id}`);
}

export async function getStaffingPage(params: PageParam) {
  return requestClient.get<PageResult<BpmOAStaffingApi.Staffing>>('/bpm/oa/staffing/page', {
    params,
  });
}
