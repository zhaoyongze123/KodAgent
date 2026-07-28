<script lang="ts" setup>
import type { formCreate } from '@form-create/antd-designer';

import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { BpmTaskApi } from '#/api/bpm/task';

import { nextTick, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { DICT_TYPE } from '@vben/constants';
import { IconifyIcon } from '@vben/icons';

import { Button } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getTaskListByProcessInstanceId } from '#/api/bpm/task';
import { setConfAndFields2 } from '#/components/form-create';

defineOptions({
  name: 'BpmProcessInstanceTaskList',
});

const props = defineProps<{
  id: string;
  loading: boolean;
}>();

/** 表单类型定义 */
interface TaskForm {
  rule: any[];
  option: Record<string, any>;
  value: Record<string, any>;
}

/** 获取表格列配置 */
function useGridColumns(): VxeTableGridOptions['columns'] {
  return [
    {
      field: 'name',
      title: '审批节点',
      minWidth: 150,
    },
    {
      field: 'approver',
      title: '审批人',
      slots: {
        default: ({ row }: { row: BpmTaskApi.Task }) => {
          return row.assigneeUser?.nickname || row.ownerUser?.nickname;
        },
      },
      minWidth: 180,
    },
    {
      field: 'createTime',
      title: '开始时间',
      formatter: 'formatDateTime',
      minWidth: 180,
    },
    {
      field: 'endTime',
      title: '结束时间',
      formatter: 'formatDateTime',
      minWidth: 180,
    },
    {
      field: 'status',
      title: '审批状态',
      minWidth: 150,
      cellRender: {
        name: 'CellDict',
        props: { type: DICT_TYPE.BPM_TASK_STATUS },
      },
    },
    {
      field: 'reason',
      title: '审批建议',
      slots: {
        default: 'slot-reason',
      },
      minWidth: 200,
    },
    {
      field: 'durationInMillis',
      title: '耗时',
      minWidth: 180,
      formatter: 'formatPast2',
    },
  ];
}

const formRef = ref<formCreate>();
const taskForm = ref<TaskForm>({
  rule: [],
  option: {},
  value: {},
});

const [Modal, modalApi] = useVbenModal({
  title: '查看表单',
  footer: false,
});

/** 刷新表格 */
function handleRefresh() {
  gridApi.query();
}

/** 显示表单详情 */
async function handleShowFormDetail(row: BpmTaskApi.Task) {
  // 设置表单配置和表单字段
  taskForm.value = {
    rule: [],
    option: {},
    value: row,
  };
  setConfAndFields2(
    taskForm,
    row.formConf,
    row.formFields || [],
    row.formVariables || {},
  );

  // 打开弹窗
  modalApi.open();
  // 等待表单渲染
  await nextTick();
  // 获取表单 API 实例
  const formApi = formRef.value?.fapi;
  if (!formApi) {
    return;
  }
  // 设置表单不可编辑
  formApi.btn.show(false);
  formApi.resetBtn.show(false);
  formApi.disabled(true);
}

const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: {
    columns: useGridColumns(),
    keepSource: true,
    showFooter: false,
    border: true,
    proxyConfig: {
      ajax: {
        query: async () => {
          return await getTaskListByProcessInstanceId(props.id);
        },
      },
    },
    rowConfig: {
      keyField: 'id',
      isHover: true,
    },
    pagerConfig: {
      enabled: false,
    },
    toolbarConfig: {
      enabled: false,
    },
  } as VxeTableGridOptions<BpmTaskApi.Task>,
});

defineExpose({
  refresh: handleRefresh,
});
</script>

<template>
  <div class="oa-process-records">
    <div class="oa-process-records-head">
      <div>
        <div class="oa-process-records-title">审批记录</div>
      </div>
    </div>
    <Grid>
      <template #slot-reason="{ row }">
        <div class="oa-process-records-reason">
          <span v-if="row.reason">{{ row.reason }}</span>
          <span v-else>-</span>
          <Button
            v-if="row.formId > 0"
            type="primary"
            size="small"
            ghost
            class="oa-process-records-form-button"
            @click="handleShowFormDetail(row)"
          >
            <IconifyIcon icon="lucide:file-text" />
            <span class="!ml-0.5 text-xs">查看表单</span>
          </Button>
        </div>
      </template>
    </Grid>
  </div>
  <Modal class="w-3/5">
    <form-create
      ref="formRef"
      v-model="taskForm.value"
      :option="taskForm.option"
      :rule="taskForm.rule"
    />
  </Modal>
</template>

<style scoped>
.oa-process-records {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.oa-process-records-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.oa-process-records-title {
  margin-top: 0;
  color: var(--oa-ink);
  font-size: 18px;
  font-weight: 600;
}

.oa-process-records-reason {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.oa-process-records-form-button {
  margin-left: 0 !important;
}

/* 表头、表体、底部由 VXE 分成多个滚动容器，只保留表体底部的横向滚动条。 */
.oa-process-records :deep(.vxe-table--header-wrapper),
.oa-process-records :deep(.vxe-table--footer-wrapper),
.oa-process-records :deep(.vxe-table--fixed-left-body-wrapper),
.oa-process-records :deep(.vxe-table--fixed-right-body-wrapper) {
  overflow-x: hidden !important;
  scrollbar-width: none;
}

.oa-process-records :deep(.vxe-table--header-wrapper::-webkit-scrollbar),
.oa-process-records :deep(.vxe-table--footer-wrapper::-webkit-scrollbar),
.oa-process-records :deep(.vxe-table--fixed-left-body-wrapper::-webkit-scrollbar),
.oa-process-records :deep(.vxe-table--fixed-right-body-wrapper::-webkit-scrollbar) {
  display: none;
  height: 0;
}
</style>
