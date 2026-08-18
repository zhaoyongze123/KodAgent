<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemNotifyMessageApi } from '#/api/system/notify/message';

import { DocAlert, Page, useVbenModal } from '@vben/common-ui';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getNotifyMessagePage } from '#/api/system/notify/message';
import { $t } from '#/locales';

import { useGridColumns, useGridFormSchema } from './data';
import Detail from './modules/detail.vue';

const [DetailModal, detailModalApi] = useVbenModal({
  connectedComponent: Detail,
  destroyOnClose: true,
});

/** 刷新表格 */
function handleRefresh() {
  gridApi.query();
}

/** 查看站内信详情 */
function handleDetail(row: SystemNotifyMessageApi.NotifyMessage) {
  detailModalApi.setData(row).open();
}

const [Grid, gridApi] = useVbenVxeGrid({
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
          return await getNotifyMessagePage({
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
  } as VxeTableGridOptions<SystemNotifyMessageApi.NotifyMessage>,
});
</script>

<template>
  <Page auto-content-height title="站内信总览">
    <template #doc>
      <DocAlert title="站内信" url="https://doc.iocoder.cn/notify/" />
    </template>

    <DetailModal @success="handleRefresh" />
    <div class="oa-workspace-page">

      <section class="oa-workspace-panel min-h-0">
        <div class="oa-workspace-panel-header">
          <div>
            <h3 class="oa-workspace-panel-title">站内信列表</h3>
          </div>
        </div>
        <div class="oa-workspace-panel-body min-h-0">
          <Grid table-title="站内信列表">
            <template #actions="{ row }">
              <TableAction
                :actions="[
                  {
                    label: $t('common.detail'),
                    type: 'link',
                    icon: ACTION_ICON.VIEW,
                    auth: ['system:notify-message:query'],
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
