<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { SystemDeptApi } from '#/api/system/dept';
import type { SystemUserApi } from '#/api/system/user';

import { ref } from 'vue';

import { confirm, Page, useVbenModal } from '@vben/common-ui';
import { DICT_TYPE } from '@vben/constants';
import { getDictLabel } from '@vben/hooks';
import { downloadFileFromBlobPart, isEmpty } from '@vben/utils';

import { message } from 'ant-design-vue';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deleteUser,
  deleteUserList,
  exportUser,
  getUserPage,
  updateUserStatus,
} from '#/api/system/user';
import { $t } from '#/locales';

import { useGridColumns, useGridFormSchema } from './data';
import AssignRoleForm from './modules/assign-role-form.vue';
import DeptTree from './modules/dept-tree.vue';
import Form from './modules/form.vue';
import ImportForm from './modules/import-form.vue';
import ResetPasswordForm from './modules/reset-password-form.vue';

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: Form,
  destroyOnClose: true,
});

const [ResetPasswordModal, resetPasswordModalApi] = useVbenModal({
  connectedComponent: ResetPasswordForm,
  destroyOnClose: true,
});

const [AssignRoleModal, assignRoleModalApi] = useVbenModal({
  connectedComponent: AssignRoleForm,
  destroyOnClose: true,
});

const [ImportModal, importModalApi] = useVbenModal({
  connectedComponent: ImportForm,
  destroyOnClose: true,
});

/** 刷新表格 */
function handleRefresh() {
  gridApi.query();
}

/** 导出表格 */
async function handleExport() {
  const data = await exportUser(await gridApi.formApi.getValues());
  downloadFileFromBlobPart({ fileName: '用户.xls', source: data });
}

/** 选择部门 */
const searchDeptId = ref<number | undefined>(undefined);
async function handleDeptSelect(dept: SystemDeptApi.Dept) {
  searchDeptId.value = dept.id;
  handleRefresh();
}

/** 创建用户 */
function handleCreate() {
  formModalApi.setData(null).open();
}

/** 导入用户 */
function handleImport() {
  importModalApi.open();
}

/** 编辑用户 */
function handleEdit(row: SystemUserApi.User) {
  formModalApi.setData(row).open();
}

/** 删除用户 */
async function handleDelete(row: SystemUserApi.User) {
  const hideLoading = message.loading({
    content: $t('ui.actionMessage.deleting', [row.username]),
    duration: 0,
  });
  try {
    await deleteUser(row.id!);
    message.success($t('ui.actionMessage.deleteSuccess', [row.username]));
    handleRefresh();
  } finally {
    hideLoading();
  }
}

/** 批量删除用户 */
async function handleDeleteBatch() {
  await confirm($t('ui.actionMessage.deleteBatchConfirm'));
  const hideLoading = message.loading({
    content: $t('ui.actionMessage.deletingBatch'),
    duration: 0,
  });
  try {
    await deleteUserList(checkedIds.value);
    checkedIds.value = [];
    message.success($t('ui.actionMessage.deleteSuccess'));
    handleRefresh();
  } finally {
    hideLoading();
  }
}

const checkedIds = ref<number[]>([]);
function handleRowCheckboxChange({
  records,
}: {
  records: SystemUserApi.User[];
}) {
  checkedIds.value = records.map((item) => item.id!);
}

/** 重置密码 */
function handleResetPassword(row: SystemUserApi.User) {
  resetPasswordModalApi.setData(row).open();
}

/** 分配角色 */
function handleAssignRole(row: SystemUserApi.User) {
  assignRoleModalApi.setData(row).open();
}

/** 更新用户状态 */
async function handleStatusChange(
  newStatus: number,
  row: SystemUserApi.User,
): Promise<boolean | undefined> {
  return new Promise((resolve, reject) => {
    confirm({
      content: `你要将${row.username}的状态切换为【${getDictLabel(DICT_TYPE.COMMON_STATUS, newStatus)}】吗？`,
    })
      .then(async () => {
        // 更新用户状态
        await updateUserStatus(row.id!, newStatus);
        // 提示并返回成功
        message.success($t('ui.actionMessage.operationSuccess'));
        resolve(true);
      })
      .catch(() => {
        reject(new Error('取消操作'));
      });
  });
}

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    schema: useGridFormSchema(),
  },
  gridOptions: {
    columns: useGridColumns(handleStatusChange),
    height: 'auto',
    keepSource: true,
    pagerConfig: {
      pageSize: 10,
    },
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) => {
          return await getUserPage({
            pageNo: page.currentPage,
            pageSize: page.pageSize,
            ...formValues,
            deptId: searchDeptId.value,
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
  } as VxeTableGridOptions<SystemUserApi.User>,
  gridEvents: {
    checkboxAll: handleRowCheckboxChange,
    checkboxChange: handleRowCheckboxChange,
  },
});
</script>

