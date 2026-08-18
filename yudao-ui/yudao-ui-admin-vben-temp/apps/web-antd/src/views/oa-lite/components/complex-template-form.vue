<script lang="ts" setup>
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';
import type { SystemDeptApi } from '#/api/system/dept';
import type { SystemUserApi } from '#/api/system/user';
import type { ComplexFieldConfig, ComplexOAModuleKey } from '#/views/bpm/oa/complex/config';

import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';

import { BpmCandidateStrategyEnum, BpmNodeIdEnum } from '@vben/constants';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  message,
  Select,
  Switch,
} from 'ant-design-vue';

import { getProcessDefinition } from '#/api/bpm/definition';
import { getApprovalDetail } from '#/api/bpm/processInstance';
import { getSimpleDeptList } from '#/api/system/dept';
import { getSimpleUserList } from '#/api/system/user';
import { getUserProfile } from '#/api/system/user/profile';
import { KodFileUpload } from '#/components/upload';
import ProcessInstanceTimeline from '#/views/bpm/processInstance/detail/modules/time-line.vue';
import {
  applyProfileDefaults,
  buildDeptOptions,
  buildSubmitPayload,
  buildUserOptions,
  getComplexModuleViewConfig,
  normalizeFieldValue,
} from '#/views/bpm/oa/complex/config';

defineOptions({ name: 'OaLiteComplexTemplateForm' });

const props = defineProps<{
  businessKey?: string;
  templateKey: ComplexOAModuleKey;
}>();

const emit = defineEmits<{
  back: [];
  success: [];
}>();

const config = computed(() => getComplexModuleViewConfig(props.templateKey));
const formLoading = ref(false);
const previewLoading = ref(false);
const selectableUsers = ref<SystemUserApi.User[]>([]);
const selectableDepts = ref<SystemDeptApi.Dept[]>([]);
const processDefinitionId = ref('');
const activityNodes = ref<BpmProcessInstanceApi.ApprovalNodeInfo[]>([]);
const startUserSelectTasks = ref<BpmProcessInstanceApi.ApprovalNodeInfo[]>([]);
const startUserSelectAssignees = ref<Record<string, number[]>>({});
const formState = reactive<Record<string, any>>({});

const userSelectOptions = computed(() => buildUserOptions(selectableUsers.value));
const deptSelectOptions = computed(() => buildDeptOptions(selectableDepts.value));

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
  startUserSelectAssignees.value = {};
  activityNodes.value = [];
  startUserSelectTasks.value = [];
}

async function loadBaseData() {
  const [profile, users, depts] = await Promise.all([
    getUserProfile().catch(() => null),
    getSimpleUserList(),
    getSimpleDeptList(),
  ]);
  selectableUsers.value = users;
  selectableDepts.value = depts;
  Object.assign(formState, applyProfileDefaults(config.value, profile));
}

async function loadDetail() {
  const businessId = Number(props.businessKey);
  if (Number.isNaN(businessId) || businessId <= 0) {
    return;
  }
  const detail = await config.value.getDetailRequest(businessId);
  config.value.createFields.forEach((field) => {
    if (detail[field.field] !== undefined) {
      formState[field.field] = normalizeFieldValue(field, detail[field.field]);
    }
  });
  config.value.detailFields.forEach((field) => {
    if (field.submit === false && detail[field.field] !== undefined) {
      formState[field.field] = normalizeFieldValue(field, detail[field.field]);
    }
  });
}

