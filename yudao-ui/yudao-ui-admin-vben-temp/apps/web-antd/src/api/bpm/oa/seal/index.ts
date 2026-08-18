import type { PageParam } from '@vben/request';

import {
  createOARecord,
  getOARecord,
  getOARecordPage,
  type BpmOACommonApi,
} from '../common';

export namespace BpmOASealApi {
  export interface Seal extends BpmOACommonApi.OARecord {
    applicantName?: string;
    attachmentUrls?: string | string[];
    counterpartUnit?: string;
    createTime?: string;
    deptId?: number;
    deptName?: string;
    externalCarry?: boolean;
    fileCount?: number;
    fileName?: string;
    operatorName?: string;
    remark?: string;
  }
}

export async function createSeal(data: BpmOASealApi.Seal) {
  return createOARecord('seal', data);
}

export async function getSeal(id: number) {
  return getOARecord('seal', id);
}

export async function getSealPage(params: PageParam) {
  return getOARecordPage('seal', params);
}
