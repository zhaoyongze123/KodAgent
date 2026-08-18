<script lang="ts" setup>
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';
import type { SystemDeptApi } from '#/api/system/dept';
import type { SystemUserApi } from '#/api/system/user';
import type { ComplexFieldConfig, ComplexOAModuleKey } from './config';

import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { confirm, Page } from '@vben/common-ui';
import { BpmCandidateStrategyEnum, BpmNodeIdEnum } from '@vben/constants';
import { useTabs } from '@vben/hooks';
import { IconifyIcon } from '@vben/icons';

import { Button, Col, DatePicker, Form, Input, InputNumber, message, Row, Select, Space, Switch } from 'ant-design-vue';

import { getProcessDefinition } from '#/api/bpm/definition';
import { getApprovalDetail } from '#/api/bpm/processInstance';
import { getSimpleDeptList } from '#/api/system/dept';
import { getSimpleUserList } from '#/api/system/user';
import { getUserProfile } from '#/api/system/user/profile';
import { KodFileUpload } from '#/components/upload';
import { router } from '#/router';
import { buildApprovalEntryBackRoute } from '#/utils/kod-entry';
import ProcessInstanceTimeline from '#/views/bpm/processInstance/detail/modules/time-line.vue';

import {
  applyProfileDefaults,
  buildDeptOptions,
  buildSubmitPayload,
  buildUserOptions,
  getComplexModuleViewConfig,
  normalizeFieldValue,
} from './config';

defineOptions({ name: 'OAComplexCreatePage' });

const props = defineProps<{
  moduleKey: ComplexOAModuleKey;
}>();

const route = useRoute();
const { closeCurrentTab, getTabDisableState } = useTabs();
const config = getComplexModuleViewConfig(props.moduleKey);

const formLoading = ref(false);
const previewLoading = ref(false);
const selectableUsers = ref<SystemUserApi.User[]>([]);
const selectableDepts = ref<SystemDeptApi.Dept[]>([]);
const userSelectOptions = computed(() => buildUserOptions(selectableUsers.value));
const deptSelectOptions = computed(() => buildDeptOptions(selectableDepts.value));
const processDefinitionId = ref('');
const activityNodes = ref<BpmProcessInstanceApi.ApprovalNodeInfo[]>([]);
const startUserSelectTasks = ref<BpmProcessInstanceApi.ApprovalNodeInfo[]>([]);
const startUserSelectAssignees = ref<Record<string, number[]>>({});
const formState = reactive<Record<string, any>>({});

async function closeCurrentTabIfPossible() {
  if (!getTabDisableState().disabledCloseCurrent) {
    await closeCurrentTab();
  }
}

function shouldReturnToOaLite() {
  const returnTo = Array.isArray(route.query.returnTo)
    ? route.query.returnTo[0]
    : route.query.returnTo;
  return returnTo === 'oa-lite';
}

function buildOaLiteRoute() {
  return buildApprovalEntryBackRoute(route.query);
}

function getFieldOptions(field: ComplexFieldConfig) {
  if (field.type === 'dept-multi-select') {
    return deptSelectOptions.value;
  }
  if (field.type === 'user-multi-select' || field.type === 'user-select') {
    return userSelectOptions.value;
  }
  return field.options || [];
}

function isStartUserSelectableNode(node: BpmProcessInstanceApi.ApprovalNodeInfo) {
  return node.candidateStrategy === BpmCandidateStrategyEnum.START_USER_SELECT;
}

function resetFormState() {
  Object.keys(formState).forEach((key) => {
    delete formState[key];
  });
  Object.assign(formState, applyProfileDefaults(config, null));
  startUserSelectAssignees.value = {};
}

async function loadBaseData() {
  const [profile, users, depts] = await Promise.all([
    getUserProfile().catch(() => null),
    getSimpleUserList(),
    getSimpleDeptList(),
  ]);
  selectableUsers.value = users;
  selectableDepts.value = depts;
  Object.assign(formState, applyProfileDefaults(config, profile));
}

