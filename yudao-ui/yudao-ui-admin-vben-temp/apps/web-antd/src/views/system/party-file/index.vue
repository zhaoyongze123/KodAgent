<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemPartyFileApi } from '#/api/system/party-file';

import { ref } from 'vue';

import { confirm, Page, useVbenModal } from '@vben/common-ui';
import { isEmpty } from '@vben/utils';
import { message, Tabs } from 'ant-design-vue';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deletePartyFileKodSource,
  deletePartyFile,
  deletePartyFileCategory,
  getPartyFileCategoryList,
  getPartyFileKodSourcePage,
  getPartyFilePage,
} from '#/api/system/party-file';
import { $t } from '#/locales';

import {
  useCategoryColumns,
  useKodSourceColumns,
  useKodSourceSearchSchema,
  usePartyFileColumns,
  usePartyFileSearchSchema,
} from './data';
import CategoryForm from './modules/category-form.vue';
import FileDetail from './modules/file-detail.vue';
import FileForm from './modules/file-form.vue';
import KodSourceForm from './modules/kod-source-form.vue';

const activeTab = ref('file');
const checkedIds = ref<number[]>([]);
const checkedCategoryIds = ref<number[]>([]);

const [CategoryFormModal, categoryFormModalApi] = useVbenModal({
  connectedComponent: CategoryForm,
  destroyOnClose: true,
});
const [FileFormModal, fileFormModalApi] = useVbenModal({
  connectedComponent: FileForm,
  destroyOnClose: true,
});
const [KodSourceFormModal, kodSourceFormModalApi] = useVbenModal({
  connectedComponent: KodSourceForm,
  destroyOnClose: true,
});
const [DetailModal, detailModalApi] = useVbenModal({
  connectedComponent: FileDetail,
  destroyOnClose: true,
});

function handleRefresh() {
  fileGridApi.query();
  categoryGridApi.query();
  kodSourceGridApi.query();
}

function handleCreateCategory() {
  categoryFormModalApi.setData(null).open();
}

function handleAppendCategory(row: SystemPartyFileApi.PartyFileCategory) {
  categoryFormModalApi.setData({ parentId: row.id }).open();
}

function handleEditCategory(row: SystemPartyFileApi.PartyFileCategory) {
  categoryFormModalApi.setData(row).open();
}

async function handleDeleteCategory(row: SystemPartyFileApi.PartyFileCategory) {
  const hideLoading = message.loading({ content: `正在删除 ${row.name}...`, duration: 0 });
  try {
    await deletePartyFileCategory(row.id!);
    message.success(`已删除 ${row.name}`);
    handleRefresh();
  } finally {
    hideLoading();
  }
}

function handleCreateFile() {
  fileFormModalApi.setData(null).open();
}

function handleCreateKodSource() {
  kodSourceFormModalApi.setData(null).open();
}

function handleEditKodSource(row: SystemPartyFileApi.PartyFileKodSource) {
  kodSourceFormModalApi.setData(row).open();
}

async function handleDeleteKodSource(row: SystemPartyFileApi.PartyFileKodSource) {
  const hideLoading = message.loading({ content: `正在删除 ${row.name}...`, duration: 0 });
  try {
    await deletePartyFileKodSource(row.id!);
    message.success(`已删除 ${row.name}`);
    handleRefresh();
  } finally {
    hideLoading();
  }
}

function handleEditFile(row: SystemPartyFileApi.PartyFile) {
  fileFormModalApi.setData(row).open();
}

function handleDetail(row: SystemPartyFileApi.PartyFile) {
  detailModalApi.setData({ id: row.id }).open();
}

async function handleDeleteFile(row: SystemPartyFileApi.PartyFile) {
  const hideLoading = message.loading({ content: `正在删除 ${row.title}...`, duration: 0 });
  try {
    await deletePartyFile(row.id!);
    message.success(`已删除 ${row.title}`);
    handleRefresh();
  } finally {
    hideLoading();
  }
}

