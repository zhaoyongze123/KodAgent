<script lang="ts" setup>
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';
import type { SystemUserApi } from '#/api/system/user';
import type { OAModuleApiKey } from '#/views/bpm/oa/shared/config';

import { computed, h, nextTick, ref, shallowRef, watch } from 'vue';

import { prompt } from '@vben/common-ui';
import {
  BpmFieldPermissionType,
  BpmModelFormType,
  BpmModelType,
  BpmProcessInstanceStatus,
} from '@vben/constants';
import { IconifyIcon } from '@vben/icons';
import { useUserStore } from '@vben/stores';
import { formatDateTime } from '@vben/utils';
import { useI18n } from '@vben/locales';

import { Button, Empty, message, Spin, Tag, Textarea } from 'ant-design-vue';

import {
  cancelProcessInstanceByAdmin,
  cancelProcessInstanceByStartUser,
  getApprovalDetail,
  getProcessInstanceBpmnModelView,
} from '#/api/bpm/processInstance';
import { withdrawTask } from '#/api/bpm/task';
import { getSimpleUserList } from '#/api/system/user';
import { setConfAndFields2 } from '#/components/form-create';
import {
  getOaFilePreviewUrl,
  normalizeOaAssetUrl,
  registerComponent,
} from '#/utils';
import { isAdminUser } from '#/utils/oa-user';
import ProcessInstanceBpmnViewer from '#/views/bpm/processInstance/detail/modules/bpm-viewer.vue';
import ProcessInstanceOperationButton from '#/views/bpm/processInstance/detail/modules/operation-button.vue';
import ProcessInstanceSimpleViewer from '#/views/bpm/processInstance/detail/modules/simple-bpm-viewer.vue';
import BpmProcessInstanceTaskList from '#/views/bpm/processInstance/detail/modules/task-list.vue';
import ProcessInstanceTimeline from '#/views/bpm/processInstance/detail/modules/time-line.vue';

defineOptions({ name: 'OaLiteProcessDetail' });

export type OaLiteDetailSection =
  | 'copied'
  | 'initiated'
  | 'manager'
  | 'pending'
  | 'processed';

export interface OaLiteDetailRequest {
  activityId?: string;
  businessKey?: string;
  processInstanceId: string;
  taskId?: string;
}

const props = defineProps<{
  request: null | OaLiteDetailRequest;
  section: OaLiteDetailSection;
}>();

const emit = defineEmits<{
  recreate: [
    processInstanceId: string,
    businessKey?: string,
    processDefinitionKey?: string,
    formCustomCreatePath?: string,
  ];
  refresh: [];
}>();
const { t } = useI18n();
const userStore = useUserStore();

const loading = ref(false);
const activeTab = ref<'diagram' | 'form' | 'record'>('form');
const approvalDetail = ref<BpmProcessInstanceApi.ApprovalDetailRespVO | null>(
  null,
);
const processModelView = ref<any>({});
const operationButtonRef = ref();
const taskListRef = ref();
const userOptions = ref<SystemUserApi.User[]>([]);
const businessFormComponent = shallowRef<any>(null);
const normalFormApi = ref<any>();
const normalForm = ref({
  option: {},
  rule: [],
  value: {},
});
const writableFields = ref<string[]>([]);
const fieldPermissions = ref<Record<string, string>>({});

const processInstance = computed(() => approvalDetail.value?.processInstance);
const processDefinition = computed(
  () => approvalDetail.value?.processDefinition || null,
);
const businessModuleKey = computed<OAModuleApiKey | undefined>(() => {
  const key = processDefinition.value?.key || '';
  if (key.startsWith('oa_')) {
    return key.slice(3) as OAModuleApiKey;
  }
  return undefined;
});
const activityNodes = computed(() => approvalDetail.value?.activityNodes || []);
const todoTask = computed(() => approvalDetail.value?.todoTask);

const canCancelProcess = computed(
  () =>
    (props.section === 'initiated' ||
      (props.section === 'manager' && isAdminUser(userStore.userRoles))) &&
    processInstance.value?.status === BpmProcessInstanceStatus.RUNNING,
);
const canRecreateProcess = computed(
  () =>
    props.section === 'initiated' &&
    processInstance.value?.status !== BpmProcessInstanceStatus.RUNNING &&
    Boolean(processInstance.value?.businessKey),
);
const canWithdrawTask = computed(
  () => props.section === 'processed' && Boolean(props.request?.taskId),
);
const showReadonlyChip = computed(() => props.section === 'copied');
const showOperationButton = computed(
  () => props.section === 'pending' && Boolean(todoTask.value?.id),
);
const businessKeyIsValid = computed(() => {
  const businessKey = processInstance.value?.businessKey;
  return typeof businessKey === 'string'
    ? /^\d+$/.test(businessKey)
    : typeof businessKey === 'number' && Number.isSafeInteger(businessKey);
});
const hasEditableNormalForm = computed(
  () => props.section === 'pending' && writableFields.value.length > 0,
);
const canViewDiagram = computed(() => isAdminUser(userStore.userRoles));