async function loadDetail(id: number) {
  const detail = await config.getDetailRequest(id);
  config.createFields.forEach((field) => {
    if (detail[field.field] !== undefined) {
      formState[field.field] = normalizeFieldValue(field, detail[field.field]);
    }
  });
  config.detailFields.forEach((field) => {
    if (field.submit === false && detail[field.field] !== undefined) {
      formState[field.field] = normalizeFieldValue(field, detail[field.field]);
    }
  });
}

async function loadProcessDefinition() {
  const processDefinitionDetail: any = await getProcessDefinition(
    undefined,
    config.processDefinitionKey,
  );
  if (!processDefinitionDetail) {
    message.error(`流程 ${config.title} 未配置，请检查 BPM 模型`);
    return false;
  }
  processDefinitionId.value = processDefinitionDetail.id;
  return true;
}

async function loadApprovalPreview() {
  if (!processDefinitionId.value) {
    return;
  }
  previewLoading.value = true;
  try {
    const data = await getApprovalDetail({
      activityId: BpmNodeIdEnum.START_USER_NODE_ID,
      processDefinitionId: processDefinitionId.value,
      processVariablesStr: JSON.stringify(config.buildProcessVariables(formState)),
    });
    activityNodes.value = data?.activityNodes || [];
    startUserSelectTasks.value = activityNodes.value.filter((node) =>
      isStartUserSelectableNode(node),
    );
    const nextAssignees: Record<string, number[]> = {};
    startUserSelectTasks.value.forEach((node) => {
      nextAssignees[node.id] = startUserSelectAssignees.value[node.id] || [];
    });
    startUserSelectAssignees.value = nextAssignees;
  } finally {
    previewLoading.value = false;
  }
}

function handleSelectUserConfirm(activityId: string, userList: SystemUserApi.User[]) {
  startUserSelectAssignees.value[activityId] = (userList || []).map((user) =>
    Number(user.id),
  );
}

function validateRequiredFields() {
  for (const field of config.createFields) {
    if (!field.required) {
      continue;
    }
    const value = formState[field.field];
    if (field.type === 'user-multi-select' || field.type === 'dept-multi-select' || field.type === 'files') {
      if (!Array.isArray(value) || value.length === 0) {
        message.warning(`${field.label}不能为空`);
        return false;
      }
      continue;
    }
    if (field.type === 'switch') {
      continue;
    }
    if (value === undefined || value === null || value === '') {
      message.warning(`${field.label}不能为空`);
      return false;
    }
  }
  return true;
}

async function handleSubmit() {
  if (!processDefinitionId.value) {
    message.error(`流程 ${config.title} 未配置，无法发起`);
    return;
  }
  if (!validateRequiredFields()) {
    return;
  }
  for (const node of startUserSelectTasks.value) {
    const assignees = startUserSelectAssignees.value[node.id] || [];
    if (isStartUserSelectableNode(node) && assignees.length === 0) {
      message.warning(`请选择 ${node.name} 的审批人`);
      return;
    }
  }
  formLoading.value = true;
  try {
    const payload = buildSubmitPayload(config, formState);
    payload.startUserSelectAssignees = startUserSelectAssignees.value;
    await config.createRequest(payload);
    message.success(`${config.title}发起成功`);
    await closeCurrentTabIfPossible();
    await router.push(
      shouldReturnToOaLite()
        ? buildOaLiteRoute()
        : { name: config.routeNames.index },
    );
  } finally {
    formLoading.value = false;
  }
}

function handleBack() {
  confirm({
    content: '确定要返回上一页吗？未提交的内容将不会保留。',
    icon: 'warning',
    async beforeClose({ isConfirm }) {
      if (isConfirm) {
        await closeCurrentTabIfPossible();
        if (shouldReturnToOaLite()) {
          await router.push(buildOaLiteRoute());
        }
      }
      return Promise.resolve(true);
    },
  });
}

watch(
  () => config.previewWatchFields.map((field) => formState[field]),
  async () => {
    if (!processDefinitionId.value) {
      return;
    }
    await loadApprovalPreview();
  },
  { deep: true },
);

onMounted(async () => {
  resetFormState();
  await loadBaseData();
  const hasDefinition = await loadProcessDefinition();
  if (!hasDefinition) {
    return;
  }
  if (route.query.id) {
    await loadDetail(Number(route.query.id));
  }
  await nextTick();
  await loadApprovalPreview();
});
</script>