async function handleDeleteBatch() {
  await confirm($t('ui.actionMessage.deleteBatchConfirm'));
  const hideLoading = message.loading({ content: $t('ui.actionMessage.deletingBatch'), duration: 0 });
  try {
    await Promise.all(checkedIds.value.map((id) => deletePartyFile(id)));
    checkedIds.value = [];
    message.success($t('ui.actionMessage.deleteSuccess'));
    handleRefresh();
  } finally {
    hideLoading();
  }
}

const [CategoryGrid, categoryGridApi] = useVbenVxeGrid({
  gridOptions: {
    columns: useCategoryColumns(),
    height: 600,
    pagerConfig: { enabled: false },
    proxyConfig: {
      ajax: {
        query: async () => await getPartyFileCategoryList(),
      },
    },
    rowConfig: {
      keyField: 'id',
      isHover: true,
    },
    treeConfig: {
      parentField: 'parentId',
      rowField: 'id',
      transform: true,
      expandAll: true,
      reserve: true,
    },
    toolbarConfig: {
      refresh: true,
    },
  } as VxeTableGridOptions<SystemPartyFileApi.PartyFileCategory>,
  gridEvents: {
    checkboxAll: ({ records }: { records: SystemPartyFileApi.PartyFileCategory[] }) => {
      checkedCategoryIds.value = records.map((item) => item.id!);
    },
    checkboxChange: ({ records }: { records: SystemPartyFileApi.PartyFileCategory[] }) => {
      checkedCategoryIds.value = records.map((item) => item.id!);
    },
  },
});