<template>
  <Page auto-content-height title="用户与组织">
    <FormModal @success="handleRefresh" />
    <ResetPasswordModal @success="handleRefresh" />
    <AssignRoleModal @success="handleRefresh" />
    <ImportModal @success="handleRefresh" />

    <div class="oa-workspace-page min-w-0">
      <div class="oa-workspace-section-grid oa-user-workspace-grid min-w-0">
        <section class="oa-workspace-panel oa-user-dept-panel min-h-0 min-w-0">
          <div class="oa-workspace-panel-header">
            <div>
              <h3 class="oa-workspace-panel-title">部门目录</h3>
            </div>
          </div>
          <div class="oa-workspace-panel-body h-full min-h-0 min-w-0">
            <div class="oa-user-dept-shell h-full min-w-0">
              <DeptTree @select="handleDeptSelect" />
            </div>
          </div>
        </section>

        <section class="oa-workspace-panel oa-user-list-panel min-h-0 min-w-0">
          <div class="oa-workspace-panel-header">
            <div>
              <h3 class="oa-workspace-panel-title">用户列表</h3>
            </div>
          </div>
          <div class="oa-workspace-panel-body min-h-0 min-w-0">
            <Grid table-title="用户列表">
              <template #toolbar-tools>
                <TableAction
                  :actions="[
                    {
                      label: $t('ui.actionTitle.create', ['用户']),
                      type: 'primary',
                      icon: ACTION_ICON.ADD,
                      auth: ['system:user:create'],
                      onClick: handleCreate,
                    },
                    {
                      label: $t('ui.actionTitle.export'),
                      type: 'primary',
                      icon: ACTION_ICON.DOWNLOAD,
                      auth: ['system:user:export'],
                      onClick: handleExport,
                    },
                    {
                      label: $t('ui.actionTitle.import', ['用户']),
                      type: 'primary',
                      icon: ACTION_ICON.UPLOAD,
                      auth: ['system:user:import'],
                      onClick: handleImport,
                    },
                    {
                      label: $t('ui.actionTitle.deleteBatch'),
                      type: 'primary',
                      danger: true,
                      icon: ACTION_ICON.DELETE,
                      disabled: isEmpty(checkedIds),
                      auth: ['system:user:delete'],
                      onClick: handleDeleteBatch,
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
                      auth: ['system:user:update'],
                      onClick: handleEdit.bind(null, row),
                    },
                    {
                      label: $t('common.delete'),
                      type: 'link',
                      danger: true,
                      icon: ACTION_ICON.DELETE,
                      auth: ['system:user:delete'],
                      popConfirm: {
                        title: $t('ui.actionMessage.deleteConfirm', [row.username]),
                        confirm: handleDelete.bind(null, row),
                      },
                    },
                  ]"
                  :drop-down-actions="[
                    {
                      label: '分配角色',
                      type: 'link',
                      auth: ['system:permission:assign-user-role'],
                      onClick: handleAssignRole.bind(null, row),
                    },
                    {
                      label: '重置密码',
                      type: 'link',
                      auth: ['system:user:update-password'],
                      onClick: handleResetPassword.bind(null, row),
                    },
                  ]"
                />
              </template>
            </Grid>
          </div>
        </section>
      </div>
    </div>
  </Page>
</template>

<style scoped>
.oa-user-workspace-grid {
  align-items: stretch;
  grid-template-columns: 140px minmax(0, 1fr);
  min-height: calc(100vh - 84px);
  width: 100%;
  min-width: 0;
  max-width: 100%;
}

.oa-user-dept-panel,
.oa-user-list-panel {
  display: flex;
  min-height: 0;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  flex-direction: column;
}

.oa-user-dept-panel :deep(.oa-workspace-panel-header),
.oa-user-list-panel :deep(.oa-workspace-panel-header) {
  padding-bottom: 10px;
}

.oa-user-dept-panel :deep(.oa-workspace-panel-title),
.oa-user-list-panel :deep(.oa-workspace-panel-title) {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.2;
}

.oa-user-dept-panel :deep(.oa-workspace-panel-body),
.oa-user-list-panel :deep(.oa-workspace-panel-body) {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  padding-top: 8px;
}

