import { http, type PageResult } from '@/shared/api/http';

export interface SimpleUser {
  avatar?: string;
  deptId?: number;
  deptName?: string;
  email?: string;
  id: number;
  mobile?: string;
  nickname: string;
  postIds?: number[];
  sex?: number;
  status?: number;
  username?: string;
}

export interface UserProfile {
  avatar?: string;
  createTime?: string;
  dept?: {
    id?: number;
    name?: string;
  };
  email?: string;
  id: number;
  loginDate?: string;
  loginIp?: string;
  mobile?: string;
  nickname: string;
  posts?: Array<{ id: number; name: string }>;
  roles?: Array<{ id: number; name: string }>;
  username: string;
}

export function getSimpleUserList() {
  return http.get<SimpleUser[]>('/system/user/simple-list');
}

export function getUserProfile() {
  return http.get<UserProfile>('/system/user/profile/get');
}

export function getUserPage() {
  return http.get<PageResult<SimpleUser>>('/system/user/page', {
    params: { pageNo: 1, pageSize: 100 },
  });
}
