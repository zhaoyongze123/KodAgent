import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace BpmOAProjectApi {
  export interface Project {
    id?: number;
    applicantName?: string;
    attachmentUrls?: string | string[];
    createTime?: string;
    deptId?: number;
    deptName?: string;
    ownerUnit: string;
    participantDeptIds?: number[] | string;
    participantDeptNames?: string;
    plannedEndTime: number | string;
    plannedStartTime: number | string;
    processInstanceId?: string;
    projectAmount: number | string;
    projectLeaderId: number;
    projectLeaderName?: string;
    projectName: string;
    projectOverview: string;
    projectSource: string;
    projectType: string;
    remark?: string;
    riskDescription?: string;
    startUserSelectAssignees?: Record<string, number[]>;
    status?: number;
  }
}

export async function createProject(data: BpmOAProjectApi.Project) {
  return requestClient.post('/bpm/oa/project/create', data);
}

export async function getProject(id: number) {
  return requestClient.get<BpmOAProjectApi.Project>(`/bpm/oa/project/get?id=${id}`);
}

export async function getProjectPage(params: PageParam) {
  return requestClient.get<PageResult<BpmOAProjectApi.Project>>('/bpm/oa/project/page', {
    params,
  });
}