<template>
  <Page>
    <Row :gutter="20" class="oa-bpm-complex-create-shell">
      <Col :span="16">
        <section class="oa-bpm-complex-panel">
          <header class="oa-bpm-complex-panel-head">
            <div>
              <h3 class="oa-bpm-complex-title">
                {{ route.query.id ? `重新发起${config.title}` : `创建${config.title}` }}
              </h3>
            </div>
            <Button @click="handleBack">
              <IconifyIcon icon="lucide:arrow-left" />
              返回
            </Button>
          </header>
          <Form layout="vertical" class="oa-bpm-complex-form-grid">
            <Form.Item
              v-for="field in config.createFields"
              :key="field.field"
              class="oa-bpm-complex-form-field"
              :class="{
                'is-full': field.type === 'textarea' || field.type === 'files',
              }"
              :label="field.label"
              :required="field.required"
            >
              <Input
                v-if="field.type === 'readonly' || field.type === 'text'"
                v-model:value="formState[field.field]"
                :disabled="field.type === 'readonly'"
                :placeholder="field.placeholder"
              />
              <Input.TextArea
                v-else-if="field.type === 'textarea'"
                v-model:value="formState[field.field]"
                :placeholder="field.placeholder"
                :rows="field.rows || 4"
              />
              <Select
                v-else-if="
                  field.type === 'select' ||
                  field.type === 'user-select' ||
                  field.type === 'user-multi-select' ||
                  field.type === 'dept-multi-select'
                "
                v-model:value="formState[field.field]"
                :allow-clear="true"
                :mode="field.type === 'user-multi-select' || field.type === 'dept-multi-select' ? 'multiple' : undefined"
                :options="getFieldOptions(field)"
                :placeholder="field.placeholder"
              />
              <DatePicker
                v-else-if="field.type === 'datetime'"
                v-model:value="formState[field.field]"
                class="w-full"
                :placeholder="field.placeholder"
                format="YYYY-MM-DD HH:mm:ss"
                show-time
                value-format="x"
              />
              <InputNumber
                v-else-if="field.type === 'number'"
                v-model:value="formState[field.field]"
                class="w-full"
                :min="0"
                :placeholder="field.placeholder"
              />
              <Switch
                v-else-if="field.type === 'switch'"
                v-model:checked="formState[field.field]"
              />
              <KodFileUpload
                v-else-if="field.type === 'files'"
                v-model:model-value="formState[field.field]"
                :max-number="10"
              />
            </Form.Item>
          </Form>

          <div class="oa-bpm-complex-actions">
            <Space :size="12">
              <Button type="primary" :loading="formLoading" @click="handleSubmit">
                提交
              </Button>
            </Space>
          </div>
        </section>
      </Col>
      <Col :span="8">
        <aside class="oa-bpm-complex-panel">
          <ProcessInstanceTimeline
            :activity-nodes="activityNodes"
            :show-status-icon="false"
            :loading="previewLoading"
            @select-user-confirm="handleSelectUserConfirm"
          />
        </aside>
      </Col>
    </Row>
  </Page>
</template>

<style lang="scss" scoped>
.oa-bpm-complex-create-shell {
  align-items: start;
}

.oa-bpm-complex-panel {
  min-width: 0;
  border-top: 1px solid var(--oa-shell-border);
  padding-top: 18px;
}

.oa-bpm-complex-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 20px;
}

.oa-bpm-complex-form-field {
  min-width: 0;
}

.oa-bpm-complex-form-field.is-full {
  grid-column: 1 / -1;
}

.oa-bpm-complex-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-bpm-complex-eyebrow {
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.oa-bpm-complex-title {
  margin: 6px 0 0;
  color: var(--oa-ink);
  font-size: 18px;
  font-weight: 600;
}

.oa-bpm-complex-actions {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--oa-shell-border);
}

@media (max-width: 1100px) {
  .oa-bpm-complex-create-shell {
    :deep(.ant-col) {
      width: 100%;
    }
  }

  .oa-bpm-complex-form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
