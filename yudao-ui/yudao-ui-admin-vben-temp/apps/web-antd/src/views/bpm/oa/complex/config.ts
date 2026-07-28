import type { PageParam, PageResult } from '@vben/request';
import type { SystemDeptApi } from '#/api/system/dept';
import type { SystemUserApi } from '#/api/system/user';
import type { SystemUserProfileApi } from '#/api/system/user/profile';

import { getDocumentPage, type BpmOADocumentApi, createDocument, getDocument } from '#/api/bpm/oa/document';
import { getProjectPage, type BpmOAProjectApi, createProject, getProject } from '#/api/bpm/oa/project';
import { getSealPage, type BpmOASealApi, createSeal, getSeal } from '#/api/bpm/oa/seal';
import { getStaffingPage, type BpmOAStaffingApi, createStaffing, getStaffing } from '#/api/bpm/oa/staffing';

export type ComplexOAModuleKey = 'document' | 'project' | 'seal' | 'staffing';

export interface SelectOption {
  label: string;
  value: number | string;
}

type FieldType =
  | 'datetime'
  | 'dept-multi-select'
  | 'files'
  | 'number'
  | 'readonly'
  | 'select'
  | 'switch'
  | 'text'
  | 'textarea'
  | 'user-multi-select'
  | 'user-select';

export interface ComplexFieldConfig {
  field: string;
  label: string;
  placeholder?: string;
  required?: boolean;
  rows?: number;
  submit?: boolean;
  type: FieldType;
  options?: SelectOption[];
}

export interface ComplexTableColumn {
  field: string;
  label: string;
  type?: 'amount' | 'boolean' | 'datetime' | 'select' | 'status' | 'text';
  options?: SelectOption[];
  width?: number;
}

export interface ComplexModuleViewConfig {
  buildProcessVariables: (data: Record<string, any>) => Record<string, any>;
  createFields: ComplexFieldConfig[];
  createRequest: (data: Record<string, any>) => Promise<unknown>;
  detailFields: ComplexFieldConfig[];
  getDetailRequest: (id: number) => Promise<Record<string, any>>;
  getPageRequest: (params: PageParam) => Promise<PageResult<Record<string, any>>>;
  key: ComplexOAModuleKey;
  previewWatchFields: string[];
  processDefinitionKey: string;
  routeNames: {
    create: string;
    detail: string;
    index: string;
  };
  searchFields: ComplexFieldConfig[];
  tableColumns: ComplexTableColumn[];
  title: string;
}

const sealTypeOptions: SelectOption[] = [
  { label: '公章', value: 1 },
  { label: '合同章', value: 2 },
  { label: '财务章', value: 3 },
];

const documentTypeOptions: SelectOption[] = [
  { label: '合同', value: '合同' },
  { label: '函件', value: '函件' },
  { label: '请示', value: '请示' },
  { label: '公文', value: '公文' },
];

const projectTypeOptions: SelectOption[] = [
  { label: '总体规划', value: '总体规划' },
  { label: '详细规划', value: '详细规划' },
  { label: '专项规划', value: '专项规划' },
  { label: '城市设计', value: '城市设计' },
];

