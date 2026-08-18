import type { PageParam, PageResult } from '@vben/request';

import type { BpmProcessDefinitionApi } from '#/api/bpm/definition';

import { requestClient } from '#/api/request';

export namespace BpmApprovalTemplateApi {
  /** 审批模板 */
  export interface ApprovalTemplate {
    id: number;
    code: string;
    name: string;
    description?: string;
    icon?: string;
    category: string;
    categoryName?: string;
    visible: boolean;
    sort: number;
    processDefinitionId: string;
    processDefinitionKey: string;
    processDefinitionName?: string;
    modelId?: string;
    modelType?: number;
    formType?: number;
    suspensionState?: number;
    deploymentTime?: number;
    createTime?: string;
  }
}

/** 查询审批模板分页 */
export async function getApprovalTemplatePage(params: PageParam) {
  return requestClient.get<PageResult<BpmApprovalTemplateApi.ApprovalTemplate>>(
    '/bpm/approval-template/page',
    { params },
  );
}

/** 查询审批模板详情 */
export async function getApprovalTemplate(id: number) {
  return requestClient.get<BpmApprovalTemplateApi.ApprovalTemplate>(
    `/bpm/approval-template/get?id=${id}`,
  );
}

/** 修改审批模板 */
export async function updateApprovalTemplate(
  data: BpmApprovalTemplateApi.ApprovalTemplate,
) {
  return requestClient.put<boolean>('/bpm/approval-template/update', data);
}

/** 修改审批模板上下架 */
export async function updateApprovalTemplateVisible(
  id: number,
  visible: boolean,
) {
  return requestClient.put<boolean>('/bpm/approval-template/update-visible', {
    id,
    visible,
  });
}

/** 查询当前用户可发起的审批模板列表 */
export async function getApprovalTemplateList() {
  return requestClient.get<BpmProcessDefinitionApi.ProcessDefinition[]>(
    '/bpm/approval-template/list',
  );
}
