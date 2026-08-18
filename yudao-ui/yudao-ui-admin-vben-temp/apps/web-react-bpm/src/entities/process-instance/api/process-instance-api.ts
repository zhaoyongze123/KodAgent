import { http, type PageParams, type PageResult } from '@/shared/api/http';

export interface ProcessInstance {
  businessKey?: string;
  category?: string;
  categoryName?: string;
  createTime?: string;
  endTime?: string;
  formVariables?: Record<string, unknown>;
  id: number;
  name: string;
  processDefinition?: {
    formCustomCreatePath?: string;
    formCustomViewPath?: string;
    formType?: number;
    icon?: string;
    id: string;
    key?: string;
    modelType?: number;
    name?: string;
  };
  result?: number;
  startUser?: {
    deptName?: string;
    id: number;
    nickname: string;
  };
  status?: number;
  summary?: Array<{ key: string; value: string }>;
  tasks?: Array<{ id: number; name: string }>;
}

export interface ApprovalDetail {
  activityNodes: Array<{
    candidateUsers?: Array<{ id: number; nickname: string }>;
    endTime?: string;
    id: string;
    name: string;
    nodeType: number;
    startTime?: string;
    status: number;
    tasks: Array<{
      assigneeUser?: { id: number; nickname: string };
      id: number;
      reason?: string;
      signPicUrl?: string;
      status?: number;
    }>;
  }>;
  formFieldsPermission?: Record<string, string>;
  processDefinition: {
    formConf?: string;
    formCustomCreatePath?: string;
    formCustomViewPath?: string;
    formFields?: string[];
    formType?: number;
    icon?: string;
    id: string;
    key?: string;
    name?: string;
  };
  processInstance: ProcessInstance;
  status?: number;
  todoTask?: import('@/entities/task/api/task-api').Task;
}

export interface ApprovalNodeInfo {
  candidateStrategy?: number;
  candidateUsers?: Array<{ id: number; nickname: string }>;
  id: string;
  name: string;
  nodeType: number;
}

export interface ProcessInstanceCopy {
  activityId?: string;
  activityName?: string;
  createTime?: string;
  createUser?: {
    id: number;
    nickname: string;
  };
  id: number;
  processInstanceId?: string;
  processInstanceName?: string;
  processInstanceStartTime?: string;
  reason?: string;
  startUser?: {
    id: number;
    nickname: string;
  };
  summary?: Array<{ key: string; value: string }>;
  taskId?: string;
}

export function getMyProcessInstances(params: PageParams) {
  return http.get<PageResult<ProcessInstance>>('/bpm/process-instance/my-page', {
    params,
  });
}

export function getManagerProcessInstances(params: PageParams) {
  return http.get<PageResult<ProcessInstance>>(
    '/bpm/process-instance/manager-page',
    {
      params,
    },
  );
}

export function getProcessInstanceCopyPage(params: PageParams) {
  return http.get<PageResult<ProcessInstanceCopy>>('/bpm/process-instance/copy/page', {
    params,
  });
}

export function getApprovalDetail(params: Record<string, unknown>) {
  return http.get<ApprovalDetail>('/bpm/process-instance/get-approval-detail', {
    params,
  });
}

export function getNextApprovalNodes(params: Record<string, unknown>) {
  return http.get<ApprovalNodeInfo[]>(
    '/bpm/process-instance/get-next-approval-nodes',
    {
      params,
    },
  );
}

export function cancelByStartUser(id: number, reason: string) {
  return http.delete<boolean>('/bpm/process-instance/cancel-by-start-user', {
    body: { id, reason } as Record<string, unknown>,
  });
}

export function cancelByAdmin(id: number, reason: string) {
  return http.delete<boolean>('/bpm/process-instance/cancel-by-admin', {
    body: { id, reason } as Record<string, unknown>,
  });
}
