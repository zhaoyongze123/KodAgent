<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { BpmCategoryApi } from '#/api/bpm/category';

import { Page, useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { deleteCategory, getCategoryPage } from '#/api/bpm/category';
import { $t } from '#/locales';

import { useGridColumns, useGridFormSchema } from './data';
import Form from './modules/form.vue';

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: Form,
  destroyOnClose: true,
});

/** 刷新表格 */
function handleRefresh() {
  gridApi.query();
}

/** 创建流程分类 */
function handleCreate() {
  formModalApi.setData(null).open();
}

/** 编辑流程分类 */
function handleEdit(row: BpmCategoryApi.Category) {
  formModalApi.setData(row).open();
}

/** 删除流程分类 */
async function handleDelete(row: BpmCategoryApi.Category) {
  const hideLoading = message.loading({
    content: $t('ui.actionMessage.deleting', [row.name]),
    duration: 0,
  });
  try {
    await deleteCategory(row.id as number);
    message.success($t('ui.actionMessage.deleteSuccess', [row.name]));
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
          return await getCategoryPage({
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
  } as VxeTableGridOptions<BpmCategoryApi.Category>,
});
</script>

<template>
  <Page auto-content-height title="流程分类">
    <FormModal @success="handleRefresh" />
    <div class="oa-workspace-page oa-category-page">
      <section class="oa-workspace-panel min-h-0">
        <div class="oa-workspace-panel-body min-h-0">
          <Grid>
            <template #toolbar-tools>
              <TableAction
                :actions="[
                  {
                    label: $t('ui.actionTitle.create', ['流程分类']),
                    type: 'primary',
                    icon: ACTION_ICON.ADD,
                    auth: ['bpm:category:create'],
                    onClick: handleCreate,
                  },
                ]"
              />
            </template>
            <template #actions="{ row }">
              <TableAction
                :actions="[
                  {
                    label: $t('common.edit'),
                    type: 'link',
                    icon: ACTION_ICON.EDIT,
                    auth: ['bpm:category:update'],
                    onClick: handleEdit.bind(null, row),
                  },
                  {
                    label: $t('common.delete'),
                    type: 'link',
                    danger: true,
                    icon: ACTION_ICON.DELETE,
                    auth: ['bpm:category:delete'],
                    popConfirm: {
                      title: $t('ui.actionMessage.deleteConfirm', [row.name]),
                      confirm: handleDelete.bind(null, row),
                    },
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
.oa-category-page :deep(.oa-workspace-panel-body) {
  padding-top: 8px;
}

.oa-category-page :deep(.vxe-grid--form-wrapper) {
  padding-bottom: 4px;
}

.oa-category-page :deep(.vxe-grid--toolbar-wrapper) {
  padding-bottom: 4px;
}

.oa-category-page :deep(.vxe-table--body-wrapper) {
  min-height: calc(100vh - 456px);
  max-height: calc(100vh - 456px);
}

.oa-category-page :deep(.vxe-table--header-wrapper),
.oa-category-page :deep(.vxe-table--body-wrapper) {
  font-size: 13px;
}

.oa-category-page :deep(.vxe-body--column),
.oa-category-page :deep(.vxe-header--column) {
  padding-inline: 10px;
}

.oa-category-page :deep(.vxe-pager) {
  padding-top: 4px;
}

@media (max-width: 1440px) {
  .oa-category-page :deep(.vxe-toolbar) {
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 0 8px;
  }

  .oa-category-page :deep(.vxe-buttons--wrapper),
  .oa-category-page :deep(.vxe-tools--wrapper),
  .oa-category-page :deep(.vxe-tools--operate) {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0;
    padding: 0;
  }

  .oa-category-page :deep(.vben-form) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .oa-category-page :deep(.vxe-table--body-wrapper) {
    min-height: calc(100vh - 492px);
    max-height: calc(100vh - 492px);
  }

  .oa-category-page :deep(.vxe-pager--wrapper) {
    flex-wrap: wrap;
    gap: 10px 14px;
    justify-content: flex-end;
  }
}

@media (max-width: 1320px) {
  .oa-category-page :deep(.vben-form) {
    grid-template-columns: 1fr;
  }

  .oa-category-page :deep(.vxe-table--body-wrapper) {
    min-height: calc(100vh - 548px);
    max-height: calc(100vh - 548px);
  }
}
</style>