watch(
  canViewDiagram,
  (visible) => {
    if (!visible && activeTab.value === 'diagram') {
      activeTab.value = 'form';
    }
  },
  { immediate: true },
);

function withTimeout<T>(promise: Promise<T>, timeoutMs = 15_000) {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      window.setTimeout(() => reject(new Error('审批详情加载超时')), timeoutMs);
    }),
  ]);
}

interface OaLiteAttachment {
  extension: string;
  name: string;
  size?: number;
  url: string;
}

interface OaLiteDisplayField {
  attachments: OaLiteAttachment[];
  displayValue: string;
  field: string;
  rule: any;
  title: string;
}

function parseSerializedValue(value: unknown): unknown {
  if (typeof value !== 'string') {
    return value;
  }
  const trimmed = value.trim();
  if (!trimmed || !['[', '{'].includes(trimmed[0] || '')) {
    return value;
  }
  try {
    return JSON.parse(trimmed);
  } catch {
    return value;
  }
}

function hasDisplayValue(value: unknown) {
  const parsed = parseSerializedValue(value);
  if (parsed === undefined || parsed === null) {
    return false;
  }
  if (typeof parsed === 'string') {
    return parsed.trim() !== '';
  }
  if (Array.isArray(parsed)) {
    return parsed.length > 0;
  }
  if (typeof parsed === 'object') {
    return Object.keys(parsed).length > 0;
  }
  return true;
}

function getAssetUrl(value: unknown) {
  if (!value || typeof value !== 'object') {
    return String(value || '');
  }
  const item = value as Record<string, any>;
  return String(
    item.url ||
      item.fileUrl ||
      item.response?.url ||
      item.response?.data ||
      item.response ||
      '',
  );
}

