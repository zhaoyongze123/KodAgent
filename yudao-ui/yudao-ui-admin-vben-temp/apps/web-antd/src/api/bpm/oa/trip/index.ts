import type { PageParam } from '@vben/request';

import {
  createOARecord,
  getOARecord,
  getOARecordPage,
  type BpmOACommonApi,
} from '../common';

export namespace BpmOATripApi {
  export type Trip = BpmOACommonApi.OARecord;
}

export async function createTrip(data: BpmOATripApi.Trip) {
  return createOARecord('trip', data);
}

export async function getTrip(id: number) {
  return getOARecord('trip', id);
}

export async function getTripPage(params: PageParam) {
  return getOARecordPage('trip', params);
}
