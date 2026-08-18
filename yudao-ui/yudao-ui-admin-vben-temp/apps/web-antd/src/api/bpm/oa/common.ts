import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export type OAModuleApiKey =
  | 'attendance'
  | 'document'
  | 'expense'
  | 'leaveCancel'
  | 'overtime'
  | 'outing'
  | 'project'
  | 'seal'
  | 'staffing'
  | 'trip';

export namespace BpmOACommonApi {
  export interface OARecord {
    id?: number;
    [key: string]: any;
    status?: number;
    type: number;
    reason: string;
    processInstanceId?: string;
    startTime: number | string;
    endTime: number | string;
    createTime?: Date | string;
    startUserSelectAssignees?: Record<string, number[]>;
  }
}

export async function createOARecord(
  moduleKey: OAModuleApiKey,
  data: BpmOACommonApi.OARecord,
) {
  return requestClient.post(`/bpm/oa/${getOAApiPath(moduleKey)}/create`, data);
}

export async function getOARecord(
  moduleKey: OAModuleApiKey,
  id: number,
) {
  return requestClient.get<BpmOACommonApi.OARecord>(
    `/bpm/oa/${getOAApiPath(moduleKey)}/get?id=${id}`,
  );
}

export async function getOARecordPage(
  moduleKey: OAModuleApiKey,
  params: PageParam,
) {
  return requestClient.get<PageResult<BpmOACommonApi.OARecord>>(
    `/bpm/oa/${getOAApiPath(moduleKey)}/page`,
    { params },
  );
}

function getOAApiPath(moduleKey: OAModuleApiKey) {
  switch (moduleKey) {
    case 'leaveCancel':
      return 'leave-cancel';
    default:
      return moduleKey;
  }
}