function getAttachmentName(value: unknown, url: string) {
  const name =
    value && typeof value === 'object'
      ? String((value as Record<string, any>).name || '')
      : '';
  const raw = name || url;
  const withoutQuery = raw.split(/[?#]/, 1)[0] || raw;
  const lastPart = withoutQuery.slice(withoutQuery.lastIndexOf('/') + 1);
  try {
    return decodeURIComponent(lastPart) || '未命名文件';
  } catch {
    return lastPart || '未命名文件';
  }
}

function getFileExtension(name: string) {
  return name.includes('.')
    ? name.split('.').pop()?.toUpperCase() || 'FILE'
    : 'FILE';
}

function getFileIcon(name: string) {
  const extension = getFileExtension(name);
  if (extension === 'PDF') {
    return 'lucide:file-type-2';
  }
  if (['DOC', 'DOCX', 'TXT'].includes(extension)) {
    return 'lucide:file-text';
  }
  if (['XLS', 'XLSX', 'CSV'].includes(extension)) {
    return 'lucide:file-spreadsheet';
  }
  if (['PNG', 'JPG', 'JPEG', 'GIF', 'WEBP', 'SVG'].includes(extension)) {
    return 'lucide:image';
  }
  return 'lucide:file';
}

function normalizeAttachments(value: unknown): OaLiteAttachment[] {
  const parsed = parseSerializedValue(value);
  let items = Array.isArray(parsed) ? parsed : [parsed];
  if (typeof parsed === 'string' && parsed.includes(',')) {
    items = parsed.split(',').map((item) => item.trim());
  }
  return items
    .map((item) => {
      const url = normalizeOaAssetUrl(getAssetUrl(item));
      if (!url) {
        return null;
      }
      const name = getAttachmentName(item, url);
      const size =
        item && typeof item === 'object'
          ? Number(
              (item as Record<string, any>).size ||
                (item as Record<string, any>).response?.size ||
                0,
            )
          : 0;
      return {
        extension: getFileExtension(name),
        name,
        size: size > 0 ? size : undefined,
        url,
      };
    })
    .filter(Boolean) as OaLiteAttachment[];
}

function formatFileSize(size?: number) {
  if (!size || size <= 0) {
    return '';
  }
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function getAttachmentPreviewUrl(file: OaLiteAttachment) {
  return getOaFilePreviewUrl(file.url, file.name);
}

function flattenNormalRules(rules: any[], fields: any[] = []) {
  rules.forEach((rule) => {
    if (rule?.field && rule?.title) {
      fields.push(rule);
    }
    if (Array.isArray(rule?.children)) {
      flattenNormalRules(rule.children, fields);
    }
    if (Array.isArray(rule?.props?.rule)) {
      flattenNormalRules(rule.props.rule, fields);
    }
  });
  return fields;
}

function getRuleOptions(rule: any) {
  const options = rule?.options || rule?.props?.options || rule?.props?.fieldProps?.options;
  return Array.isArray(options) ? options : [];
}

function getOptionLabel(rule: any, value: unknown) {
  const matched = getRuleOptions(rule).find(
    (option: any) => String(option?.value) === String(value),
  );
  return matched?.label ?? matched?.name;
}

function formatNormalValue(rule: any, value: unknown): string {
  const parsed = parseSerializedValue(value);
  if (Array.isArray(parsed)) {
    return parsed
      .map((item) => formatNormalValue(rule, item))
      .filter(Boolean)
      .join('、');
  }
  if (parsed && typeof parsed === 'object') {
    const item = parsed as Record<string, any>;
    return String(item.label || item.name || item.nickname || item.value || '');
  }
  if (parsed === true && String(rule?.type).toLowerCase().includes('switch')) {
    return '是';
  }
  if (parsed === false && String(rule?.type).toLowerCase().includes('switch')) {
    return '否';
  }
  const optionLabel = getOptionLabel(rule, parsed);
  if (optionLabel !== undefined) {
    return String(optionLabel);
  }
  const ruleType = String(rule?.type || '').toLowerCase();
  if (ruleType.includes('date') || ruleType.includes('time')) {
    return parsed ? formatDateTime(parsed as any) : '';
  }
  return parsed === undefined || parsed === null ? '' : String(parsed);
}

const normalDisplayFields = computed<OaLiteDisplayField[]>(() => {
  const values = (normalForm.value.value || {}) as Record<string, any>;
  return flattenNormalRules(normalForm.value.rule as any[])
    .filter((rule) => fieldPermissions.value[rule.field] !== BpmFieldPermissionType.NONE)
    .map((rule) => {
      const attachments = String(rule.type || '').toLowerCase().includes('upload')
        ? normalizeAttachments(values[rule.field])
        : [];
      return {
        attachments,
        displayValue: formatNormalValue(rule, values[rule.field]),
        field: rule.field,
        rule,
        title: String(rule.title),
      };
    })
    .filter((field) => field.attachments.length > 0 || hasDisplayValue(field.displayValue));
});

function getStatusText(status?: number) {
  switch (status) {
    case BpmProcessInstanceStatus.APPROVE: {
      return t('page.oaLite.status.approved');
    }
    case BpmProcessInstanceStatus.CANCEL: {
      return t('page.oaLite.status.cancelled');
    }
    case BpmProcessInstanceStatus.REJECT: {
      return t('page.oaLite.status.rejected');
    }
    case BpmProcessInstanceStatus.RUNNING: {
      return t('page.oaLite.status.running');
    }
    default: {
      return t('page.oaLite.status.processing');
    }
  }
}

function getStatusTone(status?: number) {
  if (status === BpmProcessInstanceStatus.APPROVE) {
    return 'success';
  }
  if (status === BpmProcessInstanceStatus.REJECT) {
    return 'danger';
  }
  if (status === BpmProcessInstanceStatus.CANCEL) {
    return 'muted';
  }
  if (status === BpmProcessInstanceStatus.RUNNING) {
    return 'primary';
  }
  return 'neutral';
}

function resetNormalForm() {
  normalForm.value = {
    option: {},
    rule: [],
    value: {},
  };
  businessFormComponent.value = null;
  processModelView.value = {};
  approvalDetail.value = null;
  writableFields.value = [];
  fieldPermissions.value = {};
}

function setFieldPermission(field: string, permission: string) {
  if (permission === BpmFieldPermissionType.READ) {
    normalFormApi.value?.disabled(true, field);
  }
  if (permission === BpmFieldPermissionType.WRITE) {
    normalFormApi.value?.disabled(false, field);
    if (!writableFields.value.includes(field)) {
      writableFields.value.push(field);
    }
  }
  if (permission === BpmFieldPermissionType.NONE) {
    normalFormApi.value?.hidden(true, field);
  }
}

async function ensureUserOptions() {
  if (userOptions.value.length > 0) {
    return;
  }
  userOptions.value = await getSimpleUserList();
}

async function loadDetail() {
  if (!props.request) {
    resetNormalForm();
    return;
  }
  loading.value = true;
  try {
    const data = await withTimeout(getApprovalDetail({
      activityId: props.request.activityId,
      processInstanceId: props.request.processInstanceId,
      taskId: props.request.taskId,
    }));
    approvalDetail.value = data;

    if (!data?.processDefinition || !data?.processInstance) {
      return;
    }

    const processDefinitionData = data.processDefinition;
    if (processDefinitionData.formType === BpmModelFormType.NORMAL) {
      writableFields.value = [];
      fieldPermissions.value = data.formFieldsPermission || {};
      if (processDefinitionData.formConf && processDefinitionData.formFields) {
        setConfAndFields2(
          normalForm,
          processDefinitionData.formConf,
          processDefinitionData.formFields || [],
          data.processInstance.formVariables,
        );
      } else {
        normalForm.value = {
          option: {},
          rule: [],
          value: data.processInstance.formVariables || {},
        };
      }
      await nextTick();
      normalFormApi.value?.btn?.show(false);
      normalFormApi.value?.resetBtn?.show(false);
      normalFormApi.value?.disabled(true);
      Object.entries(data.formFieldsPermission || {}).forEach(
        ([field, permission]) => {
          setFieldPermission(field, permission as string);
        },
      );
    } else {
      const componentPath = processDefinitionData.formCustomViewPath || '';
      businessFormComponent.value =
        registerComponent(componentPath) ||
        (componentPath.includes('/bpm/oa/')
          ? registerComponent('/bpm/oa/shared/detail-page')
          : null);
    }

    if (canViewDiagram.value) {
      processModelView.value = await withTimeout(getProcessInstanceBpmnModelView(
        props.request.processInstanceId,
      ));
    }

    await ensureUserOptions();
    await nextTick();
    operationButtonRef.value?.loadTodoTask(data.todoTask);
  } catch (error: any) {
    console.error('审批详情加载失败', error);
    resetNormalForm();
    message.error(error?.message || '审批详情加载失败，请稍后重试');
  } finally {
    loading.value = false;
  }
}

async function handleWithdraw() {
  if (!props.request?.taskId) {
    return;
  }
  await withdrawTask(props.request.taskId);
  message.success(t('page.oaLite.messages.withdrawSuccess'));
  emit('refresh');
}

function handleCancelProcess() {
  if (!processInstance.value?.id) {
    return;
  }
  prompt({
    component: () =>
      h(Textarea, {
        allowClear: true,
        placeholder: t('page.oaLite.processDetail.cancelReasonPlaceholder'),
        rows: 2,
      }),
    content: t('page.oaLite.processDetail.cancelReasonPlaceholder'),
    modelPropName: 'value',
    title: t('page.oaLite.processDetail.cancelProcess'),
  }).then(async (reason) => {
    if (!reason) {
      return;
    }
    if (props.section === 'manager') {
      await cancelProcessInstanceByAdmin(processInstance.value!.id, reason);
    } else {
      await cancelProcessInstanceByStartUser(processInstance.value!.id, reason);
    }
    message.success(t('page.oaLite.messages.cancelSuccess'));
    emit('refresh');
  });
}

function handleRecreate() {
  if (!props.request?.processInstanceId) {
    return;
  }
  emit(
    'recreate',
    props.request.processInstanceId,
    processInstance.value?.businessKey,
    processDefinition.value?.key,
    processDefinition.value?.formCustomCreatePath || undefined,
  );
}

function handleRefresh() {
  emit('refresh');
}

watch(
  () => props.request,
  async () => {
    activeTab.value = 'form';
    await loadDetail();
  },
  { deep: true, immediate: true },
);

watch(
  () => activeTab.value,
  async (tab) => {
    if (tab !== 'record') {
      return;
    }
    await nextTick();
    taskListRef.value?.refresh();
  },
);
</script>

<template>
  <div class="oa-lite-process-detail">
    <Spin :spinning="loading">
      <template v-if="processInstance && processDefinition">
        <div class="oa-lite-process-content">
          <div class="oa-lite-process-overview">
            <div class="oa-lite-process-head">
              <div class="oa-lite-process-head-main">
                <div class="oa-lite-process-name-row">
                  <h3 class="oa-lite-process-name">
                    {{ processInstance.name }}
                  </h3>
                  <span
                    class="oa-lite-status-chip"
                    :class="`tone-${getStatusTone(processInstance.status)}`"
                  >
                    {{ getStatusText(processInstance.status) }}
                  </span>
                </div>
                <div class="oa-lite-process-desc-row">
                  <span>
                    {{ t('page.oaLite.processDetail.startUser') }}：{{
                      processInstance.startUser?.nickname || '-'
                    }}
                  </span>
                  <span>
                    {{ t('page.oaLite.processDetail.submitTime') }}：{{
                      formatDateTime(
                        processInstance.startTime || processInstance.createTime,
                      )
                    }}
                  </span>
                </div>
                <div class="oa-lite-process-id">
                  {{ t('page.oaLite.processDetail.processNo') }}：{{
                    processInstance.id || '-'
                  }}
                  <span class="oa-lite-process-id-divider">|</span>
                  {{ t('page.oaLite.processDetail.businessKey') }}：{{
                    processInstance.businessKey || '-'
                  }}
                </div>
              </div>

              <div class="oa-lite-detail-actions">
                <Button
                  v-if="canWithdrawTask"
                  class="oa-lite-white-button"
                  @click="handleWithdraw"
                >
                  {{ t('page.oaLite.processDetail.withdrawTask') }}
                </Button>
                <Button
                  v-if="canCancelProcess"
                  class="oa-lite-white-button"
                  @click="handleCancelProcess"
                >
                  {{ t('page.oaLite.processDetail.cancelProcess') }}
                </Button>
                <Button
                  v-if="canRecreateProcess"
                  type="primary"
                  class="oa-lite-white-primary"
                  @click="handleRecreate"
                >
                  {{ t('page.oaLite.processDetail.restartProcess') }}
                </Button>
                <Tag v-if="showReadonlyChip" class="oa-lite-readonly-tag">
                  {{ t('page.oaLite.processDetail.readonly') }}
                </Tag>
              </div>
            </div>

            <div class="oa-lite-process-tabs">
              <button
                class="oa-lite-process-tab"
                :class="{ active: activeTab === 'form' }"
                @click="activeTab = 'form'"
              >
                {{ t('page.oaLite.processDetail.tabs.detail') }}
              </button>
              <button
                v-if="canViewDiagram"
                class="oa-lite-process-tab"
                :class="{ active: activeTab === 'diagram' }"
                @click="activeTab = 'diagram'"
              >
                {{ t('page.oaLite.processDetail.tabs.diagram') }}
              </button>
              <button
                class="oa-lite-process-tab"
                :class="{ active: activeTab === 'record' }"
                @click="activeTab = 'record'"
              >
                {{ t('page.oaLite.processDetail.tabs.record') }}
              </button>
            </div>
          </div>

          <div v-if="activeTab === 'form'" class="oa-lite-detail-grid">
            <section class="oa-lite-detail-card oa-lite-detail-card-form">
              <component
                :is="businessFormComponent"
                v-if="
                  processDefinition.formType === BpmModelFormType.CUSTOM &&
                  businessFormComponent &&
                  businessKeyIsValid
                "
                :id="String(processInstance.businessKey || '')"
                :module-key="businessModuleKey"
                class="oa-lite-business-form"
              />
              <form-create
                v-else-if="
                  processDefinition.formType === BpmModelFormType.NORMAL &&
                  hasEditableNormalForm
                "
                v-model="normalForm.value"
                v-model:api="normalFormApi"
                :option="normalForm.option"
                :rule="normalForm.rule"
              />
              <div
                v-else-if="
                  processDefinition.formType === BpmModelFormType.NORMAL
                "
                class="oa-lite-normal-form-fields"
              >
                <div
                  v-for="field in normalDisplayFields"
                  :key="field.field"
                  class="oa-lite-normal-form-field"
                >
                  <span class="oa-lite-normal-form-label">
                    {{ field.title }}
                  </span>
                  <div class="oa-lite-normal-form-value">
                    <div
                      v-if="field.attachments.length > 0"
                      class="oa-lite-normal-attachment-list"
                    >
                      <div
                        v-for="file in field.attachments"
                        :key="file.url"
                        class="oa-lite-normal-attachment"
                        :title="file.name"
                      >
                        <span class="oa-lite-normal-attachment-icon">
                          <IconifyIcon :icon="getFileIcon(file.name)" />
                        </span>
                        <span class="oa-lite-normal-attachment-main">
                          <strong>{{ file.name }}</strong>
                          <span>
                            {{ file.extension }}
                            <template v-if="formatFileSize(file.size)">
                              · {{ formatFileSize(file.size) }}
                            </template>
                          </span>
                        </span>
                        <span class="oa-lite-normal-attachment-actions">
                          <a
                            class="oa-lite-normal-attachment-action"
                            :href="getAttachmentPreviewUrl(file)"
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            预览
                          </a>
                          <a
                            class="oa-lite-normal-attachment-action"
                            :download="file.name"
                            :href="file.url"
                          >
                            下载
                          </a>
                        </span>
                      </div>
                    </div>
                    <span v-else class="oa-lite-normal-form-text">
                      {{ field.displayValue }}
                    </span>
                  </div>
                </div>
                <Empty
                  v-if="normalDisplayFields.length === 0"
                  :description="t('page.oaLite.processDetail.emptyBusinessForm')"
                />
              </div>
              <Empty
                v-else
                :description="t('page.oaLite.processDetail.emptyBusinessForm')"
              />
            </section>

            <aside class="oa-lite-detail-card">
              <ProcessInstanceTimeline :activity-nodes="activityNodes" />
            </aside>
          </div>

          <div
            v-else-if="activeTab === 'diagram' && canViewDiagram"
            class="oa-lite-detail-card"
          >
            <ProcessInstanceSimpleViewer
              v-if="processDefinition.modelType === BpmModelType.SIMPLE"
              :loading="loading"
              :model-view="processModelView"
            />
            <ProcessInstanceBpmnViewer
              v-else
              :loading="loading"
              :model-view="processModelView"
            />
          </div>

          <div v-else class="oa-lite-detail-card">
            <BpmProcessInstanceTaskList
              ref="taskListRef"
              :id="String(processInstance.id)"
              :loading="loading"
            />
          </div>
        </div>

        <div
          v-if="showOperationButton"
          class="oa-lite-detail-card oa-lite-operation-card"
        >
          <div class="oa-lite-operation-bar">
            <ProcessInstanceOperationButton
              ref="operationButtonRef"
              :normal-form="normalForm"
              :normal-form-api="normalFormApi"
              :process-definition="processDefinition"
              :process-instance="processInstance"
              :user-options="userOptions"
              :writable-fields="writableFields"
              @success="handleRefresh"
            />
          </div>
        </div>
      </template>

      <div v-else class="oa-lite-detail-empty">
        <Empty :description="t('page.oaLite.processDetail.emptySelect')" />
      </div>
    </Spin>
  </div>
</template>

<style lang="scss" scoped>
.oa-lite-process-detail {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--oa-shell-surface-subtle);
}

.oa-lite-process-detail :deep(.ant-spin-nested-loading),
.oa-lite-process-detail :deep(.ant-spin-container) {
  height: 100%;
}

.oa-lite-process-detail :deep(.ant-spin-container) {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.oa-lite-process-content {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
  gap: 16px;
  overflow: auto;
  padding: 20px 20px 24px;
}

.oa-lite-process-overview {
  padding: 18px 20px 0;
  border: 1px solid var(--oa-shell-border);
  border-radius: 10px;
  background: var(--oa-shell-surface);
}

.oa-lite-process-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 0;
}

.oa-lite-process-head-main {
  min-width: 0;
}

.oa-lite-process-name-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.oa-lite-process-name {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--oa-ink);
}

.oa-lite-process-desc-row {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  font-size: 13px;
  color: var(--oa-ink-soft);
}

.oa-lite-process-id {
  margin-top: 10px;
  font-size: 12px;
  color: var(--oa-ink-faint);
}

.oa-lite-process-id-divider {
  margin: 0 8px;
}

.oa-lite-detail-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.oa-lite-process-tabs {
  display: flex;
  gap: 18px;
  border-bottom: 1px solid var(--oa-shell-border);
  margin-top: 14px;
  padding: 0 0 10px;
}

.oa-lite-process-tab {
  border: none;
  background: transparent;
  color: var(--oa-ink-soft);
  border-radius: 0;
  padding: 8px 2px 10px;
  cursor: pointer;
  transition: color 0.18s ease;
}

.oa-lite-process-tab.active {
  color: var(--oa-accent);
  box-shadow: inset 0 -1px 0 var(--oa-accent);
}

.oa-lite-detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 320px);
  gap: 12px;
  align-items: start;
}

