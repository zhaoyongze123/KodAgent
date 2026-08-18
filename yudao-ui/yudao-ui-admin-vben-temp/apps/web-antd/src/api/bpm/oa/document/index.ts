import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace BpmOADocumentApi {
  export interface Document {
    id?: number;
    applicantName?: string;
    attachmentBodyUrls?: string | string[];
    attachmentExtraUrls?: string | string[];
    amount?: number | string;
    counterpartUnit?: string;
    createTime?: string;
    deptId?: number;
    deptName?: string;
    fileType: string;
    processInstanceId?: string;
    reason: string;
    relatedProject?: string;
    remark?: string;
    startUserSelectAssignees?: Record<string, number[]>;
    status?: number;
    title: string;
  }
}

export async function createDocument(data: BpmOADocumentApi.Document) {
  return requestClient.post('/bpm/oa/document/create', data);
}

export async function getDocument(id: number) {
  return requestClient.get<BpmOADocumentApi.Document>(`/bpm/oa/document/get?id=${id}`);
}

export async function getDocumentPage(params: PageParam) {
  return requestClient.get<PageResult<BpmOADocumentApi.Document>>('/bpm/oa/document/page', {
    params,
  });
}
