import { http, type PageParams, type PageResult } from '@/shared/api/http';

export interface Task {
  assigneeUser?: {
    avatar?: string;
    deptName?: string;
    id: number;
    nickname: string;
  };
  buttonsSetting?: Record<string, unknown>;
  createTime?: string;
  durationInMillis?: number;
  endTime?: string;
  formFields?: unknown[];
  formId?: number;
  formName?: string;
  formVariables?: Record<string, unknown>;
  id: string;
  name: string;
  nodeType?: number;
  ownerUser?: {
    avatar?: string;
    deptName?: string;
    id: number;
    nickname: string;
  };
  parentTaskId?: string;
  processInstance?: {
    businessKey?: string;
    category?: string;
    categoryName?: string;
    createTime?: string;
    id: number;
    name: string;
    result?: number;
    startUser?: {
      deptName?: string;
      id: number;
      nickname: string;
    };
    status?: number;
    summary?: Array<{ key: string; value: string }>;
  };
  processInstanceId?: string;
  reason?: string;
  reasonRequire?: boolean;
  signEnable?: boolean;
  status?: number;
  taskDefinitionKey?: string;
}

export interface ReturnNode {
  name: string;
  taskDefinitionKey: string;
}

export interface ChildTask {
  assigneeUser?: {
    avatar?: string;
    deptName?: string;
    id: number;
    nickname: string;
  };
  id: string;
  name: string;
  ownerUser?: {
    avatar?: string;
    deptName?: string;
    id: number;
    nickname: string;
  };
  parentTaskId?: string;
}

export function getTodoTasks(params: PageParams) {
  return http.get<PageResult<Task>>('/bpm/task/todo-page', { params });
}

export function getDoneTasks(params: PageParams) {
  return http.get<PageResult<Task>>('/bpm/task/done-page', { params });
}

export function getManagerTasks(params: PageParams) {
  return http.get<PageResult<Task>>('/bpm/task/manager-page', { params });
}

export function approveTask(data: Record<string, unknown>) {
  return http.put<boolean>('/bpm/task/approve', data);
}

export function rejectTask(data: Record<string, unknown>) {
  return http.put<boolean>('/bpm/task/reject', data);
}

export function delegateTask(data: Record<string, unknown>) {
  return http.put<boolean>('/bpm/task/delegate', data);
}

export function transferTask(data: Record<string, unknown>) {
  return http.put<boolean>('/bpm/task/transfer', data);
}

export function signCreateTask(data: Record<string, unknown>) {
  return http.put<boolean>('/bpm/task/create-sign', data);
}

export function signDeleteTask(data: Record<string, unknown>) {
  return http.delete<boolean>('/bpm/task/delete-sign', { body: data });
}

export function returnTask(data: Record<string, unknown>) {
  return http.put<boolean>('/bpm/task/return', data);
}

export function copyTask(data: Record<string, unknown>) {
  return http.put<boolean>('/bpm/task/copy', data);
}

export function getReturnNodeList(taskId: string) {
  return http.get<ReturnNode[]>('/bpm/task/list-by-return', {
    params: { id: taskId },
  });
}

export function getChildrenTaskList(parentTaskId: string) {
  return http.get<ChildTask[]>('/bpm/task/list-by-parent-task-id', {
    params: { parentTaskId },
  });
}

export function withdrawTask(taskId: string) {
  return http.put<boolean>('/bpm/task/withdraw', undefined, {
    params: { taskId },
  });
}