.oa-lite-detail-card {
  background: var(--oa-shell-surface);
  border-radius: 10px;
  border: 1px solid var(--oa-shell-border);
  padding: 20px;
  min-width: 0;
}

.oa-lite-detail-card-form {
  overflow: hidden;
}

.oa-lite-detail-grid > aside.oa-lite-detail-card {
  position: sticky;
  top: 0;
  max-height: calc(100dvh - 330px);
  overflow: auto;
}

.oa-lite-detail-card-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--oa-ink);
  margin-bottom: 14px;
}

.oa-lite-detail-empty {
  min-height: 320px;
  border-radius: 0;
  border-top: 1px dashed var(--oa-shell-border);
  border-bottom: 1px dashed var(--oa-shell-border);
  background: transparent;
  display: flex;
  align-items: center;
  justify-content: center;
}

.oa-lite-operation-card {
  flex: none;
  margin: 0 16px 16px;
  border-radius: 10px;
  padding: 0;
  background: var(--oa-shell-surface);
}

.oa-lite-operation-bar {
  position: relative;
  padding: 9px 14px;

  :deep(.ant-btn) {
    border-radius: 8px;
  }

  :deep(.oa-process-actions) {
    padding-top: 0;
    border-top: 0;
    gap: 0;
  }

  :deep(.oa-process-actions-bar) {
    flex-wrap: nowrap;
    overflow-x: auto;
  }
}

