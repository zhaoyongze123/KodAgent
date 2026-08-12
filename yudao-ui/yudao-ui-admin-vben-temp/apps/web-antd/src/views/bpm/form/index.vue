<script lang="ts" setup>
import type { TableColumnsType, TablePaginationConfig } from 'ant-design-vue';
import type { BpmFormApi } from '#/api/bpm/form';

import { onActivated, onMounted, reactive, ref } from 'vue';

import { Page, useVbenModal } from '@vben/common-ui';
import { DICT_TYPE } from '@vben/constants';
import { getDictLabel } from '@vben/hooks';
import { formatDateTime } from '@vben/utils';

import { Button, Form, Input, message, Table } from 'ant-design-vue';

import { deleteForm, getFormPage } from '#/api/bpm/form';
import { router } from '#/router';

import Detail from './modules/detail.vue';

defineOptions({ name: 'BpmForm' });

const [DetailModal, detailModalApi] = useVbenModal({
  connectedComponent: Detail,
  destroyOnClose: true,
});

const loading = ref(false);
const dataSource = ref<BpmFormApi.Form[]>([]);
const pagination = reactive({
  current: 1,
  pageSize: 20,
  total: 0,
});
const searchForm = reactive({
  name: '',
});

const columns: TableColumnsType<BpmFormApi.Form> = [
  {
    title: '编号',
    dataIndex: 'id',
    key: 'id',
    width: 96,
  },
  {
    title: '表单名称',
    dataIndex: 'name',
    key: 'name',
    ellipsis: true,
  },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 120,
  },
  {
    title: '备注',
    dataIndex: 'remark',
    key: 'remark',
    ellipsis: true,
  },
  {
    title: '创建时间',
    dataIndex: 'createTime',
    key: 'createTime',
    width: 180,
  },
  {
    title: '操作',
    key: 'actions',
    width: 220,
    fixed: 'right',
  },
];

async function loadData() {
  loading.value = true;
  try {
    const result = await getFormPage({
      pageNo: pagination.current,
      pageSize: pagination.pageSize,
      name: searchForm.name || undefined,
    });
    dataSource.value = result.list;
    pagination.total = result.total;
  } finally {
    loading.value = false;
  }
}

function handleCreate() {
  router.push({
    name: 'BpmFormEditor',
    query: { type: 'create' },
  });
}

function handleEdit(row: BpmFormApi.Form) {
  router.push({
    name: 'BpmFormEditor',
    query: { id: row.id, type: 'edit' },
  });
}

function handleCopy(row: BpmFormApi.Form) {
  router.push({
    name: 'BpmFormEditor',
    query: { copyId: row.id, type: 'copy' },
  });
}

function handleDetail(row: BpmFormApi.Form) {
  detailModalApi.setData(row).open();
}

async function handleDelete(row: BpmFormApi.Form) {
  const hideLoading = message.loading({
    content: `正在删除 ${row.name}`,
    duration: 0,
  });
  try {
    await deleteForm(row.id!);
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
  pagination.current = 1;
  loadData();
}

function handleTableChange(page: TablePaginationConfig) {
  pagination.current = page.current || 1;
  pagination.pageSize = page.pageSize || 20;
  loadData();
}

// 工作台以动态组件承载此列表，首次进入会执行 mounted 而非 activated。
// 两个生命周期都加载，兼容后续由 KeepAlive 承载的场景。
onMounted(loadData);
onActivated(loadData);
</script>

<template>
  <Page auto-content-height title="流程表单">
    <DetailModal />

    <div class="oa-admin-list-page">
      <section class="oa-admin-filterbar">
        <Form layout="inline" :model="searchForm" @finish="handleSearch">
          <Form.Item label="表单名称">
            <Input
              v-model:value="searchForm.name"
              placeholder="请输入表单名称"
              allow-clear
              class="oa-admin-filter-input"
              @press-enter="handleSearch"
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
          <h3>表单列表</h3>
          <Button type="primary" v-access:code="['bpm:form:create']" @click="handleCreate">
            新增流程表单
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
          :scroll="{ x: 1100 }"
          @change="handleTableChange"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              {{ getDictLabel(DICT_TYPE.COMMON_STATUS, record.status) || '-' }}
            </template>
            <template v-else-if="column.key === 'createTime'">
              {{ formatDateTime(record.createTime) }}
            </template>
            <template v-else-if="column.key === 'actions'">
              <div class="oa-admin-row-actions">
                <Button
                  type="link"
                  size="small"
                  v-access:code="['bpm:form:update']"
                  @click="handleCopy(record)"
                >
                  复制
                </Button>
                <Button
                  type="link"
                  size="small"
                  v-access:code="['bpm:form:update']"
                  @click="handleEdit(record)"
                >
                  修改
                </Button>
                <Button
                  type="link"
                  size="small"
                  v-access:code="['bpm:form:query']"
                  @click="handleDetail(record)"
                >
                  详情
                </Button>
                <Button
                  danger
                  type="link"
                  size="small"
                  v-access:code="['bpm:form:delete']"
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

.oa-admin-filter-input {
  width: 320px;
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
