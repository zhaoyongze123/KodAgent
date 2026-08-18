import { http } from '@/shared/api/http';

export interface Category {
  code: string;
  id: number;
  name: string;
  sort?: number;
  status?: number;
}

export function getCategorySimpleList() {
  return http.get<Category[]>('/bpm/category/simple-list');
}