const complexModuleConfigs: Record<ComplexOAModuleKey, ComplexModuleViewConfig> = {
  document: {
    buildProcessVariables: (data) => ({
      amount: data.amount ? Number(data.amount) : 0,
    }),
    createFields: [
      { field: 'applicantName', label: '申请人', submit: false, type: 'readonly' },
      { field: 'deptName', label: '部门', submit: false, type: 'readonly' },
      { field: 'fileType', label: '文件类型', options: documentTypeOptions, placeholder: '请选择文件类型', required: true, type: 'select' },
      { field: 'title', label: '文件标题', placeholder: '请输入文件标题', required: true, type: 'text' },
      { field: 'relatedProject', label: '关联项目', placeholder: '请输入关联项目', type: 'text' },
      { field: 'counterpartUnit', label: '对方单位', placeholder: '请输入对方单位', type: 'text' },
      { field: 'amount', label: '金额', placeholder: '请输入金额', type: 'number' },
      { field: 'reason', label: '审批事由', placeholder: '请输入审批事由', required: true, rows: 4, type: 'textarea' },
      { field: 'attachmentBodyUrls', label: '附件正文', type: 'files' },
      { field: 'attachmentExtraUrls', label: '附件补充材料', type: 'files' },
      { field: 'remark', label: '备注', placeholder: '请输入备注', rows: 3, type: 'textarea' },
    ],
    createRequest: createDocument,
    detailFields: [
      { field: 'applicantName', label: '申请人', type: 'readonly' },
      { field: 'deptName', label: '部门', type: 'readonly' },
      { field: 'fileType', label: '文件类型', options: documentTypeOptions, type: 'select' },
      { field: 'title', label: '文件标题', type: 'text' },
      { field: 'relatedProject', label: '关联项目', type: 'text' },
      { field: 'counterpartUnit', label: '对方单位', type: 'text' },
      { field: 'amount', label: '金额', type: 'number' },
      { field: 'reason', label: '审批事由', type: 'textarea' },
      { field: 'attachmentBodyUrls', label: '附件正文', type: 'files' },
      { field: 'attachmentExtraUrls', label: '附件补充材料', type: 'files' },
      { field: 'remark', label: '备注', type: 'textarea' },
    ],
    getDetailRequest: (id) => getDocument(id) as Promise<Record<string, any>>,
    getPageRequest: (params) => getDocumentPage(params) as Promise<PageResult<Record<string, any>>>,
    key: 'document',
    previewWatchFields: ['amount'],
    processDefinitionKey: 'oa_document',
    routeNames: {
      create: 'OADocumentCreate',
      detail: 'OADocumentDetail',
      index: 'OADocumentIndex',
    },
    searchFields: [
      { field: 'fileType', label: '文件类型', options: documentTypeOptions, placeholder: '请选择文件类型', type: 'select' },
      { field: 'title', label: '文件标题', placeholder: '请输入文件标题', type: 'text' },
      { field: 'relatedProject', label: '关联项目', placeholder: '请输入关联项目', type: 'text' },
      { field: 'counterpartUnit', label: '对方单位', placeholder: '请输入对方单位', type: 'text' },
    ],
    tableColumns: [
      { field: 'id', label: '编号', width: 90 },
      { field: 'status', label: '状态', type: 'status', width: 100 },
      { field: 'fileType', label: '文件类型', type: 'select', options: documentTypeOptions, width: 120 },
      { field: 'title', label: '文件标题', width: 220 },
      { field: 'relatedProject', label: '关联项目', width: 180 },
      { field: 'counterpartUnit', label: '对方单位', width: 180 },
      { field: 'amount', label: '金额', type: 'amount', width: 120 },
      { field: 'createTime', label: '申请时间', type: 'datetime', width: 180 },
    ],
    title: '合同/文件审批',
  },
  project: {
    buildProcessVariables: (data) => ({
      projectAmount: data.projectAmount ? Number(data.projectAmount) : 0,
    }),
    createFields: [
      { field: 'applicantName', label: '申请人', submit: false, type: 'readonly' },
      { field: 'deptName', label: '部门', submit: false, type: 'readonly' },
      { field: 'projectName', label: '项目名称', placeholder: '请输入项目名称', required: true, type: 'text' },
      { field: 'projectType', label: '项目类型', options: projectTypeOptions, placeholder: '请选择项目类型', required: true, type: 'select' },
      { field: 'ownerUnit', label: '业主单位', placeholder: '请输入业主单位', required: true, type: 'text' },
      { field: 'projectSource', label: '项目来源', placeholder: '请输入项目来源', required: true, type: 'text' },
      { field: 'projectLeaderId', label: '项目负责人', placeholder: '请选择项目负责人', required: true, type: 'user-select' },
      { field: 'projectOverview', label: '项目概况', placeholder: '请输入项目概况', required: true, rows: 4, type: 'textarea' },
      { field: 'projectAmount', label: '合同金额/预估金额', placeholder: '请输入金额', required: true, type: 'number' },
      { field: 'plannedStartTime', label: '计划开始时间', placeholder: '请选择计划开始时间', required: true, type: 'datetime' },
      { field: 'plannedEndTime', label: '计划结束时间', placeholder: '请选择计划结束时间', required: true, type: 'datetime' },
      { field: 'participantDeptIds', label: '参与部门', placeholder: '请选择参与部门', type: 'dept-multi-select' },
      { field: 'riskDescription', label: '风险说明', placeholder: '请输入风险说明', rows: 3, type: 'textarea' },
      { field: 'attachmentUrls', label: '附件', type: 'files' },
      { field: 'remark', label: '备注', placeholder: '请输入备注', rows: 3, type: 'textarea' },
    ],
    createRequest: createProject,
    detailFields: [
      { field: 'applicantName', label: '申请人', type: 'readonly' },
      { field: 'deptName', label: '部门', type: 'readonly' },
      { field: 'projectName', label: '项目名称', type: 'text' },
      { field: 'projectType', label: '项目类型', options: projectTypeOptions, type: 'select' },
      { field: 'ownerUnit', label: '业主单位', type: 'text' },
      { field: 'projectSource', label: '项目来源', type: 'text' },
      { field: 'projectLeaderName', label: '项目负责人', type: 'text' },
      { field: 'projectOverview', label: '项目概况', type: 'textarea' },
      { field: 'projectAmount', label: '合同金额/预估金额', type: 'number' },
      { field: 'plannedStartTime', label: '计划开始时间', type: 'datetime' },
      { field: 'plannedEndTime', label: '计划结束时间', type: 'datetime' },
      { field: 'participantDeptNames', label: '参与部门', type: 'text' },
      { field: 'riskDescription', label: '风险说明', type: 'textarea' },
      { field: 'attachmentUrls', label: '附件', type: 'files' },
      { field: 'remark', label: '备注', type: 'textarea' },
    ],
    getDetailRequest: (id) => getProject(id) as Promise<Record<string, any>>,
    getPageRequest: (params) => getProjectPage(params) as Promise<PageResult<Record<string, any>>>,
    key: 'project',
    previewWatchFields: ['projectAmount'],
    processDefinitionKey: 'oa_project',
    routeNames: {
      create: 'OAProjectCreate',
      detail: 'OAProjectDetail',
      index: 'OAProjectIndex',
    },
    searchFields: [
      { field: 'projectName', label: '项目名称', placeholder: '请输入项目名称', type: 'text' },
      { field: 'projectType', label: '项目类型', options: projectTypeOptions, placeholder: '请选择项目类型', type: 'select' },
      { field: 'ownerUnit', label: '业主单位', placeholder: '请输入业主单位', type: 'text' },
    ],
    tableColumns: [
      { field: 'id', label: '编号', width: 90 },
      { field: 'status', label: '状态', type: 'status', width: 100 },
      { field: 'projectName', label: '项目名称', width: 220 },
      { field: 'projectType', label: '项目类型', type: 'select', options: projectTypeOptions, width: 120 },
      { field: 'ownerUnit', label: '业主单位', width: 180 },
      { field: 'projectLeaderName', label: '项目负责人', width: 140 },
      { field: 'projectAmount', label: '金额', type: 'amount', width: 120 },
      { field: 'createTime', label: '申请时间', type: 'datetime', width: 180 },
    ],
    title: '项目立项申请',
  },
  seal: {
    buildProcessVariables: (data) => ({
      externalCarry: Boolean(data.externalCarry),
      fileCount: data.fileCount ? Number(data.fileCount) : 0,
    }),
    createFields: [
      { field: 'applicantName', label: '申请人', submit: false, type: 'readonly' },
      { field: 'deptName', label: '部门', submit: false, type: 'readonly' },
      { field: 'type', label: '用章类型', options: sealTypeOptions, placeholder: '请选择用章类型', required: true, type: 'select' },
      { field: 'fileName', label: '文件名称', placeholder: '请输入文件名称', required: true, type: 'text' },
      { field: 'fileCount', label: '文件份数', placeholder: '请输入文件份数', required: true, type: 'number' },
      { field: 'reason', label: '用章事由', placeholder: '请输入用章事由', required: true, rows: 4, type: 'textarea' },
      { field: 'startTime', label: '使用时间', placeholder: '请选择使用时间', required: true, type: 'datetime' },
      { field: 'counterpartUnit', label: '对方单位', placeholder: '请输入对方单位', type: 'text' },
      { field: 'externalCarry', label: '是否外带', type: 'switch' },
      { field: 'operatorName', label: '经办人', placeholder: '请输入经办人', required: true, type: 'text' },
      { field: 'attachmentUrls', label: '附件', type: 'files' },
      { field: 'remark', label: '备注', placeholder: '请输入备注', rows: 3, type: 'textarea' },
    ],
    createRequest: createSeal,
    detailFields: [
      { field: 'applicantName', label: '申请人', type: 'readonly' },
      { field: 'deptName', label: '部门', type: 'readonly' },
      { field: 'type', label: '用章类型', options: sealTypeOptions, type: 'select' },
      { field: 'fileName', label: '文件名称', type: 'text' },
      { field: 'fileCount', label: '文件份数', type: 'number' },
      { field: 'reason', label: '用章事由', type: 'textarea' },
      { field: 'startTime', label: '使用时间', type: 'datetime' },
      { field: 'counterpartUnit', label: '对方单位', type: 'text' },
      { field: 'externalCarry', label: '是否外带', type: 'switch' },
      { field: 'operatorName', label: '经办人', type: 'text' },
      { field: 'attachmentUrls', label: '附件', type: 'files' },
      { field: 'remark', label: '备注', type: 'textarea' },
    ],
    getDetailRequest: (id) => getSeal(id) as Promise<Record<string, any>>,
    getPageRequest: (params) => getSealPage(params) as Promise<PageResult<Record<string, any>>>,
    key: 'seal',
    previewWatchFields: ['externalCarry', 'fileCount'],
    processDefinitionKey: 'oa_seal',
    routeNames: {
      create: 'OASealCreate',
      detail: 'OASealDetail',
      index: 'OASealIndex',
    },
    searchFields: [
      { field: 'type', label: '用章类型', options: sealTypeOptions, placeholder: '请选择用章类型', type: 'select' },
      { field: 'fileName', label: '文件名称', placeholder: '请输入文件名称', type: 'text' },
      { field: 'counterpartUnit', label: '对方单位', placeholder: '请输入对方单位', type: 'text' },
    ],
    tableColumns: [
      { field: 'id', label: '编号', width: 90 },
      { field: 'status', label: '状态', type: 'status', width: 100 },
      { field: 'type', label: '用章类型', options: sealTypeOptions, type: 'select', width: 120 },
      { field: 'fileName', label: '文件名称', width: 220 },
      { field: 'fileCount', label: '份数', width: 90 },
      { field: 'counterpartUnit', label: '对方单位', width: 180 },
      { field: 'startTime', label: '使用时间', type: 'datetime', width: 180 },
      { field: 'createTime', label: '申请时间', type: 'datetime', width: 180 },
    ],
    title: '用章申请',
  },
  staffing: {
    buildProcessVariables: (data) => ({
      memberCount: Array.isArray(data.memberIds) ? data.memberIds.length : 0,
    }),
    createFields: [
      { field: 'applicantName', label: '申请人', submit: false, type: 'readonly' },
      { field: 'deptName', label: '部门', submit: false, type: 'readonly' },
      { field: 'projectName', label: '所属项目', placeholder: '请输入所属项目', required: true, type: 'text' },
      { field: 'memberIds', label: '调入/调出人员', placeholder: '请选择调入/调出人员', required: true, type: 'user-multi-select' },
      { field: 'reason', label: '调配原因', placeholder: '请输入调配原因', required: true, rows: 4, type: 'textarea' },
      { field: 'transferTime', label: '调配时间', placeholder: '请选择调配时间', required: true, type: 'datetime' },
      { field: 'expectedWorkPeriod', label: '预计工作周期', placeholder: '请输入预计工作周期', required: true, type: 'text' },
      { field: 'targetUnit', label: '接收部门或项目组', placeholder: '请输入接收部门或项目组', required: true, type: 'text' },
      { field: 'remark', label: '备注', placeholder: '请输入备注', rows: 3, type: 'textarea' },
    ],
    createRequest: createStaffing,
    detailFields: [
      { field: 'applicantName', label: '申请人', type: 'readonly' },
      { field: 'deptName', label: '部门', type: 'readonly' },
      { field: 'projectName', label: '所属项目', type: 'text' },
      { field: 'memberNames', label: '调入/调出人员', type: 'text' },
      { field: 'reason', label: '调配原因', type: 'textarea' },
      { field: 'transferTime', label: '调配时间', type: 'datetime' },
      { field: 'expectedWorkPeriod', label: '预计工作周期', type: 'text' },
      { field: 'targetUnit', label: '接收部门或项目组', type: 'text' },
      { field: 'remark', label: '备注', type: 'textarea' },
    ],
    getDetailRequest: (id) => getStaffing(id) as Promise<Record<string, any>>,
    getPageRequest: (params) => getStaffingPage(params) as Promise<PageResult<Record<string, any>>>,
    key: 'staffing',
    previewWatchFields: ['memberIds'],
    processDefinitionKey: 'oa_staffing',
    routeNames: {
      create: 'OAStaffingCreate',
      detail: 'OAStaffingDetail',
      index: 'OAStaffingIndex',
    },
    searchFields: [
      { field: 'projectName', label: '所属项目', placeholder: '请输入所属项目', type: 'text' },
      { field: 'reason', label: '调配原因', placeholder: '请输入调配原因', type: 'text' },
      { field: 'targetUnit', label: '接收部门或项目组', placeholder: '请输入接收部门或项目组', type: 'text' },
    ],
    tableColumns: [
      { field: 'id', label: '编号', width: 90 },
      { field: 'status', label: '状态', type: 'status', width: 100 },
      { field: 'projectName', label: '所属项目', width: 220 },
      { field: 'memberNames', label: '调入/调出人员', width: 220 },
      { field: 'targetUnit', label: '接收部门或项目组', width: 180 },
      { field: 'transferTime', label: '调配时间', type: 'datetime', width: 180 },
      { field: 'createTime', label: '申请时间', type: 'datetime', width: 180 },
    ],
    title: '项目人员调配申请',
  },
};

