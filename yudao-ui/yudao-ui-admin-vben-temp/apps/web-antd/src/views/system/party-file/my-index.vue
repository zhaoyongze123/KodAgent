<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemPartyFileApi } from '#/api/system/party-file';

import { Page, useVbenModal } from '@vben/common-ui';
import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getMyPartyFilePage } from '#/api/system/party-file';

import { useMyPartyFileColumns, useMyPartyFileSearchSchema } from './data';
import FileDetail from './modules/file-detail.vue';

const [DetailModal, detailModalApi] = useVbenModal({
  connectedComponent: FileDetail,
  destroyOnClose: true,
});

function handleDetail(row: SystemPartyFileApi.PartyFile) {
  detailModalApi.setData({ id: row.id, mine: true }).open();
}

const [Grid] = useVbenVxeGrid({
  formOptions: {
    schema: useMyPartyFileSearchSchema(),
  },
  gridOptions: {
    columns: useMyPartyFileColumns(),
    height: 'auto',
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) =>
          await getMyPartyFilePage({
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
  } as VxeTableGridOptions<SystemPartyFileApi.PartyFile>,
});
</script>

<template>
  <Page title="我的党务文件">
    <DetailModal />
    <div class="party-file-page">
      <Grid table-title="我的党务文件">
        <template #actions="{ row }">
          <TableAction
            :actions="[
              {
                label: '查看',
                type: 'link',
                onClick: handleDetail.bind(null, row),
              },
            ]"
          />
        </template>
      </Grid>
    </div>
  </Page>
</template>

<style scoped>
.party-file-page :deep(.vxe-grid) {
  min-height: 1020px;
}
</style>
