<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';

import { DocAlert, Page } from '@vben/common-ui';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getProcessInstanceCopyPage } from '#/api/bpm/processInstance';
import { $t } from '#/locales';
import { router } from '#/router';

import { useGridColumns, useGridFormSchema } from './data';

defineOptions({ name: 'BpmCopyTask' });

/** 任务详情 */
function handleDetail(row: BpmProcessInstanceApi.ProcessInstanceCopyRespVO) {
  const query = {
    id: row.processInstanceId,
    ...(row.activityId && { activityId: row.activityId }),
  };
  router.push({
    name: 'BpmProcessInstanceDetail',
    query,
  });
}

const [Grid] = useVbenVxeGrid({
  formOptions: {
    schema: useGridFormSchema(),
  },
  gridOptions: {
    columns: useGridColumns(),
    height: 'auto',
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) => {
          return await getProcessInstanceCopyPage({
            pageNo: page.currentPage,
            pageSize: page.pageSize,
            ...formValues,
          });
        },
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
  } as VxeTableGridOptions<BpmProcessInstanceApi.ProcessInstanceCopyRespVO>,
});
</script>

<template>
  <Page auto-content-height title="抄送任务">
    <template #doc>
      <DocAlert
        title="审批转办、委派、抄送"
        url="https://doc.iocoder.cn/bpm/task-delegation-and-cc/"
      />
    </template>

    <div class="oa-workspace-page">

      <section class="oa-workspace-panel min-h-0">
        <div class="oa-workspace-panel-header">
          <div>
            <h3 class="oa-workspace-panel-title">抄送任务</h3>
          </div>
        </div>
        <div class="oa-workspace-panel-body min-h-0">
          <Grid table-title="抄送任务">
            <template #actions="{ row }">
              <TableAction
                :actions="[
                  {
                    label: $t('common.detail'),
                    type: 'link',
                    icon: ACTION_ICON.VIEW,
                    auth: ['bpm:task:query'],
                    onClick: handleDetail.bind(null, row),
                  },
                ]"
              />
            </template>
          </Grid>
        </div>
      </section>
    </div>
  </Page>
</template>
