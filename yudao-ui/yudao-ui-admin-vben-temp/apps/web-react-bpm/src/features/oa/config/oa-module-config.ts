import type { OAModuleKey } from '@/entities/oa/api/oa-api';

export interface OAFieldOption {
  label: string;
  value: number | string;
}

export interface OAFieldConfig {
  field: string;
  label: string;
  options?: OAFieldOption[];
  placeholder?: string;
  required?: boolean;
  rows?: number;
  type:
    | 'datetime'
    | 'dept-multi-select'
    | 'files'
    | 'number'
    | 'switch'
    | 'text'
    | 'textarea'
    | 'user-multi-select'
    | 'user-select';
}

export interface OADetailFieldConfig {
  field: string;
  label: string;
  type?: 'datetime' | 'files' | 'number' | 'switch' | 'text';
}

export interface OAModuleConfig {
  categoryLabel: string;
  detailFields: OADetailFieldConfig[];
  description: string;
  fields: OAFieldConfig[];
  key: OAModuleKey;
  processDefinitionKey: string;
  summaryFields: string[];
  title: string;
}

const buildSharedFields = (typeOptions: OAFieldOption[]): OAFieldConfig[] => [
  {
    field: 'startTime',
    label: '开始时间',
    placeholder: '请选择开始时间',
    required: true,
    type: 'datetime',
  },
  {
    field: 'endTime',
    label: '结束时间',
    placeholder: '请选择结束时间',
    required: true,
    type: 'datetime',
  },
  {
    field: 'type',
    label: '类型',
    options: typeOptions,
    placeholder: '请选择类型',
    required: true,
    type: 'text',
  },
  {
    field: 'reason',
    label: '事由',
    placeholder: '请输入审批事由',
    required: true,
    rows: 4,
    type: 'textarea',
  },
];

const buildSharedDetailFields = (): OADetailFieldConfig[] => [
  { field: 'type', label: '类型' },
  { field: 'startTime', label: '开始时间', type: 'datetime' },
  { field: 'endTime', label: '结束时间', type: 'datetime' },
  { field: 'reason', label: '事由', type: 'text' },
];

