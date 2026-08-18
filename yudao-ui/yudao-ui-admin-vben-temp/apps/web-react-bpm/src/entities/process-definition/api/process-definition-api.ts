import { http } from '@/shared/api/http';

export interface ProcessDefinition {
  category?: string;
  categoryName?: string;
  description?: string;
  formCustomCreatePath?: string;
  formType?: number;
  icon?: string;
  id: string;
  key?: string;
  name: string;
  sort?: number;
}

export function getProcessDefinitionList(params?: Record<string, unknown>) {
  return http.get<ProcessDefinition[]>('/bpm/process-definition/list', { params });
}

export function getProcessDefinition(id?: string, key?: string) {
  return http.get<ProcessDefinition>('/bpm/process-definition/get', {
    params: { id, key },
  });
}