.oa-lite-status-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  border-radius: 0;
  padding: 0 2px 2px;
  font-size: 12px;
  font-weight: 600;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-lite-status-chip.tone-primary {
  background: transparent;
  border-bottom-color: color-mix(
    in srgb,
    var(--oa-accent) 36%,
    var(--oa-shell-border)
  );
  color: var(--oa-accent);
}

.oa-lite-status-chip.tone-success {
  background: transparent;
  border-bottom-color: color-mix(
    in srgb,
    var(--oa-success) 42%,
    var(--oa-shell-border)
  );
  color: var(--oa-success-text);
}

.oa-lite-status-chip.tone-danger {
  background: transparent;
  border-bottom-color: color-mix(
    in srgb,
    var(--oa-danger-text) 42%,
    var(--oa-shell-border)
  );
  color: var(--oa-danger-text);
}

.oa-lite-status-chip.tone-muted,
.oa-lite-status-chip.tone-neutral {
  background: transparent;
  color: var(--oa-ink-soft);
}

.oa-lite-white-button,
.oa-lite-white-primary {
  border-radius: 0;
}

.oa-lite-readonly-tag {
  border-radius: 0;
  background: transparent;
  color: var(--oa-accent);
  border-color: color-mix(
    in srgb,
    var(--oa-accent) 34%,
    var(--oa-shell-border)
  );
}

