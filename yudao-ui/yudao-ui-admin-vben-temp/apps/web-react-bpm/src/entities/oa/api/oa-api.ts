import { http, type PageParams, type PageResult } from '@/shared/api/http';

export type OAModuleKey =
  | 'attendance'
  | 'document'
  | 'expense'
  | 'leave'
  | 'overtime'
  | 'project'
  | 'seal'
  | 'staffing'
  | 'trip';

export function createOARecord(moduleKey: OAModuleKey, data: Record<string, unknown>) {
  return http.post<number>(`/bpm/oa/${moduleKey}/create`, data);
}

export function getOARecord(moduleKey: OAModuleKey, id: number) {
  return http.get<Record<string, unknown>>(`/bpm/oa/${moduleKey}/get`, {
    params: { id },
  });
}

export function getOARecordPage(moduleKey: OAModuleKey, params: PageParams) {
  return http.get<PageResult<Record<string, unknown>>>(`/bpm/oa/${moduleKey}/page`, {
    params,
  });
}
