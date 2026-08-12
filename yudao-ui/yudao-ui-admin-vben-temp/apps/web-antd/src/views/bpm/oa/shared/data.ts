import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { DescriptionItemSchema } from '#/components/description';

import { DICT_TYPE } from '@vben/constants';
import { getDictLabel, getDictOptions } from '@vben/hooks';
import {
  formatFlowFormDate,
  formatFlowFormDateTime,
} from '#/components/form-create';
import { getRangePickerDefaultProps } from '#/utils';

import type { OAModuleViewConfig } from './config';

const compensationTypeOptions = [
  { label: '调休', value: 1 },
  { label: '加班费', value: 2 },
  { label: '无', value: 3 },
];

const outingOfficeOptions = [
  { label: '院内外出', value: false },
  { label: '离院外出', value: true },
];

function getFallbackTypeLabel(
  config: OAModuleViewConfig,
  value: null | number | string | undefined,
) {
  if (value === undefined || value === null) {
    return '-';
  }
  const matched = config.fallbackTypeOptions?.find(
    (item) => String(item.value) === String(value),
  );
  return matched?.label || String(value);
}

function useFormSchema(config: OAModuleViewConfig): VbenFormSchema[] {
  const typeLabel = `${config.title}类型`;
  const reasonLabel = `${config.title}原因`;
  const typeOptions = getTypeOptions(config);

  if (config.key === 'overtime') {
    return [
      {
        fieldName: 'type',
        label: typeLabel,
        component: 'Select',
        componentProps: {
          placeholder: `请选择${typeLabel}`,
          options: typeOptions,
          allowClear: true,
        },
        rules: 'required',
      },
      {
        fieldName: 'workDate',
        label: '加班日期',
        component: 'DatePicker',
        componentProps: {
          placeholder: '请选择加班日期',
          valueFormat: 'YYYY-MM-DD',
          format: 'YYYY-MM-DD',
        },
        rules: 'required',
      },
      {
        fieldName: 'startTime',
        label: '开始时间',
        component: 'DatePicker',
        componentProps: {
          placeholder: '请选择开始时间',
          showTime: true,
          valueFormat: 'x',
          format: 'YYYY-MM-DD HH:mm:ss',
        },
        rules: 'required',
      },
      {
        fieldName: 'endTime',
        label: '结束时间',
        component: 'DatePicker',
        componentProps: {
          placeholder: '请选择结束时间',
          showTime: true,
          valueFormat: 'x',
          format: 'YYYY-MM-DD HH:mm:ss',
        },
        rules: 'required',
      },
      {
        fieldName: 'durationHours',
        label: '加班时长（小时）',
        component: 'InputNumber',
        componentProps: {
          placeholder: '请输入加班时长',
          min: 0.5,
          step: 0.5,
          precision: 2,
          class: 'w-full',
        },
        rules: 'required',
      },
      {
        fieldName: 'workLocation',
        label: '加班地点',
        component: 'Input',
        componentProps: {
          placeholder: '请输入加班地点',
        },
      },
      {
        fieldName: 'projectName',
        label: '关联项目',
        component: 'Input',
        componentProps: {
          placeholder: '请输入关联项目',
        },
      },
      {
        fieldName: 'compensationType',
        label: '补偿方式',
        component: 'Select',
        componentProps: {
          placeholder: '请选择补偿方式',
          options: compensationTypeOptions,
          allowClear: true,
        },
      },
      {
        fieldName: 'workContent',
        label: '加班内容',
        component: 'Textarea',
        componentProps: {
          placeholder: '请输入加班内容',
          rows: 4,
        },
        rules: 'required',
      },
      {
        fieldName: 'reason',
        label: '申请说明',
        component: 'Textarea',
        componentProps: {
          placeholder: '请输入申请说明',
          rows: 3,
        },
        rules: 'required',
      },
      {
        fieldName: 'remark',
        label: '备注',
        component: 'Textarea',
        componentProps: {
          placeholder: '请输入备注',
          rows: 3,
        },
      },
    ];
  }

  if (config.key === 'outing') {
    return [
      {
        fieldName: 'type',
        label: typeLabel,
        component: 'Select',
        componentProps: {
          placeholder: `请选择${typeLabel}`,
          options: typeOptions,
          allowClear: true,
        },
        rules: 'required',
      },
      {
        fieldName: 'outingDate',
        label: '外出日期',
        component: 'DatePicker',
        componentProps: {
          placeholder: '请选择外出日期',
          valueFormat: 'YYYY-MM-DD',
          format: 'YYYY-MM-DD',
        },
        rules: 'required',
      },
      {
        fieldName: 'startTime',
        label: '开始时间',
        component: 'DatePicker',
        componentProps: {
          placeholder: '请选择开始时间',
          showTime: true,
          valueFormat: 'x',
          format: 'YYYY-MM-DD HH:mm:ss',
        },
        rules: 'required',
      },
      {
        fieldName: 'endTime',
        label: '结束时间',
        component: 'DatePicker',
        componentProps: {
          placeholder: '请选择结束时间',
          showTime: true,
          valueFormat: 'x',
          format: 'YYYY-MM-DD HH:mm:ss',
        },
        rules: 'required',
      },
      {
        fieldName: 'durationHours',
        label: '外出时长（小时）',
        component: 'InputNumber',
        componentProps: {
          placeholder: '请输入外出时长',
          min: 0.5,
          step: 0.5,
          precision: 2,
          class: 'w-full',
        },
        rules: 'required',
      },
      {
        fieldName: 'destination',
        label: '外出地点',
        component: 'Input',
        componentProps: {
          placeholder: '请输入外出地点',
        },
        rules: 'required',
      },
      {
        fieldName: 'outsideOffice',
        label: '外出范围',
        component: 'Select',
        componentProps: {
          placeholder: '请选择外出范围',
          options: outingOfficeOptions,
          allowClear: true,
        },
      },
      {
        fieldName: 'contactMobile',
        label: '联系电话',
        component: 'Input',
        componentProps: {
          placeholder: '请输入联系电话',
        },
      },
      {
        fieldName: 'companionNames',
        label: '同行人员',
        component: 'Input',
        componentProps: {
          placeholder: '请输入同行人员，多个用顿号分隔',
        },
      },
      {
        fieldName: 'reason',
        label: reasonLabel,
        component: 'Textarea',
        componentProps: {
          placeholder: `请输入${reasonLabel}`,
          rows: 4,
        },
        rules: 'required',
      },
      {
        fieldName: 'remark',
        label: '备注',
        component: 'Textarea',
        componentProps: {
          placeholder: '请输入备注',
          rows: 3,
        },
      },
    ];
  }

  return [
    {
      fieldName: 'type',
      label: typeLabel,
      component: 'Select',
      componentProps: {
        placeholder: `请选择${typeLabel}`,
        options: typeOptions,
        allowClear: true,
      },
      rules: 'required',
    },
    {
      fieldName: 'startTime',
      label: '开始时间',
      component: 'DatePicker',
      componentProps: {
        placeholder: '请选择开始时间',
        showTime: true,
        valueFormat: 'x',
        format: 'YYYY-MM-DD HH:mm:ss',
      },
      rules: 'required',
    },
    {
      fieldName: 'endTime',
      label: '结束时间',
      component: 'DatePicker',
      componentProps: {
        placeholder: '请选择结束时间',
        showTime: true,
        valueFormat: 'x',
        format: 'YYYY-MM-DD HH:mm:ss',
      },
      rules: 'required',
    },
    {
      fieldName: 'reason',
      label: reasonLabel,
      component: 'Textarea',
      componentProps: {
        placeholder: `请输入${reasonLabel}`,
      },
      rules: 'required',
    },
  ];
}

