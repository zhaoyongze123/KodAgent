import { http } from '@/shared/api/http';

export interface SimpleDept {
  children?: SimpleDept[];
  id: number;
  leaderUserId?: number;
  name: string;
  parentId?: number;
  status?: number;
}

export function getSimpleDeptList() {
  return http.get<SimpleDept[]>('/system/dept/simple-list');
}
