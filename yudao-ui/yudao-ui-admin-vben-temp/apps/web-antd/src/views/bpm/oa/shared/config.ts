import type { OAModuleApiKey } from '#/api/bpm/oa/common';

import dayjs from 'dayjs';

const BPM_OA_DICT_TYPE = 'bpm_oa_type';

type OARouteNames = {
  create: string;
  detail: string;
  index: string;
};

interface OAModuleViewConfig {
  activePath: string;
  buildProcessVariables?: (formData: Record<string, any>) => Record<string, any>;
  dictType: string;
  fallbackTypeOptions?: Array<{
    label: string;
    value: number | string;
  }>;
  key: OAModuleApiKey;
  processDefinitionKey: string;
  routeNames: OARouteNames;
  title: string;
}

const oaModuleViewConfigs: Record<OAModuleApiKey, OAModuleViewConfig> = {
  attendance: {
    activePath: '/bpm/oa/attendance',
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [
      { label: '上班漏打卡', value: 1 },
      { label: '下班漏打卡', value: 2 },
      { label: '外勤补卡', value: 3 },
    ],
    key: 'attendance',
    processDefinitionKey: 'oa_attendance',
    routeNames: {
      create: 'OAAttendanceCreate',
      detail: 'OAAttendanceDetail',
      index: 'OAAttendanceIndex',
    },
    title: '补卡',
  },
  document: {
    activePath: '/bpm/oa/document',
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [],
    key: 'document',
    processDefinitionKey: 'oa_document',
    routeNames: {
      create: 'OADocumentCreate',
      detail: 'OADocumentDetail',
      index: 'OADocumentIndex',
    },
    title: '合同/文件审批',
  },
  expense: {
    activePath: '/bpm/oa/expense',
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [
      { label: '差旅费', value: 1 },
      { label: '办公费', value: 2 },
      { label: '接待费', value: 3 },
    ],
    key: 'expense',
    processDefinitionKey: 'oa_expense',
    routeNames: {
      create: 'OAExpenseCreate',
      detail: 'OAExpenseDetail',
      index: 'OAExpenseIndex',
    },
    title: '报销',
  },
  leaveCancel: {
    activePath: '/bpm/oa/leave-cancel',
    buildProcessVariables: (formData) => ({
      day: Math.max(
        dayjs(formData?.endTime).diff(dayjs(formData?.startTime), 'day'),
        0,
      ),
    }),
    dictType: 'bpm_oa_leave_type',
    fallbackTypeOptions: [
      { label: '病假', value: 1 },
      { label: '事假', value: 2 },
      { label: '婚假', value: 3 },
    ],
    key: 'leaveCancel',
    processDefinitionKey: 'oa_leave_cancel',
    routeNames: {
      create: 'OALeaveCancelCreate',
      detail: 'OALeaveCancelDetail',
      index: 'OALeaveCancelIndex',
    },
    title: '销假',
  },
  overtime: {
    activePath: '/bpm/oa/overtime',
    buildProcessVariables: (formData) => ({
      durationHours: Number(formData?.durationHours || 0),
      day: Number(formData?.durationHours || 0) / 8,
    }),
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [
      { label: '工作日加班', value: 1 },
      { label: '周末加班', value: 2 },
      { label: '节假日加班', value: 3 },
    ],
    key: 'overtime',
    processDefinitionKey: 'oa_overtime',
    routeNames: {
      create: 'OAOvertimeCreate',
      detail: 'OAOvertimeDetail',
      index: 'OAOvertimeIndex',
    },
    title: '加班',
  },
  outing: {
    activePath: '/bpm/oa/outing',
    buildProcessVariables: (formData) => ({
      durationHours: Number(formData?.durationHours || 0),
      day: Number(formData?.durationHours || 0) / 8,
    }),
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [
      { label: '项目现场', value: 1 },
      { label: '政府汇报', value: 2 },
      { label: '商务洽谈', value: 3 },
    ],
    key: 'outing',
    processDefinitionKey: 'oa_outing',
    routeNames: {
      create: 'OAOutingCreate',
      detail: 'OAOutingDetail',
      index: 'OAOutingIndex',
    },
    title: '临时外出',
  },
  project: {
    activePath: '/bpm/oa/project',
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [],
    key: 'project',
    processDefinitionKey: 'oa_project',
    routeNames: {
      create: 'OAProjectCreate',
      detail: 'OAProjectDetail',
      index: 'OAProjectIndex',
    },
    title: '项目立项申请',
  },
  seal: {
    activePath: '/bpm/oa/seal',
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [
      { label: '公章', value: 1 },
      { label: '合同章', value: 2 },
      { label: '财务章', value: 3 },
    ],
    key: 'seal',
    processDefinitionKey: 'oa_seal',
    routeNames: {
      create: 'OASealCreate',
      detail: 'OASealDetail',
      index: 'OASealIndex',
    },
    title: '用章',
  },
  staffing: {
    activePath: '/bpm/oa/staffing',
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [],
    key: 'staffing',
    processDefinitionKey: 'oa_staffing',
    routeNames: {
      create: 'OAStaffingCreate',
      detail: 'OAStaffingDetail',
      index: 'OAStaffingIndex',
    },
    title: '项目人员调配申请',
  },
  trip: {
    activePath: '/bpm/oa/trip',
    dictType: BPM_OA_DICT_TYPE,
    fallbackTypeOptions: [
      { label: '项目调研', value: 1 },
      { label: '汇报对接', value: 2 },
      { label: '外地驻场', value: 3 },
    ],
    key: 'trip',
    processDefinitionKey: 'oa_trip',
    routeNames: {
      create: 'OATripCreate',
      detail: 'OATripDetail',
      index: 'OATripIndex',
    },
    title: '出差',
  },
};

function getOAModuleViewConfig(key: OAModuleApiKey) {
  return oaModuleViewConfigs[key];
}

export { getOAModuleViewConfig, oaModuleViewConfigs };
export type { OAModuleApiKey, OAModuleViewConfig };