function useGridFormSchema(config: OAModuleViewConfig): VbenFormSchema[] {
  return [
    {
      fieldName: 'type',
      label: `${config.title}类型`,
      component: 'Select',
      componentProps: {
        placeholder: `请选择${config.title}类型`,
        options: getTypeOptions(config),
        allowClear: true,
      },
    },
    {
      fieldName: 'createTime',
      label: '创建时间',
      component: 'RangePicker',
      componentProps: {
        ...getRangePickerDefaultProps(),
        allowClear: true,
      },
    },
    {
      fieldName: 'status',
      label: '审批结果',
      component: 'Select',
      componentProps: {
        placeholder: '请选择审批结果',
        allowClear: true,
        options: getDictOptions(
          DICT_TYPE.BPM_PROCESS_INSTANCE_STATUS,
          'number',
        ),
      },
    },
    {
      fieldName: 'reason',
      label: `${config.title}原因`,
      component: 'Input',
      componentProps: {
        placeholder: `请输入${config.title}原因`,
        allowClear: true,
      },
    },
  ];
}

function useGridColumns(
  config: OAModuleViewConfig,
): VxeTableGridOptions['columns'] {
  if (config.key === 'overtime') {
    return [
      { field: 'id', title: '申请编号', minWidth: 100 },
      {
        field: 'status',
        title: '状态',
        minWidth: 100,
        cellRender: {
          name: 'CellDict',
          props: { type: DICT_TYPE.BPM_PROCESS_INSTANCE_STATUS },
        },
      },
      { field: 'workDate', title: '加班日期', minWidth: 140, formatter: 'formatDate' },
      { field: 'durationHours', title: '时长(小时)', minWidth: 120 },
      { field: 'projectName', title: '关联项目', minWidth: 160 },
      {
        field: 'type',
        title: `${config.title}类型`,
        minWidth: 120,
        formatter: ({ cellValue }: any) =>
          getDictLabel(config.dictType, cellValue) || getFallbackTypeLabel(config, cellValue),
      },
      { field: 'reason', title: '申请说明', minWidth: 180 },
      { field: 'createTime', title: '申请时间', minWidth: 180, formatter: 'formatDateTime' },
      { title: '操作', width: 240, fixed: 'right', slots: { default: 'actions' } },
    ];
  }

  if (config.key === 'outing') {
    return [
      { field: 'id', title: '申请编号', minWidth: 100 },
      {
        field: 'status',
        title: '状态',
        minWidth: 100,
        cellRender: {
          name: 'CellDict',
          props: { type: DICT_TYPE.BPM_PROCESS_INSTANCE_STATUS },
        },
      },
      { field: 'outingDate', title: '外出日期', minWidth: 140, formatter: 'formatDate' },
      { field: 'durationHours', title: '时长(小时)', minWidth: 120 },
      { field: 'destination', title: '外出地点', minWidth: 180 },
      {
        field: 'type',
        title: `${config.title}类型`,
        minWidth: 120,
        formatter: ({ cellValue }: any) =>
          getDictLabel(config.dictType, cellValue) || getFallbackTypeLabel(config, cellValue),
      },
      { field: 'reason', title: `${config.title}原因`, minWidth: 180 },
      { field: 'createTime', title: '申请时间', minWidth: 180, formatter: 'formatDateTime' },
      { title: '操作', width: 240, fixed: 'right', slots: { default: 'actions' } },
    ];
  }

  return [
    {
      field: 'id',
      title: '申请编号',
      minWidth: 100,
    },
    {
      field: 'status',
      title: '状态',
      minWidth: 100,
      cellRender: {
        name: 'CellDict',
        props: { type: DICT_TYPE.BPM_PROCESS_INSTANCE_STATUS },
      },
    },
    {
      field: 'startTime',
      title: '开始时间',
      minWidth: 180,
      formatter: 'formatDate',
    },
    {
      field: 'endTime',
      title: '结束时间',
      minWidth: 180,
      formatter: 'formatDate',
    },
    {
      field: 'type',
      title: `${config.title}类型`,
      minWidth: 120,
      cellRender: {
        name: 'CellDict',
        props: { type: config.dictType },
      },
    },
    {
      field: 'reason',
      title: `${config.title}原因`,
      minWidth: 150,
    },
    {
      field: 'createTime',
      title: '申请时间',
      minWidth: 180,
      formatter: 'formatDateTime',
    },
    {
      title: '操作',
      width: 240,
      fixed: 'right',
      slots: { default: 'actions' },
    },
  ];
}

