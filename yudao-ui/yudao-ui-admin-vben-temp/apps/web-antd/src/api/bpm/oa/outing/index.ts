import type { PageParam } from '@vben/request';

import {
  createOARecord,
  getOARecord,
  getOARecordPage,
  type BpmOACommonApi,
} from '../common';

export namespace BpmOAOutingApi {
  export type Outing = BpmOACommonApi.OARecord;
}

export async function createOuting(data: BpmOAOutingApi.Outing) {
  return createOARecord('outing', data);
}

export async function getOuting(id: number) {
  return getOARecord('outing', id);
}

export async function getOutingPage(params: PageParam) {
  return getOARecordPage('outing', params);
}
