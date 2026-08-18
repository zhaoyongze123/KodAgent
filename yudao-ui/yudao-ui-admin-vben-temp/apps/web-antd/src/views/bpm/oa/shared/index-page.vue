<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { BpmOACommonApi, OAModuleApiKey } from '#/api/bpm/oa/common';

import { h, onActivated } from 'vue';

import { DocAlert, Page, prompt } from '@vben/common-ui';
import { BpmProcessInstanceStatus } from '@vben/constants';

import { message, Textarea } from 'ant-design-vue';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { cancelProcessInstanceByStartUser } from '#/api/bpm/processInstance';
import { $t } from '#/locales';
import { router } from '#/router';

import { getOAModuleViewConfig } from './config';
import { useGridColumns, useGridFormSchema } from './data';

const props = defineProps<{
  fetchPage: (params: any) => Promise<any>;
  moduleKey: OAModuleApiKey;
}>();

const config = getOAModuleViewConfig(props.moduleKey);

function handleRefresh() {
  gridApi.query();
}

function handleCreate() {
  router.push({
    name: config.routeNames.create,
  });
}

function handleReCreate(row: BpmOACommonApi.OARecord) {
  router.push({
    name: config.routeNames.create,
    query: {
      id: row.id,
    },
  });
}

function handleCancel(row: BpmOACommonApi.OARecord) {
  prompt({
    title: '取消流程',
    content: '请输入取消原因',
    modelPropName: 'value',
    component: () =>
      h(Textarea, {
        placeholder: '请输入取消原因',
        allowClear: true,
        rows: 2,
        rules: [{ required: true, message: '请输入取消原因' }],
      }),
    async beforeClose(scope) {
      if (!scope.isConfirm) {
        return;
      }
      if (!scope.value) {
        message.error('请输入取消原因');
        return false;
      }
      const hideLoading = message.loading({
        content: '正在取消中...',
        duration: 0,
      });
      try {
        await cancelProcessInstanceByStartUser(Number(row.id), scope.value);
        message.success('取消成功');
        handleRefresh();
      } catch {
        return false;
      } finally {
        hideLoading();
      }
    },
  });
}

function handleDetail(row: BpmOACommonApi.OARecord) {
  router.push({
    name: config.routeNames.detail,
    query: { id: row.id },
  });
}

function handleProgress(row: BpmOACommonApi.OARecord) {
  router.push({
    name: 'BpmProcessInstanceDetail',
    query: { id: row.processInstanceId },
  });
}

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    schema: useGridFormSchema(config),
  },
  gridOptions: {
    columns: useGridColumns(config),
    height: 'auto',
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) =>
          await props.fetchPage({
            pageNo: page.currentPage,
            pageSize: page.pageSize,
            ...formValues,
          }),
      },
    },
    rowConfig: {
      keyField: 'id',
      isHover: true,
    },
    toolbarConfig: {
      refresh: true,
      search: true,
    },
  } as VxeTableGridOptions<BpmOACommonApi.OARecord>,
});

onActivated(() => {
  handleRefresh();
});
</script>

<template>
  <Page auto-content-height>
    <template #doc>
      <DocAlert
        title="审批接入（业务表单）"
        url="https://doc.iocoder.cn/bpm/use-business-form/"
      />
    </template>

    <Grid :table-title="`${config.title}列表`">
      <template #toolbar-tools>
        <TableAction
          :actions="[
            {
              label: `发起${config.title}`,
              type: 'primary',
              icon: ACTION_ICON.ADD,
              onClick: handleCreate,
            },
          ]"
        />
      </template>
      <template #actions="{ row }">
        <TableAction
          :actions="[
            {
              label: $t('common.detail'),
              type: 'link',
              icon: ACTION_ICON.VIEW,
              onClick: handleDetail.bind(null, row),
            },
            {
              label: '审批进度',
              type: 'link',
              icon: ACTION_ICON.VIEW,
              onClick: handleProgress.bind(null, row),
            },
            {
              label: '取消',
              type: 'link',
              danger: true,
              icon: ACTION_ICON.DELETE,
              ifShow: row.status === BpmProcessInstanceStatus.RUNNING,
              onClick: handleCancel.bind(null, row),
            },
            {
              label: '重新发起',
              type: 'link',
              icon: ACTION_ICON.ADD,
              ifShow: row.status !== BpmProcessInstanceStatus.RUNNING,
              onClick: handleReCreate.bind(null, row),
            },
          ]"
        />
      </template>
    </Grid>
  </Page>
</template>
