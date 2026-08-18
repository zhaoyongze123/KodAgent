<script lang="ts" setup>
import type { TableColumnsType, TablePaginationConfig } from 'ant-design-vue';
import type { BpmProcessExpressionApi } from '#/api/bpm/processExpression';

import { onActivated, reactive, ref } from 'vue';

import { Page, useVbenModal } from '@vben/common-ui';
import { DICT_TYPE } from '@vben/constants';
import { getDictLabel, getDictOptions } from '@vben/hooks';
import { formatDateTime } from '@vben/utils';

import { Button, Form, Input, message, Select, Table } from 'ant-design-vue';

import {
  deleteProcessExpression,
  getProcessExpressionPage,
} from '#/api/bpm/processExpression';

import FormModalContent from './modules/form.vue';

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: FormModalContent,
  destroyOnClose: true,
});

const loading = ref(false);
const dataSource = ref<BpmProcessExpressionApi.ProcessExpression[]>([]);
const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
});
const searchForm = reactive({
  name: '',
  status: undefined as number | undefined,
});

const columns: TableColumnsType<BpmProcessExpressionApi.ProcessExpression> = [
  { title: '编号', dataIndex: 'id', key: 'id', width: 96 },
  { title: '名字', dataIndex: 'name', key: 'name', width: 180 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 120 },
  { title: '表达式', dataIndex: 'expression', key: 'expression', ellipsis: true },
  { title: '创建时间', dataIndex: 'createTime', key: 'createTime', width: 180 },
  { title: '操作', key: 'actions', width: 160, fixed: 'right' },
];

async function loadData() {
  loading.value = true;
  try {
    const result = await getProcessExpressionPage({
      pageNo: pagination.current,
      pageSize: pagination.pageSize,
      name: searchForm.name || undefined,
      status: searchForm.status,
    });
    dataSource.value = result.list;
    pagination.total = result.total;
  } finally {
    loading.value = false;
  }
}

function handleCreate() {
  formModalApi.setData(null).open();
}

function handleEdit(row: BpmProcessExpressionApi.ProcessExpression) {
  formModalApi.setData(row).open();
}

async function handleDelete(row: BpmProcessExpressionApi.ProcessExpression) {
  const hideLoading = message.loading({
    content: `正在删除 ${row.name}`,
    duration: 0,
  });
  try {
    await deleteProcessExpression(row.id);
    message.success(`已删除 ${row.name}`);
    if (dataSource.value.length === 1 && pagination.current > 1) {
      pagination.current -= 1;
    }
    await loadData();
  } finally {
    hideLoading();
  }
}

function handleSearch() {
  pagination.current = 1;
  loadData();
}

function handleReset() {
  searchForm.name = '';
  searchForm.status = undefined;
  pagination.current = 1;
  loadData();
}

function handleTableChange(page: TablePaginationConfig) {
  pagination.current = page.current || 1;
  pagination.pageSize = page.pageSize || 20;
  loadData();
}

onActivated(() => {
  loadData();
});
</script>

<template>
  <Page auto-content-height title="流程表达式">
    <FormModal @success="loadData" />

    <div class="oa-admin-list-page">
      <section class="oa-admin-filterbar">
        <Form layout="inline" :model="searchForm" @finish="handleSearch">
          <Form.Item label="名字">
            <Input
              v-model:value="searchForm.name"
              placeholder="请输入名字"
              allow-clear
              class="oa-admin-filter-input"
              @press-enter="handleSearch"
            />
          </Form.Item>
          <Form.Item label="状态">
            <Select
              v-model:value="searchForm.status"
              placeholder="请选择状态"
              allow-clear
              class="oa-admin-filter-select"
              :options="getDictOptions(DICT_TYPE.COMMON_STATUS, 'number')"
            />
          </Form.Item>
        </Form>
        <div class="oa-admin-filter-actions">
          <Button @click="handleReset">重置</Button>
          <Button type="primary" @click="handleSearch">搜索</Button>
        </div>
      </section>

      <section class="oa-admin-table-shell">
        <div class="oa-admin-table-toolbar">
          <h3>表达式列表</h3>
          <Button
            type="primary"
            v-access:code="['bpm:process-expression:create']"
            @click="handleCreate"
          >
            新增流程表达式
          </Button>
        </div>

        <Table
          row-key="id"
          :columns="columns"
          :data-source="dataSource"
          :loading="loading"
          :pagination="{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: pagination.total,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (total) => `共 ${total} 条记录`,
          }"
          :scroll="{ x: 1080 }"
          @change="handleTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              {{ getDictLabel(DICT_TYPE.COMMON_STATUS, record.status) || '-' }}
            </template>
            <template v-else-if="column.key === 'createTime'">
              {{ formatDateTime((record as any).createTime) }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <div class="oa-admin-row-actions">
                <Button
                  type="link"
                  size="small"
                  v-access:code="['bpm:process-expression:update']"
                  @click="handleEdit(record)"
                >
                  修改
                </Button>
                <Button
                  danger
                  type="link"
                  size="small"
                  v-access:code="['bpm:process-expression:delete']"
                  @click="handleDelete(record)"
                >
                  删除
                </Button>
              </div>
            </template>
          </template>
        </Table>
      </section>
    </div>
  </Page>
</template>

<style scoped>
.oa-admin-list-page {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.oa-admin-filterbar {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  padding: 0 0 14px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-admin-filter-input,
.oa-admin-filter-select {
  width: 260px;
}

.oa-admin-filter-actions {
  display: flex;
  gap: 10px;
}

.oa-admin-table-shell {
  min-width: 0;
}

.oa-admin-table-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-admin-table-toolbar h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.oa-admin-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
</style>