.oa-lite-normal-form-fields {
  display: flex;
  min-width: 0;
  flex-direction: column;
}

.oa-lite-normal-form-field {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 6px;
  padding: 14px 0 16px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-lite-normal-form-field:first-child {
  padding-top: 0;
}

.oa-lite-normal-form-field:last-of-type {
  padding-bottom: 0;
  border-bottom: 0;
}

.oa-lite-normal-form-label {
  color: var(--oa-ink-faint);
  font-size: 12px;
  line-height: 1.5;
}

.oa-lite-normal-form-value {
  min-width: 0;
  max-width: 100%;
  color: var(--oa-ink);
  font-size: 14px;
  line-height: 1.65;
  overflow-wrap: anywhere;
}

.oa-lite-normal-form-text {
  display: block;
  white-space: pre-wrap;
}

.oa-lite-normal-attachment-list {
  display: flex;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  flex-direction: column;
  gap: 8px;
}

.oa-lite-normal-attachment {
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 64px;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--oa-shell-border);
  border-radius: 8px;
  background: var(--oa-shell-surface-subtle);
  color: inherit;
  text-decoration: none;
  transition: border-color 0.18s ease, background-color 0.18s ease;
}

.oa-lite-normal-attachment:hover,
.oa-lite-normal-attachment:focus-visible {
  border-color: color-mix(
    in srgb,
    var(--oa-accent) 42%,
    var(--oa-shell-border)
  );
  background: color-mix(
    in srgb,
    var(--oa-accent-soft) 62%,
    var(--oa-shell-surface-subtle)
  );
  outline: none;
}