async function loadProcessDefinition() {
  const processDefinitionDetail: any = await getProcessDefinition(
    undefined,
    config.value.processDefinitionKey,
  );
  if (!processDefinitionDetail) {
    message.error(`流程 ${config.value.title} 未配置，请检查 BPM 模型`);
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
      processVariablesStr: JSON.stringify(
        config.value.buildProcessVariables(formState),
      ),
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
  for (const field of config.value.createFields) {
    if (!field.required) {
      continue;
    }
    const value = formState[field.field];
    if (
      field.type === 'user-multi-select' ||
      field.type === 'dept-multi-select' ||
      field.type === 'files'
    ) {
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
    message.error(`流程 ${config.value.title} 未配置，无法发起`);
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
    const payload = buildSubmitPayload(config.value, formState);
    payload.startUserSelectAssignees = startUserSelectAssignees.value;
    await config.value.createRequest(payload);
    message.success(`${config.value.title}发起成功`);
    emit('success');
  } finally {
    formLoading.value = false;
  }
}

watch(
  () => config.value.previewWatchFields.map((field) => formState[field]),
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
  if (props.businessKey) {
    await loadDetail();
  }
  await nextTick();
  await loadApprovalPreview();
});
</script>

<template>
  <main class="oa-lite-complex-main">
    <div class="oa-lite-complex-shell">
      <div class="oa-lite-complex-card">
        <div class="oa-lite-complex-title-row">
          <div>
            <h1 class="oa-lite-complex-title">{{ config.title }}</h1>
          </div>
          <IconifyIcon icon="lucide:files" class="oa-lite-complex-badge" />
        </div>

        <div class="oa-lite-complex-divider"></div>

          <Form layout="vertical" class="oa-lite-complex-form-grid">
            <Form.Item
              v-for="field in config.createFields"
              :key="field.field"
              class="oa-lite-complex-form-field"
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
              :rows="field.rows || 4"
              :placeholder="field.placeholder"
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
              :mode="
                field.type === 'user-multi-select' ||
                field.type === 'dept-multi-select'
                  ? 'multiple'
                  : undefined
              "
              :options="getFieldOptions(field)"
              :placeholder="field.placeholder"
            />
            <DatePicker
              v-else-if="field.type === 'datetime'"
              v-model:value="formState[field.field]"
              class="w-full"
              format="YYYY-MM-DD HH:mm:ss"
              show-time
              value-format="x"
              :placeholder="field.placeholder"
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
      </div>

      <div class="oa-lite-complex-card">
        <div class="oa-lite-complex-flow-body">
          <ProcessInstanceTimeline
            :activity-nodes="activityNodes"
            :show-status-icon="false"
            @select-user-confirm="handleSelectUserConfirm"
          />
        </div>

        <div class="oa-lite-complex-submit-row">
          <Button @click="emit('back')">返回</Button>
          <Button type="primary" :loading="formLoading" @click="handleSubmit">
            提交{{ config.title }}
          </Button>
        </div>
      </div>
    </div>
  </main>
</template>

<style lang="scss" scoped>
.oa-lite-complex-main {
  padding: 24px 0 32px;
}

.oa-lite-complex-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(340px, 0.8fr);
  gap: 24px;
}

.oa-lite-complex-card {
  border-top: 1px solid var(--oa-shell-border);
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  padding: 20px 0 0;
}

.oa-lite-complex-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0 18px;
}

.oa-lite-complex-form-field {
  min-width: 0;
}

.oa-lite-complex-form-field.is-full {
  grid-column: 1 / -1;
}

.oa-lite-complex-title-row,
.oa-lite-complex-flow-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.oa-lite-complex-title {
  margin: 0;
  font-size: 26px;
  font-weight: 600;
  color: var(--oa-ink);
}

.oa-lite-complex-badge {
  font-size: 30px;
  color: var(--oa-accent);
}

.oa-lite-complex-divider {
  height: 1px;
  background: var(--oa-shell-border);
  margin: 18px 0 10px;
}

.oa-lite-complex-flow-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--oa-ink);
}

.oa-lite-complex-flow-tag {
  border-radius: 0;
  background: var(--oa-accent-soft);
  color: var(--oa-accent);
  font-size: 12px;
  padding: 6px 12px;
}

.oa-lite-complex-flow-body {
  min-height: 340px;
  padding-top: 8px;
}

.oa-lite-complex-submit-row {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 12px;
}

@media (max-width: 1100px) {
  .oa-lite-complex-shell {
    grid-template-columns: 1fr;
  }

  .oa-lite-complex-form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