const [FileGrid, fileGridApi] = useVbenVxeGrid({
  formOptions: {
    schema: usePartyFileSearchSchema(),
  },
  gridOptions: {
    columns: usePartyFileColumns(),
    height: 'auto',
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) =>
          await getPartyFilePage({
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
  gridEvents: {
    checkboxAll: ({ records }: { records: SystemPartyFileApi.PartyFile[] }) => {
      checkedIds.value = records.map((item) => item.id!);
    },
    checkboxChange: ({ records }: { records: SystemPartyFileApi.PartyFile[] }) => {
      checkedIds.value = records.map((item) => item.id!);
    },
  },
});

const [KodSourceGrid, kodSourceGridApi] = useVbenVxeGrid({
  formOptions: {
    schema: useKodSourceSearchSchema(),
  },
  gridOptions: {
    columns: useKodSourceColumns(),
    height: 'auto',
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) =>
          await getPartyFileKodSourcePage({
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
  } as VxeTableGridOptions<SystemPartyFileApi.PartyFileKodSource>,
  gridEvents: {
    checkboxAll: () => {},
    checkboxChange: () => {},
  },
});
</script>

<template>
  <Page title="党务文件">
    <CategoryFormModal @success="handleRefresh" />
    <FileFormModal @success="handleRefresh" />
    <KodSourceFormModal @success="handleRefresh" />
    <DetailModal />
    <div class="party-file-page">
      <Tabs v-model:active-key="activeTab" class="party-file-tabs">
        <Tabs.TabPane key="file" tab="文件管理">
          <div class="party-file-tabpane">
            <FileGrid table-title="党务文件列表">
          <template #toolbar-tools>
            <TableAction
              :actions="[
                {
                  label: $t('ui.actionTitle.create', ['党务文件']),
                  type: 'primary',
                  icon: ACTION_ICON.ADD,
                  auth: ['system:party-file:create'],
                  onClick: handleCreateFile,
                },
                {
                  label: $t('ui.actionTitle.deleteBatch'),
                  type: 'primary',
                  danger: true,
                  icon: ACTION_ICON.DELETE,
                  auth: ['system:party-file:delete'],
                  disabled: isEmpty(checkedIds),
                  onClick: handleDeleteBatch,
                },
              ]"
            />
          </template>
          <template #actions="{ row }">
            <TableAction
              :actions="[
                {
                  label: '详情',
                  type: 'link',
                  auth: ['system:party-file:query'],
                  onClick: handleDetail.bind(null, row),
                },
                {
                  label: $t('common.edit'),
                  type: 'link',
                  icon: ACTION_ICON.EDIT,
                  auth: ['system:party-file:update'],
                  onClick: handleEditFile.bind(null, row),
                },
                {
                  label: $t('common.delete'),
                  type: 'link',
                  danger: true,
                  icon: ACTION_ICON.DELETE,
                  auth: ['system:party-file:delete'],
                  popConfirm: {
                    title: $t('ui.actionMessage.deleteConfirm', [row.title]),
                    confirm: handleDeleteFile.bind(null, row),
                  },
                },
              ]"
            />
          </template>
            </FileGrid>
          </div>
        </Tabs.TabPane>
        <Tabs.TabPane key="category" tab="分类管理">
          <div class="party-file-tabpane">
            <CategoryGrid table-title="党务分类列表">
          <template #toolbar-tools>
            <TableAction
              :actions="[
                {
                  label: $t('ui.actionTitle.create', ['分类']),
                  type: 'primary',
                  icon: ACTION_ICON.ADD,
                  auth: ['system:party-file-category:create'],
                  onClick: handleCreateCategory,
                },
              ]"
            />
          </template>
          <template #actions="{ row }">
            <TableAction
              :actions="[
                {
                  label: '新增下级',
                  type: 'link',
                  icon: ACTION_ICON.ADD,
                  auth: ['system:party-file-category:create'],
                  onClick: handleAppendCategory.bind(null, row),
                },
                {
                  label: $t('common.edit'),
                  type: 'link',
                  icon: ACTION_ICON.EDIT,
                  auth: ['system:party-file-category:update'],
                  onClick: handleEditCategory.bind(null, row),
                },
                {
                  label: $t('common.delete'),
                  type: 'link',
                  danger: true,
                  icon: ACTION_ICON.DELETE,
                  auth: ['system:party-file-category:delete'],
                  popConfirm: {
                    title: $t('ui.actionMessage.deleteConfirm', [row.name]),
                    confirm: handleDeleteCategory.bind(null, row),
                  },
                },
              ]"
            />
          </template>
            </CategoryGrid>
          </div>
        </Tabs.TabPane>
        <Tabs.TabPane key="kod-source" tab="目录来源">
          <div class="party-file-tabpane">
            <KodSourceGrid table-title="可道云目录来源">
              <template #toolbar-tools>
                <TableAction
                  :actions="[
                    {
                      label: $t('ui.actionTitle.create', ['目录来源']),
                      type: 'primary',
                      icon: ACTION_ICON.ADD,
                      auth: ['system:party-file:update'],
                      onClick: handleCreateKodSource,
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
                      auth: ['system:party-file:update'],
                      onClick: handleEditKodSource.bind(null, row),
                    },
                    {
                      label: $t('common.delete'),
                      type: 'link',
                      danger: true,
                      icon: ACTION_ICON.DELETE,
                      auth: ['system:party-file:update'],
                      popConfirm: {
                        title: $t('ui.actionMessage.deleteConfirm', [row.name]),
                        confirm: handleDeleteKodSource.bind(null, row),
                      },
                    },
                  ]"
                />
              </template>
            </KodSourceGrid>
          </div>
        </Tabs.TabPane>
      </Tabs>
    </div>
  </Page>
</template>

<style scoped>
.party-file-page {
  min-height: 0;
}

.party-file-tabs :deep(.ant-tabs-content-holder),
.party-file-tabs :deep(.ant-tabs-content),
.party-file-tabs :deep(.ant-tabs-tabpane) {
  min-height: 0;
}

.party-file-tabpane {
  min-height: 0;
}

.party-file-tabpane :deep(.vxe-grid) {
  min-height: 720px;
}
</style>