.oa-user-list-panel :deep(.vxe-grid),
.oa-user-list-panel :deep(.vxe-grid--wrapper),
.oa-user-list-panel :deep(.vxe-grid--form-wrapper),
.oa-user-list-panel :deep(.vxe-grid--toolbar-wrapper),
.oa-user-list-panel :deep(.vxe-grid--body-wrapper) {
  min-height: 0;
  width: 100%;
  min-width: 0;
  max-width: 100%;
}

.oa-user-list-panel :deep(.vben-form),
.oa-user-list-panel :deep(.vxe-form--item),
.oa-user-list-panel :deep(.vxe-form--item-inner),
.oa-user-list-panel :deep(.ant-form-item-control),
.oa-user-list-panel :deep(.ant-form-item-control-input),
.oa-user-list-panel :deep(.ant-form-item-control-input-content) {
  min-width: 0;
  max-width: 100%;
}

.oa-user-list-panel :deep(.vxe-grid--form-wrapper) {
  padding-bottom: 4px;
}

.oa-user-list-panel :deep(.vxe-grid--toolbar-wrapper) {
  padding-bottom: 4px;
}

.oa-user-list-panel :deep(.vxe-table--header-wrapper) {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  margin-bottom: 0;
  overflow-y: hidden;
}

.oa-user-list-panel :deep(.vxe-table--body-wrapper) {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  min-height: calc(100vh - 472px);
  max-height: calc(100vh - 472px);
  overscroll-behavior-x: contain;
}

.oa-user-list-panel :deep(.vxe-table--header-wrapper),
.oa-user-list-panel :deep(.vxe-table--body-wrapper) {
  font-size: 13px;
}

.oa-user-list-panel :deep(.vxe-body--column),
.oa-user-list-panel :deep(.vxe-header--column) {
  padding-inline: 10px;
}

.oa-user-list-panel :deep(.vxe-body--column.col--last),
.oa-user-list-panel :deep(.vxe-header--column.col--last) {
  overflow: visible;
}

.oa-user-list-panel :deep(.table-actions) {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.oa-user-list-panel :deep(.vxe-table--header),
.oa-user-list-panel :deep(.vxe-table--body) {
  min-width: max-content;
}

.oa-user-list-panel :deep(.vxe-pager) {
  padding-top: 4px;
}

.oa-user-dept-shell {
  height: 100%;
  min-height: 0;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  border-top: 1px solid var(--oa-shell-border);
}

.oa-user-dept-shell :deep(.oa-dept-tree),
.oa-user-dept-shell :deep(.vben-scrollbar),
.oa-user-dept-shell :deep(.vben-scrollbar__wrap) {
  height: 100%;
}

.oa-user-dept-shell :deep(.ant-tree) {
  padding-top: 12px;
}

@media (max-width: 1200px) {
  .oa-user-workspace-grid {
    min-height: auto;
  }
}

@media (max-width: 1440px) {
  .oa-user-workspace-grid {
    grid-template-columns: 140px minmax(0, 1fr);
    gap: 14px;
  }

  .oa-user-list-panel :deep(.vxe-grid--form-wrapper) {
    padding-right: 0;
  }

  .oa-user-list-panel :deep(.vben-form) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .oa-user-list-panel :deep(.vxe-table--body-wrapper) {
    min-height: calc(100vh - 504px);
    max-height: calc(100vh - 504px);
  }

  .oa-user-list-panel :deep(.vxe-toolbar) {
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 10px;
    padding: 12px 0 8px;
  }

  .oa-user-list-panel :deep(.vxe-buttons--wrapper),
  .oa-user-list-panel :deep(.vxe-tools--wrapper),
  .oa-user-list-panel :deep(.vxe-tools--operate) {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 0;
    padding: 0;
  }

  .oa-user-list-panel :deep(.table-action .ant-btn) {
    padding-inline: 12px;
  }

  .oa-user-list-panel :deep(.vxe-pager--wrapper) {
    flex-wrap: wrap;
    gap: 10px 14px;
    justify-content: flex-end;
  }
}

@media (max-width: 1320px) {
  .oa-user-workspace-grid {
    grid-template-columns: 1fr;
  }

  .oa-user-dept-panel {
    max-height: 320px;
  }

  .oa-user-list-panel :deep(.vben-form) {
    grid-template-columns: 1fr;
  }

  .oa-user-list-panel :deep(.vxe-table--body-wrapper) {
    min-height: calc(100vh - 560px);
    max-height: calc(100vh - 560px);
  }
}
</style>
