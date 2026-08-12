<script lang="ts" setup>
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';

import { computed, nextTick, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import {
  BpmCandidateStrategyEnum,
  BpmFieldPermissionType,
  BpmModelFormType,
  BpmNodeIdEnum,
} from '@vben/constants';
import { useTabs } from '@vben/hooks';
import { IconifyIcon } from '@vben/icons';

import { Button, Col, message, Row, Space } from 'ant-design-vue';

import {
  createProcessInstance,
  getApprovalDetail as getApprovalDetailApi,
} from '#/api/bpm/processInstance';
import {
  decodeFields,
  getFlowFormLayoutMode,
  normalizeFlowFormRulesForDisplay,
  setConfAndFields2,
} from '#/components/form-create';
import { router } from '#/router';
import ProcessInstanceTimeline from '#/views/bpm/processInstance/detail/modules/time-line.vue';

/** 类型定义 */
interface ProcessFormData {
  rule: any[];
  option: Record<string, any>;
  value: Record<string, any>;
}

interface UserTask {
  id: number;
  name: string;
}

defineOptions({ name: 'BpmProcessInstanceCreateForm' });

const props = defineProps({
  selectProcessDefinition: {
    type: Object,
    required: true,
  },
});

const emit = defineEmits(['cancel']);
const route = useRoute();
const { closeCurrentTab, getTabDisableState } = useTabs();

const getTitle = computed(() => {
  return `流程表单 - ${props.selectProcessDefinition.name}`;
});
const isOaLiteMode = computed(() => shouldReturnToOaLite());
const submitButtonText = computed(() => (isOaLiteMode.value ? '提交' : '发起'));

const detailForm = ref<ProcessFormData>({
  rule: [],
  option: {},
  value: {},
});
const fApi = ref<any>();

const startUserSelectTasks = ref<UserTask[]>([]);
const startUserSelectAssignees = ref<Record<string, string[]>>({});
const tempStartUserSelectAssignees = ref<Record<string, string[]>>({});

const activityNodes = ref<BpmProcessInstanceApi.ApprovalNodeInfo[]>([]);
const processInstanceStartLoading = ref(false);
const initializedDefinitionId = ref<string>();

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

/** 提交按钮 */
async function submitForm() {
  if (!fApi.value || !props.selectProcessDefinition) {
    return;
  }
  // 流程表单校验
  await fApi.value.validate();
  // 校验指定审批人
  if (startUserSelectTasks.value?.length > 0) {
    for (const userTask of startUserSelectTasks.value) {
      const assignees = startUserSelectAssignees.value[userTask.id];
      if (Array.isArray(assignees) && assignees.length === 0) {
        message.warning(`请选择${userTask.name}的候选人`);
        return;
      }
    }
  }

  processInstanceStartLoading.value = true;
  try {
    // 提交请求
    await createProcessInstance({
      processDefinitionId: props.selectProcessDefinition.id,
      variables: detailForm.value.value,
      startUserSelectAssignees: startUserSelectAssignees.value,
    });
    // 关闭并提示
    message.success('发起流程成功');
    await closeCurrentTabIfPossible();
    await router.push(
      shouldReturnToOaLite()
        ? { name: 'OALite' }
        : { name: 'BpmProcessInstanceMy' },
    );
  } finally {
    processInstanceStartLoading.value = false;
  }
}

/** 设置表单信息、获取流程图数据 */
async function initProcessInfo(row: any, formVariables?: any) {
  initializedDefinitionId.value = row?.id;
  // 重置指定审批人
  startUserSelectTasks.value = [];
  startUserSelectAssignees.value = {};
  tempStartUserSelectAssignees.value = {};
  detailForm.value = {
    rule: [],
    option: {},
    value: {},
  };
  activityNodes.value = [];

  // 情况一：流程表单
  if (row.formType === BpmModelFormType.NORMAL) {
    // 设置表单
    // 注意：需要从 formVariables 中，移除不在 row.formFields 的值。
    // 原因是：后端返回的 formVariables 里面，会有一些非表单的信息。例如说，某个流程节点的审批人。
    //        这样，就可能导致一个流程被审批不通过后，重新发起时，会直接后端报错！！！

    // 解析表单字段列表（不创建实例，避免重复渲染）
    const decodedFields = decodeFields(row.formFields);
    const allowedFields = new Set(
      decodedFields.map((field: any) => field.field).filter(Boolean),
    );

    // 过滤掉不允许的字段
    if (formVariables) {
      for (const key in formVariables) {
        if (!allowedFields.has(key)) {
          delete formVariables[key];
        }
      }
    }

    setConfAndFields2(detailForm, row.formConf, row.formFields, formVariables);

    // 布局是流程表单配置的一部分：单列、两列和设计器的自定义栅格都直接生效。
    // 不能在发起页强制改写，否则编辑器配置永远无法展示出来。
    const layoutMode = getFlowFormLayoutMode(detailForm.value.option);
    detailForm.value.option = {
      ...detailForm.value.option,
      row: {
        ...(detailForm.value.option.row || {}),
        gutter: 16,
      },
    };
    detailForm.value.rule = normalizeFlowFormRulesForDisplay(
      detailForm.value.rule,
      layoutMode,
    );

    // 在配置中禁用 form-create 自带的提交和重置按钮
    detailForm.value.option = {
      ...detailForm.value.option,
      submitBtn: false,
      resetBtn: false,
    };

    await nextTick();

    // 获取流程审批信息,当再次发起时，流程审批节点要根据原始表单参数预测出来
    await getApprovalDetail({
      id: row.id,
      processVariablesStr: JSON.stringify(formVariables),
    });

    // 情况二：业务表单
  } else if (row.formCustomCreatePath) {
    await router.push({
      path: row.formCustomCreatePath,
    });
  }
}

/** 预测流程节点会因为输入的参数值而产生新的预测结果值，所以需重新预测一次 */
watch(
  () => props.selectProcessDefinition,
  async (definition) => {
    if (!definition?.id) {
      return;
    }
    if (initializedDefinitionId.value === definition.id) {
      return;
    }
    await initProcessInfo(definition);
  },
  {
    deep: true,
    immediate: true,
  },
);

watch(
  () => detailForm.value.value,
  (newValue) => {
    if (newValue && Object.keys(newValue).length > 0) {
      // 记录之前的节点审批人
      tempStartUserSelectAssignees.value = startUserSelectAssignees.value;
      startUserSelectAssignees.value = {};
      // 加载最新的审批详情
      getApprovalDetail({
        id: props.selectProcessDefinition.id,
        processVariablesStr: JSON.stringify(newValue), // 解决 GET 无法传递对象的问题，后端 String 再转 JSON
      });
    }
  },
  {
    deep: true,
  },
);

/** 获取审批详情 */
async function getApprovalDetail(row: {
  id: string;
  processVariablesStr: string;
}) {
  const data = await getApprovalDetailApi({
    processDefinitionId: row.id,
    activityId: BpmNodeIdEnum.START_USER_NODE_ID,
    processVariablesStr: row.processVariablesStr,
  });
  if (!data) {
    message.error('查询不到审批详情信息！');
    return;
  }

  // 获取审批节点
  activityNodes.value = data.activityNodes;

  // 获取发起人自选的任务
  startUserSelectTasks.value = (data.activityNodes?.filter(
    (node) =>
      BpmCandidateStrategyEnum.START_USER_SELECT === node.candidateStrategy,
  ) || []) as unknown as UserTask[];

  // 恢复之前的选择审批人
  if (startUserSelectTasks.value.length > 0) {
    for (const node of startUserSelectTasks.value) {
      const tempAssignees = tempStartUserSelectAssignees.value[node.id];
      startUserSelectAssignees.value[node.id] = tempAssignees?.length
        ? tempAssignees
        : [];
    }
  }

  // 设置表单字段权限
  const formFieldsPermission = data.formFieldsPermission;
  if (formFieldsPermission) {
    Object.entries(formFieldsPermission).forEach(([field, permission]) => {
      setFieldPermission(field, permission as string);
    });
  }
}

/** 设置表单权限 */
function setFieldPermission(field: string, permission: string) {
  if (permission === BpmFieldPermissionType.READ) {
    fApi.value?.disabled(true, field);
  }
  if (permission === BpmFieldPermissionType.WRITE) {
    fApi.value?.disabled(false, field);
  }
  if (permission === BpmFieldPermissionType.NONE) {
    fApi.value?.hidden(true, field);
  }
}

/** 取消发起审批 */
async function handleCancel() {
  if (shouldReturnToOaLite()) {
    await closeCurrentTabIfPossible();
    await router.push({ name: 'OALite' });
    return;
  }
  emit('cancel');
}

/** 选择发起人 */
function selectUserConfirm(activityId: string, userList: any[]) {
  if (!activityId || !Array.isArray(userList)) return;
  startUserSelectAssignees.value[activityId] = userList.map((item) => item.id);
}

defineExpose({ initProcessInfo });
</script>

<template>
  <section
    class="bpm-create-form-shell"
    :class="{ 'is-oa-lite': isOaLiteMode }"
  >
    <header class="bpm-create-form-header">
      <div>
        <div v-if="!isOaLiteMode" class="bpm-create-form-eyebrow">
          Process Launch
        </div>
        <h2 class="bpm-create-form-title">{{ getTitle }}</h2>
      </div>
      <Space wrap>
        <Button plain type="default" @click="handleCancel">
          <IconifyIcon icon="lucide:arrow-left" />&nbsp; 返回
        </Button>
      </Space>
    </header>

    <section class="bpm-create-form-tabs">
      <div v-if="!isOaLiteMode" class="bpm-create-form-tab-active">
        表单填写
      </div>
      <Row :gutter="[40, 16]" class="bpm-create-form-panel">
        <Col
          :xs="24"
          :sm="24"
          :md="18"
          :lg="18"
          :xl="18"
          class="bpm-create-form-content"
        >
          <form-create
            class="bpm-create-normal-form"
            :rule="detailForm.rule"
            v-model:api="fApi"
            v-model="detailForm.value"
            :option="detailForm.option"
            @submit="submitForm"
          />
        </Col>
        <Col :xs="24" :sm="24" :md="6" :lg="6" :xl="6">
          <ProcessInstanceTimeline
            :activity-nodes="activityNodes"
            @select-user-confirm="selectUserConfirm"
          />
        </Col>
      </Row>
    </section>

    <footer class="bpm-create-form-actions">
      <Space
        wrap
        class="flex w-full"
        :class="isOaLiteMode ? 'justify-start' : 'justify-center'"
      >
        <Button
          plain
          type="primary"
          @click="submitForm"
          :loading="processInstanceStartLoading"
        >
          <IconifyIcon icon="lucide:check" />
          {{ submitButtonText }}
        </Button>
        <Button v-if="!isOaLiteMode" plain type="default" @click="handleCancel">
          <IconifyIcon icon="lucide:x" />
          取消
        </Button>
      </Space>
    </footer>
  </section>
</template>

<style scoped>
.bpm-create-form-shell {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  background: transparent;
}

.bpm-create-form-shell.is-oa-lite {
  gap: 8px;
}

.bpm-create-form-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  padding: 0 0 16px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.bpm-create-form-shell.is-oa-lite .bpm-create-form-header {
  align-items: flex-start;
}

.bpm-create-form-eyebrow {
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 700;
}

.bpm-create-form-title {
  margin: 6px 0 0;
  color: var(--oa-ink);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.02em;
}

.bpm-create-form-shell.is-oa-lite .bpm-create-form-title {
  margin-top: 0;
  font-size: 22px;
}

.bpm-create-form-tabs {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  overflow: auto;
  overscroll-behavior: contain;
  padding-top: 12px;
}

.bpm-create-form-shell.is-oa-lite .bpm-create-form-tabs {
  padding-top: 0;
}

.bpm-create-form-tab-active {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 0 0 12px;
  border-bottom: 3px solid var(--oa-accent);
  color: var(--oa-accent);
  font-size: 15px;
  font-weight: 600;
  line-height: 1;
}

.bpm-create-form-panel {
  min-width: 0;
  padding-top: 8px;
  padding-bottom: 24px;
  border-top: 1px solid var(--oa-shell-border);
  margin-top: -1px;
}

.bpm-create-form-shell.is-oa-lite .bpm-create-form-panel {
  padding-top: 18px;
  border-top: 0;
  margin-top: 0;
}

.bpm-create-form-actions {
  flex: none;
  padding: 16px 0 0;
  border-top: 1px solid var(--oa-shell-border);
}

.bpm-create-form-shell.is-oa-lite .bpm-create-form-actions {
  padding-top: 12px;
}

.bpm-create-normal-form {
  width: 100%;
}

.bpm-create-form-content {
  min-width: 0;
}
</style>