function useDetailFormSchema(
  config: OAModuleViewConfig,
): DescriptionItemSchema[] {
  if (config.key === 'overtime') {
    return [
      {
        label: `${config.title}类型`,
        field: 'type',
        render: (val) =>
          val === undefined || val === null
            ? '-'
            : getDictLabel(config.dictType, val) || getFallbackTypeLabel(config, val),
      },
      { label: '加班日期', field: 'workDate', render: formatFlowFormDate },
      { label: '开始时间', field: 'startTime', render: formatFlowFormDateTime },
      { label: '结束时间', field: 'endTime', render: formatFlowFormDateTime },
      { label: '加班时长（小时）', field: 'durationHours' },
      { label: '加班地点', field: 'workLocation' },
      { label: '关联项目', field: 'projectName' },
      {
        label: '补偿方式',
        field: 'compensationType',
        render: (val) =>
          compensationTypeOptions.find((item) => item.value === val)?.label || '-',
      },
      { label: '加班内容', field: 'workContent' },
      { label: '申请说明', field: 'reason' },
      { label: '备注', field: 'remark' },
    ];
  }

  if (config.key === 'outing') {
    return [
      {
        label: `${config.title}类型`,
        field: 'type',
        render: (val) =>
          val === undefined || val === null
            ? '-'
            : getDictLabel(config.dictType, val) || getFallbackTypeLabel(config, val),
      },
      { label: '外出日期', field: 'outingDate', render: formatFlowFormDate },
      { label: '开始时间', field: 'startTime', render: formatFlowFormDateTime },
      { label: '结束时间', field: 'endTime', render: formatFlowFormDateTime },
      { label: '外出时长（小时）', field: 'durationHours' },
      { label: '外出地点', field: 'destination' },
      {
        label: '外出范围',
        field: 'outsideOffice',
        render: (val) => (val ? '离院外出' : '院内外出'),
      },
      { label: '联系电话', field: 'contactMobile' },
      { label: '同行人员', field: 'companionNames' },
      { label: `${config.title}原因`, field: 'reason' },
      { label: '备注', field: 'remark' },
    ];
  }

  return [
    {
      label: `${config.title}类型`,
      field: 'type',
      render: (val) =>
        val === undefined || val === null
          ? '-'
          : getDictLabel(config.dictType, val) || getFallbackTypeLabel(config, val),
    },
    {
      label: '开始时间',
      field: 'startTime',
      render: formatFlowFormDateTime,
    },
    {
      label: '结束时间',
      field: 'endTime',
      render: formatFlowFormDateTime,
    },
    {
      label: `${config.title}原因`,
      field: 'reason',
    },
  ];
}

function getTypeOptions(config: OAModuleViewConfig) {
  const dictOptions = getDictOptions(config.dictType, 'number');
  return dictOptions.length > 0 ? dictOptions : (config.fallbackTypeOptions ?? []);
}

export {
  useDetailFormSchema,
  useFormSchema,
  useGridColumns,
  useGridFormSchema,
};
