<script lang="ts" setup>
import type { ComplexFieldConfig, ComplexOAModuleKey } from './config';

import { computed, h, onActivated, reactive, ref } from 'vue';

import { Page, prompt } from '@vben/common-ui';
import { BpmProcessInstanceStatus } from '@vben/constants';

import { Button, Col, DatePicker, Form, Input, message, Row, Select, Space, Table, Tag, Textarea } from 'ant-design-vue';

import { cancelProcessInstanceByStartUser } from '#/api/bpm/processInstance';
import { formatFlowFormDateTime } from '#/components/form-create';
import { router } from '#/router';

import { getComplexModuleViewConfig } from './config';

defineOptions({ name: 'OAComplexIndexPage' });

const props = defineProps<{
  moduleKey: ComplexOAModuleKey;
}>();

const config = getComplexModuleViewConfig(props.moduleKey);
const loading = ref(false);
const dataSource = ref<Record<string, any>[]>([]);
const searchState = reactive<Record<string, any>>({
  createTime: undefined,
});
const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
});

function getFieldOptions(field: ComplexFieldConfig) {
  return field.options || [];
}

function renderStatus(status?: number) {
  switch (status) {
    case 1:
      return { color: 'processing', text: '审批中' };
    case 2:
      return { color: 'success', text: '已通过' };
    case 3:
      return { color: 'error', text: '已拒绝' };
    case 4:
      return { color: 'default', text: '已取消' };
    default:
      return { color: 'default', text: '-' };
  }
}

function renderCell(column: (typeof config.tableColumns)[number], record: Record<string, any>) {
  const value = record[column.field];
  if (column.type === 'status') {
    const status = renderStatus(value);
    return h(Tag, { color: status.color }, () => status.text);
  }
  if (column.type === 'datetime') {
    return formatFlowFormDateTime(value) || '-';
  }
  if (column.type === 'boolean') {
    return value ? '是' : '否';
  }
  if (column.type === 'amount') {
    return value ?? '-';
  }
  if (column.type === 'select') {
    const matched = column.options?.find((item) => String(item.value) === String(value));
    return matched?.label || value || '-';
  }
  return value || '-';
}

const columns = computed(() => [
  ...config.tableColumns.map((column) => ({
    customRender: ({ record }: { record: Record<string, any> }) => renderCell(column, record),
    dataIndex: column.field,
    key: column.field,
    title: column.label,
    width: column.width,
  })),
  {
    fixed: 'right',
    key: 'actions',
    title: '操作',
    width: 260,
  },
]);

async function loadData() {
  loading.value = true;
  try {
    const params: Record<string, any> = {
      pageNo: pagination.current,
      pageSize: pagination.pageSize,
    };
    Object.entries(searchState).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') {
        return;
      }
      if (key === 'createTime' && Array.isArray(value) && value.length === 2) {
        params.createTime = value;
        return;
      }
      params[key] = value;
    });
    const resp = await config.getPageRequest(params);
    dataSource.value = resp.list || [];
    pagination.total = resp.total || 0;
  } finally {
    loading.value = false;
  }
}

function handleCreate() {
  router.push({ name: config.routeNames.create });
}

function handleDetail(record: Record<string, any>) {
  router.push({
    name: config.routeNames.detail,
    query: { id: record.id },
  });
}

function handleRecreate(record: Record<string, any>) {
  router.push({
    name: config.routeNames.create,
    query: { id: record.id },
  });
}

function handleProgress(record: Record<string, any>) {
  router.push({
    name: 'BpmProcessInstanceDetail',
    query: { id: record.processInstanceId },
  });
}

function handleCancel(record: Record<string, any>) {
  prompt({
    title: '取消流程',
    content: '请输入取消原因',
    modelPropName: 'value',
    component: () =>
      h(Textarea, {
        placeholder: '请输入取消原因',
        allowClear: true,
        rows: 2,
      }),
    async beforeClose(scope) {
      if (!scope.isConfirm) {
        return;
      }
      if (!scope.value) {
        message.error('请输入取消原因');
        return false;
      }
      await cancelProcessInstanceByStartUser(Number(record.processInstanceId), scope.value);
      message.success('取消成功');
      await loadData();
      return true;
    },
  });
}

function handlePageChange(page: number, pageSize: number) {
  pagination.current = page;
  pagination.pageSize = pageSize;
  loadData();
}

function handleSearch() {
  pagination.current = 1;
  loadData();
}

function handleReset() {
  Object.keys(searchState).forEach((key) => {
    searchState[key] = key === 'createTime' ? undefined : '';
  });
  pagination.current = 1;
  loadData();
}

onActivated(() => {
  loadData();
});
</script>

<template>
  <Page auto-content-height>
    <section class="oa-bpm-complex-index-shell">
      <Form layout="vertical">
        <Row :gutter="16">
          <Col
            v-for="field in config.searchFields"
            :key="field.field"
            :span="6"
          >
            <Form.Item :label="field.label">
              <Input
                v-if="field.type === 'text'"
                v-model:value="searchState[field.field]"
                :placeholder="field.placeholder"
              />
              <Select
                v-else-if="field.type === 'select'"
                v-model:value="searchState[field.field]"
                :allow-clear="true"
                :options="getFieldOptions(field)"
                :placeholder="field.placeholder"
              />
            </Form.Item>
          </Col>
          <Col :span="6">
            <Form.Item label="申请时间">
              <DatePicker.RangePicker
                v-model:value="searchState.createTime"
                class="w-full"
                show-time
                value-format="x"
              />
            </Form.Item>
          </Col>
        </Row>
      </Form>

      <Space class="mb-4">
        <Button type="primary" @click="handleSearch">查询</Button>
        <Button @click="handleReset">重置</Button>
        <Button type="primary" @click="handleCreate">发起{{ config.title }}</Button>
      </Space>

      <Table
        :columns="columns"
        :data-source="dataSource"
        :loading="loading"
        :pagination="{
          current: pagination.current,
          pageSize: pagination.pageSize,
          total: pagination.total,
          onChange: handlePageChange,
          onShowSizeChange: handlePageChange,
          showSizeChanger: true,
        }"
        row-key="id"
        scroll="{ x: 1400 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'actions'">
            <Space>
              <Button type="link" @click="handleDetail(record)">详情</Button>
              <Button type="link" @click="handleProgress(record)">进度</Button>
              <Button
                v-if="record.status === BpmProcessInstanceStatus.RUNNING"
                danger
                type="link"
                @click="handleCancel(record)"
              >
                取消
              </Button>
              <Button
                v-else
                type="link"
                @click="handleRecreate(record)"
              >
                重新发起
              </Button>
            </Space>
          </template>
        </template>
      </Table>
    </section>
  </Page>
</template>

<style lang="scss" scoped>
.oa-bpm-complex-index-shell {
  border-top: 1px solid var(--oa-shell-border);
  padding-top: 18px;
}

.oa-bpm-complex-index-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-bpm-complex-index-eyebrow {
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.oa-bpm-complex-index-title {
  margin: 6px 0 0;
  color: var(--oa-ink);
  font-size: 20px;
  font-weight: 600;
}
</style>
