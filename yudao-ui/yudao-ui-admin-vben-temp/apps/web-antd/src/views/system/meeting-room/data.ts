import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';

import { CommonStatusEnum, DICT_TYPE } from '@vben/constants';
import { getDictOptions } from '@vben/hooks';

import { z } from '#/adapter/form';

export function useFormSchema(): VbenFormSchema[] {
  return [
    {
      component: 'Input',
      fieldName: 'id',
      dependencies: {
        triggerFields: [''],
        show: () => false,
      },
    },
    {
      fieldName: 'name',
      label: '会议室名称',
      component: 'Input',
      componentProps: {
        placeholder: '请输入会议室名称',
      },
      rules: 'required',
    },
    {
      fieldName: 'location',
      label: '所在位置',
      component: 'Input',
      componentProps: {
        placeholder: '请输入所在位置',
      },
      rules: 'required',
    },
    {
      fieldName: 'capacity',
      label: '容纳人数',
      component: 'InputNumber',
      componentProps: {
        min: 1,
        placeholder: '请输入容纳人数',
      },
      rules: 'required',
    },
    {
      fieldName: 'equipment',
      label: '设备配置',
      component: 'CheckboxGroup',
      componentProps: {
        options: getDictOptions(DICT_TYPE.SYSTEM_MEETING_ROOM_EQUIPMENT, 'string'),
      },
      modelPropName: 'modelValue',
    },
    {
      fieldName: 'sort',
      label: '排序号',
      component: 'InputNumber',
      componentProps: {
        min: 0,
        placeholder: '请输入排序号',
      },
      rules: 'required',
    },
    {
      fieldName: 'status',
      label: '状态',
      component: 'RadioGroup',
      componentProps: {
        options: getDictOptions(DICT_TYPE.COMMON_STATUS, 'number'),
        buttonStyle: 'solid',
        optionType: 'button',
      },
      rules: z.number().default(CommonStatusEnum.ENABLE),
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

export function useGridFormSchema(): VbenFormSchema[] {
  return [
    {
      fieldName: 'name',
      label: '会议室名称',
      component: 'Input',
      componentProps: {
        placeholder: '请输入会议室名称',
        allowClear: true,
      },
    },
    {
      fieldName: 'location',
      label: '所在位置',
      component: 'Input',
      componentProps: {
        placeholder: '请输入所在位置',
        allowClear: true,
      },
    },
    {
      fieldName: 'status',
      label: '状态',
      component: 'Select',
      componentProps: {
        options: getDictOptions(DICT_TYPE.COMMON_STATUS, 'number'),
        placeholder: '请选择状态',
        allowClear: true,
      },
    },
  ];
}

export function useGridColumns(): VxeTableGridOptions['columns'] {
  return [
    {
      field: 'id',
      title: '编号',
      minWidth: 100,
    },
    {
      field: 'name',
      title: '会议室名称',
      minWidth: 180,
    },
    {
      field: 'location',
      title: '所在位置',
      minWidth: 180,
    },
    {
      field: 'capacity',
      title: '容纳人数',
      minWidth: 100,
    },
    {
      field: 'equipment',
      title: '设备配置',
      minWidth: 220,
      formatter: ({ cellValue }: { cellValue?: string[] | string }) =>
        Array.isArray(cellValue) ? cellValue.join(', ') : cellValue || '-',
    },
    {
      field: 'sort',
      title: '排序号',
      minWidth: 100,
    },
    {
      field: 'status',
      title: '状态',
      minWidth: 100,
      cellRender: {
        name: 'CellDict',
        props: { type: DICT_TYPE.COMMON_STATUS },
      },
    },
    {
      field: 'createTime',
      title: '创建时间',
      minWidth: 180,
      formatter: 'formatDateTime',
    },
    {
      title: '操作',
      width: 140,
      fixed: 'right',
      slots: { default: 'actions' },
    },
  ];
}
