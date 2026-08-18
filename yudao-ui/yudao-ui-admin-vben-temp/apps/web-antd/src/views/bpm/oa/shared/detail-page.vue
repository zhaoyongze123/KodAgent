<script lang="ts" setup>
import type { BpmOACommonApi, OAModuleApiKey } from '#/api/bpm/oa/common';

import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import { ContentWrap } from '@vben/common-ui';

import { Spin } from 'ant-design-vue';

import { getAttendance } from '#/api/bpm/oa/attendance';
import { getExpense } from '#/api/bpm/oa/expense';
import { getLeaveCancel } from '#/api/bpm/oa/leave-cancel';
import { getOvertime } from '#/api/bpm/oa/overtime';
import { getOuting } from '#/api/bpm/oa/outing';
import { getSeal } from '#/api/bpm/oa/seal';
import { getTrip } from '#/api/bpm/oa/trip';

import { getOAModuleViewConfig } from './config';
import { useDetailFormSchema } from './data';

const props = defineProps<{
  id?: string;
  moduleKey: OAModuleApiKey;
}>();

const { query } = useRoute();
const config = getOAModuleViewConfig(props.moduleKey);
const detailRequestMap: Partial<Record<
  OAModuleApiKey,
  (id: number) => Promise<BpmOACommonApi.OARecord>
>> = {
  attendance: getAttendance,
  expense: getExpense,
  leaveCancel: getLeaveCancel,
  overtime: getOvertime,
  outing: getOuting,
  seal: getSeal,
  trip: getTrip,
};

const loading = ref(false);
const formData = ref<BpmOACommonApi.OARecord>();
const queryId = computed(() => query.id as string);
const detailSchema = useDetailFormSchema(config);

function hasValue(value: unknown) {
  if (value === undefined || value === null) {
    return false;
  }
  if (typeof value === 'string') {
    return value.trim() !== '';
  }
  if (Array.isArray(value)) {
    return value.length > 0;
  }
  if (typeof value === 'object') {
    return Object.keys(value).length > 0;
  }
  return true;
}

const visibleDetailFields = computed(() =>
  detailSchema.filter((field) => {
    const value = formData.value?.[field.field];
    return hasValue(value) && (!field.show || field.show(formData.value));
  }),
);

function renderDetailValue(field: (typeof detailSchema)[number]) {
  const value = formData.value?.[field.field];
  return field.render ? field.render(value, formData.value) : value;
}

async function getDetailData() {
  try {
    loading.value = true;
    const request = detailRequestMap[props.moduleKey];
    if (!request) {
      return;
    }
    const id = Number(props.id || queryId.value);
    if (!Number.isSafeInteger(id) || id <= 0) {
      return;
    }
    formData.value = await request(id);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  getDetailData();
});
</script>

<template>
  <ContentWrap class="m-2">
    <Spin :spinning="loading" tip="加载中...">
      <div class="oa-shared-detail-fields">
        <div
          v-for="field in visibleDetailFields"
          :key="field.field"
          class="oa-shared-detail-field"
        >
          <span class="oa-shared-detail-label">{{ field.label }}</span>
          <span class="oa-shared-detail-value">
            {{ renderDetailValue(field) }}
          </span>
        </div>
      </div>
    </Spin>
  </ContentWrap>
</template>

<style scoped>
.oa-shared-detail-fields {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.oa-shared-detail-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
  padding: 14px 0 16px;
  border-bottom: 1px solid var(--oa-shell-border, #e8edf3);
}

.oa-shared-detail-field:first-child {
  padding-top: 0;
}

.oa-shared-detail-field:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.oa-shared-detail-label {
  color: var(--oa-ink-faint, #8b98a9);
  font-size: 12px;
  line-height: 1.5;
}

.oa-shared-detail-value {
  min-width: 0;
  color: var(--oa-ink, #17202d);
  font-size: 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
</style>
