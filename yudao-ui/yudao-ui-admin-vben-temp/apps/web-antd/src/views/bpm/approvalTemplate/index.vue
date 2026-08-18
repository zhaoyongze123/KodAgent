<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { BpmApprovalTemplateApi } from '#/api/bpm/approvalTemplate';

import { Page, useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { message, Tag } from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getApprovalTemplatePage,
  updateApprovalTemplateVisible,
} from '#/api/bpm/approvalTemplate';

import { useGridColumns, useGridFormSchema } from './data';
import Form from './modules/form.vue';

defineOptions({ name: 'BpmApprovalTemplate' });

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: Form,
  destroyOnClose: true,
});

function handleRefresh() {
  gridApi.query();
}

function handleEdit(row: BpmApprovalTemplateApi.ApprovalTemplate) {
  formModalApi.setData(row).open();
}

function isImageIcon(icon?: string) {
  if (!icon) {
    return false;
  }
  return /^(https?:\/\/|\/|data:)/.test(icon);
}

async function handleToggleVisible(row: BpmApprovalTemplateApi.ApprovalTemplate) {
  const nextVisible = !row.visible;
  const hideLoading = message.loading({
    content: nextVisible
      ? `正在上架模板：${row.name}`
      : `正在下架模板：${row.name}`,
    duration: 0,
  });
  try {
    await updateApprovalTemplateVisible(row.id, nextVisible);
    message.success(nextVisible ? '模板已上架' : '模板已下架');
    handleRefresh();
  } finally {
    hideLoading();
  }
}

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    schema: useGridFormSchema(),
  },
  gridOptions: {
    columns: useGridColumns(),
    height: 'auto',
    keepSource: true,
    pagerConfig: {
      pageSize: 10,
    },
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) => {
          return await getApprovalTemplatePage({
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
  } as VxeTableGridOptions<BpmApprovalTemplateApi.ApprovalTemplate>,
});
</script>

<template>
  <Page auto-content-height title="审批模板管理">
    <FormModal @success="handleRefresh" />
    <div class="oa-workspace-page oa-approval-template-page">
      <section class="oa-workspace-panel min-h-0">
        <div class="oa-workspace-panel-body min-h-0">
          <Grid>
            <template #icon="{ row }">
              <img
                v-if="row.icon && isImageIcon(row.icon)"
                :src="row.icon"
                alt=""
                class="oa-template-icon-image"
              />
              <IconifyIcon
                v-else
                :icon="row.icon || 'solar:document-text-outline'"
                class="oa-template-icon"
              />
            </template>
            <template #visible="{ row }">
              <Tag :color="row.visible ? 'success' : 'default'">
                {{ row.visible ? '上架中' : '已下架' }}
              </Tag>
            </template>
            <template #suspensionState="{ row }">
              <Tag :color="row.suspensionState === 1 ? 'processing' : 'warning'">
                {{ row.suspensionState === 1 ? '运行中' : '已停用' }}
              </Tag>
            </template>
            <template #actions="{ row }">
              <TableAction
                :actions="[
                  {
                    label: '编辑',
                    type: 'link',
                    auth: ['bpm:model:update'],
                    onClick: handleEdit.bind(null, row),
                  },
                  {
                    label: row.visible ? '下架' : '上架',
                    type: 'link',
                    auth: ['bpm:model:update'],
                    onClick: handleToggleVisible.bind(null, row),
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

<style scoped>
.oa-approval-template-page :deep(.oa-workspace-panel-body) {
  padding-top: 8px;
}

.oa-approval-template-page :deep(.vxe-grid--form-wrapper) {
  padding-bottom: 4px;
}

.oa-approval-template-page :deep(.vxe-grid--toolbar-wrapper) {
  padding-bottom: 4px;
}

.oa-approval-template-page :deep(.vxe-table--body-wrapper) {
  min-height: calc(100vh - 472px);
  max-height: calc(100vh - 472px);
}

.oa-template-icon {
  font-size: 20px;
  color: #1565c0;
}

.oa-template-icon-image {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  object-fit: cover;
}
</style>