.oa-lite-normal-attachment-icon {
  display: inline-flex;
  width: 34px;
  height: 34px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: var(--oa-accent-soft);
  color: var(--oa-accent);
  font-size: 20px;
}

.oa-lite-normal-attachment-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.oa-lite-normal-attachment-main strong,
.oa-lite-normal-attachment-main span {
  display: block;
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.oa-lite-normal-attachment-main strong {
  color: var(--oa-ink);
  font-size: 14px;
  font-weight: 500;
}

.oa-lite-normal-attachment-main span {
  color: var(--oa-ink-faint);
  font-size: 12px;
}

.oa-lite-normal-attachment-action {
  flex: none;
  color: var(--oa-accent);
  font-size: 12px;
  text-decoration: none;
}

.oa-lite-normal-attachment-actions {
  display: inline-flex;
  flex: none;
  gap: 12px;
}

.oa-lite-business-form {
  :deep(.m-2) {
    margin: 0 !important;
  }

  :deep(.mx-4) {
    margin-left: 0 !important;
    margin-right: 0 !important;
  }
}

.oa-lite-process-detail {
  :deep(.oa-process-actions-eyebrow) {
    color: var(--oa-ink-faint);
  }

  :deep(.oa-process-actions-caption) {
    color: var(--oa-ink-soft);
  }

  :deep(.oa-process-actions-bar .ant-btn) {
    min-width: 72px;
    min-height: 48px;
    border-color: transparent;
    background: transparent;
    color: var(--oa-ink);
    box-shadow: none;
  }

  :deep(.oa-process-actions-bar .ant-btn:hover),
  :deep(.oa-process-actions-bar .ant-btn:focus-visible) {
    border-color: transparent;
    color: var(--oa-accent);
    background: color-mix(
      in srgb,
      var(--oa-accent-soft) 22%,
      var(--oa-shell-surface) 78%
    );
  }

  :deep(.oa-process-actions-bar .ant-btn.ant-btn-primary) {
    background: color-mix(in srgb, var(--oa-accent) 9%, transparent);
    border-color: transparent;
    color: var(--oa-accent);
  }

  :deep(.oa-process-actions-bar .ant-btn.ant-btn-primary.ant-btn-dangerous) {
    background: color-mix(in srgb, var(--oa-danger-text) 90%, #b42318);
    border-color: color-mix(in srgb, var(--oa-danger-text) 88%, #b42318);
    color: #fff;
  }

  :deep(.oa-process-actions-bar .ant-btn.ant-btn-background-ghost) {
    background: transparent;
  }

  :deep(.oa-process-actions-bar .ant-btn.ant-btn-dashed) {
    border-style: solid;
  }

  :deep(
    .oa-process-actions-bar .ant-btn.ant-btn-primary.ant-btn-background-ghost
  ) {
    border-color: color-mix(
      in srgb,
      var(--oa-accent) 54%,
      var(--oa-shell-border)
    );
    color: var(--oa-accent);
    background: color-mix(in srgb, var(--oa-accent-soft) 18%, transparent);
  }

  :deep(
    .oa-process-actions-bar
      .ant-btn.ant-btn-primary.ant-btn-background-ghost.ant-btn-dangerous
  ) {
    border-color: color-mix(
      in srgb,
      var(--oa-danger-text) 52%,
      var(--oa-shell-border)
    );
    color: var(--oa-danger-text);
    background: color-mix(in srgb, var(--oa-danger-text) 10%, transparent);
  }

  :deep(.oa-process-actions-bar .ant-btn[disabled]),
  :deep(.oa-process-actions-bar .ant-btn[disabled]:hover) {
    border-color: color-mix(
      in srgb,
      var(--oa-shell-border) 90%,
      transparent
    ) !important;
    background: color-mix(
      in srgb,
      var(--oa-shell-surface-subtle) 88%,
      var(--oa-shell-surface) 12%
    ) !important;
    color: var(--oa-ink-soft) !important;
    opacity: 0.88;
  }

  :deep(.ant-timeline-item-content) {
    color: var(--oa-ink) !important;
  }

  :deep(.bg-card) {
    background: var(--oa-shell-surface) !important;
    border: 0;
    border-radius: 8px;
  }

  :deep(.simple-process-model-container) {
    border-top: 1px solid var(--oa-shell-border);
    border-bottom: 1px solid var(--oa-shell-border);
    border-left: 0;
    border-right: 0;
    border-radius: 0;
    overflow: hidden;
  }

  :deep(.simple-process-model-container .ant-btn),
  :deep(.simple-process-model-container .ant-btn > span),
  :deep(.simple-process-model-container .ant-btn .iconify) {
    color: var(--oa-ink) !important;
  }

  :deep(.simple-process-model-container .ant-btn) {
    background: transparent !important;
    border-color: var(--oa-shell-border) !important;
    box-shadow: none !important;
  }

  :deep(.vxe-table--render-default),
  :deep(.vxe-table--render-default .vxe-table--header-wrapper),
  :deep(.vxe-table--render-default .vxe-table--body-wrapper),
  :deep(.vxe-table--render-default .vxe-body--column),
  :deep(.vxe-table--render-default .vxe-header--column) {
    background: var(--oa-shell-surface) !important;
  }

  :deep(.vxe-table--render-default .vxe-cell),
  :deep(.vxe-table--render-default .vxe-table--empty-content) {
    color: var(--oa-ink) !important;
  }

  :deep(.vxe-table--render-default .vxe-header--column .vxe-cell) {
    color: var(--oa-ink-soft) !important;
    font-weight: 600;
  }
}

:global(body.oa-lite-theme-dark) .oa-lite-process-detail {
  :deep(.oa-process-actions-eyebrow) {
    color: color-mix(in srgb, var(--oa-ink-soft) 78%, white 22%);
  }

  :deep(.oa-process-actions-title),
  :deep(.oa-process-actions-caption),
  :deep(.oa-process-inline-section-title),
  :deep(.ant-form-item-label > label),
  :deep(.ant-form-item-extra),
  :deep(.ant-form-item-explain),
  :deep(.ant-select-selection-item),
  :deep(.ant-select-selection-placeholder),
  :deep(.ant-select-arrow),
  :deep(.ant-input-prefix),
  :deep(.ant-input-show-count-suffix),
  :deep(.ant-popover-title),
  :deep(.ant-empty-description) {
    color: var(--oa-ink) !important;
  }

  :deep(.oa-process-inline-note) {
    color: color-mix(in srgb, var(--oa-ink-soft) 84%, white 16%);
    border-left-color: color-mix(
      in srgb,
      var(--oa-danger-text) 62%,
      var(--oa-shell-border)
    );
  }

  :deep(.oa-process-actions .ant-popover-arrow::before),
  :deep(.oa-process-actions .ant-popover-arrow::after) {
    background: var(--oa-shell-surface-raised);
  }

  :deep(.oa-process-actions .ant-popover-inner) {
    border-color: color-mix(
      in srgb,
      var(--oa-shell-border-strong, var(--oa-shell-border)) 88%,
      transparent
    );
    background: var(--oa-shell-surface-raised);
    box-shadow: 0 22px 50px rgb(1 8 20 / 48%);
  }

  :deep(.oa-process-actions .ant-popover-inner-content),
  :deep(.oa-process-action-panel) {
    background: var(--oa-shell-surface-raised);
  }

  :deep(.oa-process-action-panel) {
    color: var(--oa-ink);
  }

  :deep(.oa-process-inline-section) {
    border-bottom-color: color-mix(
      in srgb,
      var(--oa-shell-border-strong, var(--oa-shell-border)) 86%,
      transparent
    );
  }

  :deep(.oa-process-actions .ant-input),
  :deep(.oa-process-actions .ant-input-affix-wrapper),
  :deep(.oa-process-actions .ant-select-selector),
  :deep(.oa-process-actions .ant-image),
  :deep(
    .oa-process-actions .ant-btn:not(.ant-btn-primary):not(.ant-btn-dangerous)
  ) {
    border-color: color-mix(
      in srgb,
      var(--oa-shell-border-strong, var(--oa-shell-border)) 92%,
      transparent
    ) !important;
  }

  :deep(.oa-process-actions .ant-input),
  :deep(.oa-process-actions .ant-input-affix-wrapper),
  :deep(.oa-process-actions .ant-select-selector) {
    background: color-mix(
      in srgb,
      var(--oa-shell-surface-subtle) 92%,
      black 8%
    ) !important;
    color: var(--oa-ink) !important;
  }

  :deep(.oa-process-actions .ant-input::placeholder),
  :deep(.oa-process-actions .ant-select-selection-placeholder) {
    color: color-mix(in srgb, var(--oa-ink-soft) 84%, white 16%) !important;
  }
}

@media (max-width: 1200px) {
  .oa-lite-detail-grid {
    grid-template-columns: 1fr;
  }

  .oa-lite-detail-grid > aside.oa-lite-detail-card {
    position: static;
    max-height: none;
  }
}

@media (max-width: 768px) {
  .oa-lite-process-head {
    flex-direction: column;
  }

  .oa-lite-detail-actions {
    justify-content: flex-start;
  }

  .oa-lite-process-name {
    font-size: 18px;
  }
}
</style>
