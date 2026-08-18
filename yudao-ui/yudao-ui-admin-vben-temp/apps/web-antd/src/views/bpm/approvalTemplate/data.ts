import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { BpmProcessDefinitionApi } from '#/api/bpm/definition';

import { DICT_TYPE } from '@vben/constants';

import { getRangePickerDefaultProps } from '#/utils';

/** 编辑表单 */
export function useFormSchema(): VbenFormSchema[] {
  return [
    {
      fieldName: 'id',
      component: 'Input',
      dependencies: {
        triggerFields: [''],
        show: () => false,
      },
    },
    {
      fieldName: 'name',
      label: '模板名称',
      component: 'Input',
      componentProps: {
        placeholder: '请输入模板名称',
      },
      rules: 'required',
    },
    {
      fieldName: 'processDefinitionId',
      label: '绑定流程',
      component: 'Select',
      componentProps: {
        allowClear: false,
        options: [],
        placeholder: '请选择流程定义',
        showSearch: true,
        optionFilterProp: 'label',
      },
      rules: 'required',
    },
    {
      fieldName: 'description',
      label: '模板描述',
      component: 'Textarea',
      componentProps: {
        placeholder: '请输入模板描述',
        rows: 3,
      },
    },
    {
      fieldName: 'icon',
      label: '模板图标',
      component: 'ImageUpload',
      componentProps: {
        helpText: '支持本地上传 PNG、JPG、SVG、WEBP，建议使用方形图标',
        maxNumber: 1,
        maxSize: 2,
      },
    },
    {
      fieldName: 'visible',
      label: '发起展示',
      component: 'Switch',
      componentProps: {
        checkedChildren: '上架',
        unCheckedChildren: '下架',
      },
      rules: 'required',
    },
    {
      fieldName: 'sort',
      label: '模板排序',
      component: 'InputNumber',
      componentProps: {
        min: 0,
        placeholder: '请输入模板排序',
      },
      rules: 'required',
    },
  ];
}

/** 查询表单 */
export function useGridFormSchema(): VbenFormSchema[] {
  return [
    {
      fieldName: 'name',
      label: '模板名称',
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请输入模板名称',
      },
    },
    {
      fieldName: 'processDefinitionKey',
      label: '流程标识',
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请输入流程标识',
      },
    },
    {
      fieldName: 'category',
      label: '流程分类',
      component: 'Input',
      componentProps: {
        allowClear: true,
        placeholder: '请输入流程分类编码',
      },
    },
    {
      fieldName: 'visible',
      label: '发起展示',
      component: 'Select',
      componentProps: {
        allowClear: true,
        options: [
          { label: '上架中', value: true },
          { label: '已下架', value: false },
        ],
        placeholder: '请选择发起展示状态',
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
  ];
}

/** 列字段 */
export function useGridColumns(): VxeTableGridOptions['columns'] {
  return [
    {
      field: 'id',
      title: '模板编号',
      width: 96,
    },
    {
      field: 'name',
      title: '模板名称',
      minWidth: 160,
    },
    {
      field: 'icon',
      title: '图标',
      minWidth: 100,
      slots: { default: 'icon' },
    },
    {
      field: 'processDefinitionName',
      title: '绑定流程定义',
      minWidth: 180,
    },
    {
      field: 'processDefinitionKey',
      title: '流程标识',
      minWidth: 150,
    },
    {
      field: 'modelId',
      title: '流程模型编号',
      minWidth: 180,
    },
    {
      field: 'categoryName',
      title: '流程分类',
      minWidth: 120,
    },
    {
      field: 'visible',
      title: '发起展示',
      width: 110,
      slots: { default: 'visible' },
    },
    {
      field: 'modelType',
      title: '流程类型',
      width: 120,
      cellRender: {
        name: 'CellDict',
        props: { type: DICT_TYPE.BPM_MODEL_TYPE },
      },
    },
    {
      field: 'suspensionState',
      title: '运行状态',
      width: 110,
      slots: { default: 'suspensionState' },
    },
    {
      field: 'sort',
      title: '排序',
      width: 90,
    },
    {
      field: 'deploymentTime',
      title: '部署时间',
      width: 172,
      formatter: 'formatDateTime',
    },
    {
      title: '操作',
      width: 210,
      fixed: 'right',
      slots: { default: 'actions' },
    },
  ];
}

export function buildProcessDefinitionOptions(
  list: BpmProcessDefinitionApi.ProcessDefinition[],
) {
  return list.map((item) => ({
    label: `${item.name}（${item.key || item.id}）`,
    value: item.id,
  }));
}