function getComplexModuleViewConfig(key: ComplexOAModuleKey) {
  return complexModuleConfigs[key];
}

function buildUserOptions(users: SystemUserApi.User[]) {
  return users.map((item) => ({
    label: item.nickname,
    value: item.id as number,
  }));
}

function buildDeptOptions(depts: SystemDeptApi.Dept[]) {
  return depts.map((item) => ({
    label: item.name,
    value: item.id as number,
  }));
}

function applyProfileDefaults(
  config: ComplexModuleViewConfig,
  profile?: SystemUserProfileApi.UserProfileRespVO | null,
) {
  const defaults: Record<string, any> = {};
  if (!profile) {
    return defaults;
  }
  for (const field of config.createFields) {
    if (field.field === 'applicantName') {
      defaults.applicantName = profile.nickname;
    }
    if (field.field === 'deptName') {
      defaults.deptName = profile.dept?.name || '';
    }
  }
  return defaults;
}

function parseJsonArray(value: unknown) {
  if (Array.isArray(value)) {
    return value;
  }
  if (typeof value !== 'string' || value.trim() === '') {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }
}

function normalizeFieldValue(field: ComplexFieldConfig, value: unknown) {
  if (field.type === 'datetime') {
    return value ? String(value) : undefined;
  }
  if (field.type === 'dept-multi-select' || field.type === 'files' || field.type === 'user-multi-select') {
    return parseJsonArray(value);
  }
  if (field.type === 'switch') {
    return Boolean(value);
  }
  return value;
}

function buildSubmitPayload(config: ComplexModuleViewConfig, formState: Record<string, any>) {
  const payload: Record<string, any> = {};
  for (const field of config.createFields) {
    if (field.submit === false) {
      continue;
    }
    const value = formState[field.field];
    if (field.type === 'datetime') {
      payload[field.field] = value ? Number(value) : value;
      continue;
    }
    if (field.type === 'text' || field.type === 'textarea') {
      payload[field.field] = typeof value === 'string' ? value.trim() : value;
      continue;
    }
    payload[field.field] = value;
  }
  return payload;
}

export {
  applyProfileDefaults,
  buildDeptOptions,
  buildSubmitPayload,
  buildUserOptions,
  getComplexModuleViewConfig,
  normalizeFieldValue,
  parseJsonArray,
};

export type {
  ComplexFieldConfig,
  ComplexModuleViewConfig,
  ComplexOAModuleKey,
  ComplexTableColumn,
};