export const oaModuleConfigs: Record<OAModuleKey, OAModuleConfig> = {
  attendance: {
    categoryLabel: '考勤',
    detailFields: buildSharedDetailFields(),
    description: '补卡申请',
    fields: buildSharedFields([
      { label: '上班漏打卡', value: 1 },
      { label: '下班漏打卡', value: 2 },
      { label: '外勤补卡', value: 3 },
    ]),
    key: 'attendance',
    processDefinitionKey: 'oa_attendance',
    summaryFields: ['type', 'startTime', 'endTime', 'reason'],
    title: '补卡申请',
  },
  document: {
    categoryLabel: '法务',
    detailFields: [
      { field: 'applicantName', label: '申请人' },
      { field: 'deptName', label: '所属部门' },
      { field: 'fileType', label: '文件类型' },
      { field: 'title', label: '文件标题' },
      { field: 'relatedProject', label: '关联项目' },
      { field: 'counterpartUnit', label: '对方单位' },
      { field: 'amount', label: '金额', type: 'number' },
      { field: 'reason', label: '审批事由' },
      { field: 'attachmentBodyUrls', label: '正文附件', type: 'files' },
      { field: 'attachmentExtraUrls', label: '补充附件', type: 'files' },
      { field: 'remark', label: '备注' },
    ],
    description: '合同/文件审批',
    fields: [
      {
        field: 'fileType',
        label: '文件类型',
        options: [
          { label: '合同', value: '合同' },
          { label: '函件', value: '函件' },
          { label: '请示', value: '请示' },
          { label: '公文', value: '公文' },
        ],
        placeholder: '请选择文件类型',
        required: true,
        type: 'text',
      },
      { field: 'title', label: '文件标题', placeholder: '请输入文件标题', required: true, type: 'text' },
      { field: 'relatedProject', label: '关联项目', placeholder: '请输入关联项目', type: 'text' },
      { field: 'counterpartUnit', label: '对方单位', placeholder: '请输入对方单位', type: 'text' },
      { field: 'amount', label: '金额', placeholder: '请输入金额', type: 'number' },
      { field: 'reason', label: '审批事由', placeholder: '请输入审批事由', required: true, rows: 4, type: 'textarea' },
      { field: 'attachmentBodyUrls', label: '正文附件', type: 'files' },
      { field: 'attachmentExtraUrls', label: '补充附件', type: 'files' },
      { field: 'remark', label: '备注', placeholder: '请输入备注', rows: 3, type: 'textarea' },
    ],
    key: 'document',
    processDefinitionKey: 'oa_document',
    summaryFields: ['fileType', 'title', 'counterpartUnit', 'amount'],
    title: '合同/文件审批',
  },
  expense: {
    categoryLabel: '财务',
    detailFields: buildSharedDetailFields(),
    description: '报销申请',
    fields: buildSharedFields([
      { label: '差旅费', value: 1 },
      { label: '办公费', value: 2 },
      { label: '接待费', value: 3 },
    ]),
    key: 'expense',
    processDefinitionKey: 'oa_expense',
    summaryFields: ['type', 'startTime', 'endTime', 'reason'],
    title: '报销申请',
  },
  leave: {
    categoryLabel: '考勤',
    detailFields: buildSharedDetailFields(),
    description: '请假申请',
    fields: buildSharedFields([
      { label: '事假', value: 1 },
      { label: '病假', value: 2 },
      { label: '年假', value: 3 },
    ]),
    key: 'leave',
    processDefinitionKey: 'oa_leave',
    summaryFields: ['type', 'startTime', 'endTime', 'reason'],
    title: '请假申请',
  },
  overtime: {
    categoryLabel: '考勤',
    detailFields: buildSharedDetailFields(),
    description: '加班申请',
    fields: buildSharedFields([
      { label: '工作日加班', value: 1 },
      { label: '周末加班', value: 2 },
      { label: '节假日加班', value: 3 },
    ]),
    key: 'overtime',
    processDefinitionKey: 'oa_overtime',
    summaryFields: ['type', 'startTime', 'endTime', 'reason'],
    title: '加班申请',
  },
  project: {
    categoryLabel: '项目',
    detailFields: [
      { field: 'applicantName', label: '申请人' },
      { field: 'deptName', label: '所属部门' },
      { field: 'projectName', label: '项目名称' },
      { field: 'projectType', label: '项目类型' },
      { field: 'ownerUnit', label: '业主单位' },
      { field: 'projectSource', label: '项目来源' },
      { field: 'projectLeaderName', label: '项目负责人' },
      { field: 'projectOverview', label: '项目概况' },
      { field: 'projectAmount', label: '合同金额/预估金额', type: 'number' },
      { field: 'plannedStartTime', label: '计划开始时间', type: 'datetime' },
      { field: 'plannedEndTime', label: '计划结束时间', type: 'datetime' },
      { field: 'participantDeptNames', label: '参与部门' },
      { field: 'riskDescription', label: '风险说明' },
      { field: 'attachmentUrls', label: '附件', type: 'files' },
      { field: 'remark', label: '备注' },
    ],
    description: '项目立项申请',
    fields: [
      { field: 'projectName', label: '项目名称', placeholder: '请输入项目名称', required: true, type: 'text' },
      { field: 'projectType', label: '项目类型', placeholder: '请输入项目类型', required: true, type: 'text' },
      { field: 'ownerUnit', label: '业主单位', placeholder: '请输入业主单位', required: true, type: 'text' },
      { field: 'projectSource', label: '项目来源', placeholder: '请输入项目来源', required: true, type: 'text' },
      { field: 'projectLeaderId', label: '项目负责人', placeholder: '请输入项目负责人编号', required: true, type: 'user-select' },
      { field: 'projectOverview', label: '项目概况', placeholder: '请输入项目概况', required: true, rows: 4, type: 'textarea' },
      { field: 'projectAmount', label: '合同金额/预估金额', placeholder: '请输入金额', required: true, type: 'number' },
      { field: 'plannedStartTime', label: '计划开始时间', placeholder: '请选择开始时间', required: true, type: 'datetime' },
      { field: 'plannedEndTime', label: '计划结束时间', placeholder: '请选择结束时间', required: true, type: 'datetime' },
      { field: 'participantDeptIds', label: '参与部门', placeholder: '请输入部门编号，逗号分隔', type: 'dept-multi-select' },
      { field: 'riskDescription', label: '风险说明', placeholder: '请输入风险说明', rows: 3, type: 'textarea' },
      { field: 'attachmentUrls', label: '附件', type: 'files' },
      { field: 'remark', label: '备注', placeholder: '请输入备注', rows: 3, type: 'textarea' },
    ],
    key: 'project',
    processDefinitionKey: 'oa_project',
    summaryFields: ['projectName', 'projectType', 'ownerUnit', 'projectAmount'],
    title: '项目立项申请',
  },
  seal: {
    categoryLabel: '法务',
    detailFields: [
      { field: 'applicantName', label: '申请人' },
      { field: 'deptName', label: '所属部门' },
      { field: 'type', label: '用章类型' },
      { field: 'fileName', label: '文件名称' },
      { field: 'fileCount', label: '文件份数', type: 'number' },
      { field: 'reason', label: '用章事由' },
      { field: 'startTime', label: '使用时间', type: 'datetime' },
      { field: 'counterpartUnit', label: '对方单位' },
      { field: 'externalCarry', label: '是否外带', type: 'switch' },
      { field: 'operatorName', label: '经办人' },
      { field: 'attachmentUrls', label: '附件', type: 'files' },
      { field: 'remark', label: '备注' },
    ],
    description: '用章申请',
    fields: [
      {
        field: 'type',
        label: '用章类型',
        options: [
          { label: '公章', value: 1 },
          { label: '合同章', value: 2 },
          { label: '财务章', value: 3 },
        ],
        placeholder: '请选择用章类型',
        required: true,
        type: 'text',
      },
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
    key: 'seal',
    processDefinitionKey: 'oa_seal',
    summaryFields: ['type', 'fileName', 'fileCount', 'startTime'],
    title: '用章申请',
  },
  staffing: {
    categoryLabel: '项目',
    detailFields: [
      { field: 'applicantName', label: '申请人' },
      { field: 'deptName', label: '所属部门' },
      { field: 'projectName', label: '所属项目' },
      { field: 'memberNames', label: '调入/调出人员' },
      { field: 'reason', label: '调配原因' },
      { field: 'transferTime', label: '调配时间', type: 'datetime' },
      { field: 'expectedWorkPeriod', label: '预计工作周期' },
      { field: 'targetUnit', label: '接收部门或项目组' },
      { field: 'remark', label: '备注' },
    ],
    description: '项目人员调配申请',
    fields: [
      { field: 'projectName', label: '所属项目', placeholder: '请输入所属项目', required: true, type: 'text' },
      { field: 'memberIds', label: '调入/调出人员', placeholder: '请输入用户编号，逗号分隔', required: true, type: 'user-multi-select' },
      { field: 'reason', label: '调配原因', placeholder: '请输入调配原因', required: true, rows: 4, type: 'textarea' },
      { field: 'transferTime', label: '调配时间', placeholder: '请选择调配时间', required: true, type: 'datetime' },
      { field: 'expectedWorkPeriod', label: '预计工作周期', placeholder: '请输入预计工作周期', required: true, type: 'text' },
      { field: 'targetUnit', label: '接收部门或项目组', placeholder: '请输入接收部门或项目组', required: true, type: 'text' },
      { field: 'remark', label: '备注', placeholder: '请输入备注', rows: 3, type: 'textarea' },
    ],
    key: 'staffing',
    processDefinitionKey: 'oa_staffing',
    summaryFields: ['projectName', 'memberIds', 'transferTime', 'targetUnit'],
    title: '项目人员调配申请',
  },
  trip: {
    categoryLabel: '财务',
    detailFields: buildSharedDetailFields(),
    description: '出差申请',
    fields: buildSharedFields([
      { label: '项目调研', value: 1 },
      { label: '汇报对接', value: 2 },
      { label: '外地驻场', value: 3 },
    ]),
    key: 'trip',
    processDefinitionKey: 'oa_trip',
    summaryFields: ['type', 'startTime', 'endTime', 'reason'],
    title: '出差申请',
  },
};

export const oaModuleOrder: OAModuleKey[] = [
  'expense',
  'trip',
  'leave',
  'overtime',
  'attendance',
  'document',
  'seal',
  'project',
  'staffing',
];
