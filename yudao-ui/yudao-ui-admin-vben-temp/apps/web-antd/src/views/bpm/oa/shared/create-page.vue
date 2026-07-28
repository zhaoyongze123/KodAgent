<script lang="ts" setup>
import type { BpmOACommonApi, OAModuleApiKey } from '#/api/bpm/oa/common';
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';

import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';

import { confirm, Page, useVbenForm } from '@vben/common-ui';
import { BpmCandidateStrategyEnum, BpmNodeIdEnum } from '@vben/constants';
import { useTabs } from '@vben/hooks';
import { IconifyIcon } from '@vben/icons';

import { Button, Col, message, Row, Space } from 'ant-design-vue';

import { createAttendance, getAttendance } from '#/api/bpm/oa/attendance';
import { getProcessDefinition } from '#/api/bpm/definition';
import { createExpense, getExpense } from '#/api/bpm/oa/expense';
import { createLeaveCancel, getLeaveCancel } from '#/api/bpm/oa/leave-cancel';
import { createOvertime, getOvertime } from '#/api/bpm/oa/overtime';
import { createOuting, getOuting } from '#/api/bpm/oa/outing';
import { createSeal, getSeal } from '#/api/bpm/oa/seal';
import { createTrip, getTrip } from '#/api/bpm/oa/trip';
import { getApprovalDetail as getApprovalDetailApi } from '#/api/bpm/processInstance';
import { $t } from '#/locales';
import { router } from '#/router';
import { buildApprovalEntryBackRoute } from '#/utils/kod-entry';
import ProcessInstanceTimeline from '#/views/bpm/processInstance/detail/modules/time-line.vue';

import { getOAModuleViewConfig } from './config';
import { useFormSchema } from './data';

const props = defineProps<{
  moduleKey: OAModuleApiKey;
}>();

const { closeCurrentTab, getTabDisableState } = useTabs();
const { query } = useRoute();
const config = getOAModuleViewConfig(props.moduleKey);
const createRequestMap: Partial<Record<
  OAModuleApiKey,
  (data: BpmOACommonApi.OARecord) => Promise<unknown>
>> = {
  attendance: (data) => createAttendance(data),
  expense: (data) => createExpense(data),
  leaveCancel: (data) => createLeaveCancel(data),
  overtime: (data) => createOvertime(data),
  outing: (data) => createOuting(data),
  seal: (data) => createSeal(data as any),
  trip: (data) => createTrip(data),
};
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

const formLoading = ref(false);
const processTimeLineLoading = ref(false);
const startUserSelectTasks = ref<BpmProcessInstanceApi.ApprovalNodeInfo[]>([]);
const startUserSelectAssignees = ref<Record<string, number[]>>({});
const activityNodes = ref<BpmProcessInstanceApi.ApprovalNodeInfo[]>([]);
const processDefinitionId = ref('');
const formData = ref<Partial<BpmOACommonApi.OARecord>>({});

const getTitle = computed(() => {
  return formData.value?.id
    ? `重新发起${config.title}`
    : $t('ui.actionTitle.create', [config.title]);
});

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: {
      class: 'w-full',
    },
    formItemClass: 'col-span-2',
    labelWidth: 100,
  },
  layout: 'horizontal',
  schema: useFormSchema(config),
  showDefaultActions: false,
});

async function closeCurrentTabIfPossible() {
  if (!getTabDisableState().disabledCloseCurrent) {
    await closeCurrentTab();
  }
}

function shouldReturnToOaLite() {
  const returnTo = Array.isArray(query.returnTo) ? query.returnTo[0] : query.returnTo;
  return returnTo === 'oa-lite';
}

function buildOaLiteRoute() {
  return buildApprovalEntryBackRoute(query);
}

async function getApprovalDetail() {
  processTimeLineLoading.value = true;
  try {
    const processVariables = config.buildProcessVariables
      ? config.buildProcessVariables((await formApi.getValues()) as Record<string, any>)
      : {};
    const data = await getApprovalDetailApi({
      processDefinitionId: processDefinitionId.value,
      activityId: BpmNodeIdEnum.START_USER_NODE_ID,
      processVariablesStr: JSON.stringify(processVariables),
    });
    if (!data) {
      message.error('查询不到审批详情信息');
      return;
    }
    activityNodes.value = data.activityNodes;
    startUserSelectTasks.value = data.activityNodes?.filter(
      (node) =>
        BpmCandidateStrategyEnum.START_USER_SELECT === node.candidateStrategy,
    );
    startUserSelectAssignees.value = {};
    for (const node of startUserSelectTasks.value) {
      startUserSelectAssignees.value[node.id] = [];
    }
  } finally {
    processTimeLineLoading.value = false;
  }
}

function selectUserConfirm(id: string, userList: any[]) {
  startUserSelectAssignees.value[id] = userList?.map((item: any) => item.id);
}

async function loadDetail(id: number) {
  try {
    formLoading.value = true;
    const request = detailRequestMap[props.moduleKey];
    if (!request) {
      message.error(`OA ${config.title}未配置详情接口`);
      return;
    }
    const data = await request(id);
    if (!data) {
      message.error(`重新发起${config.title}失败，原因：原申请不存在`);
      return;
    }
    formData.value = {
      ...formData.value,
      ...data,
    };
    await formApi.setValues(data);
  } finally {
    formLoading.value = false;
  }
}

async function onSubmit() {
  const { valid } = await formApi.validate();
  if (!valid) {
    return;
  }
  for (const userTask of startUserSelectTasks.value) {
    const selectedAssignees = startUserSelectAssignees.value[userTask.id] ?? [];
    if (
      Array.isArray(selectedAssignees) &&
      selectedAssignees.length === 0
    ) {
      return message.warning(`请选择${userTask.name}的审批人`);
    }
  }

  const values = (await formApi.getValues()) as BpmOACommonApi.OARecord;
  const submitData: BpmOACommonApi.OARecord = {
    ...values,
    endTime: values.endTime ? Number(values.endTime) : values.endTime,
    reason: typeof values.reason === 'string' ? values.reason.trim() : values.reason,
    startTime: values.startTime ? Number(values.startTime) : values.startTime,
  };
  if (startUserSelectTasks.value.length > 0) {
    submitData.startUserSelectAssignees = startUserSelectAssignees.value;
  }

  try {
    formLoading.value = true;
    const request = createRequestMap[props.moduleKey];
    if (!request) {
      message.error(`OA ${config.title}未配置提交流程`);
      return;
    }
    await request(submitData);
    message.success($t('ui.actionMessage.operationSuccess'));
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

function onBack() {
  confirm({
    content: '确定要返回上一页吗？请先保存您填写的信息！',
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

onMounted(async () => {
  const processDefinitionDetail: any = await getProcessDefinition(
    undefined,
    config.processDefinitionKey,
  );
  if (!processDefinitionDetail) {
    message.error(`OA ${config.title}的流程模型未配置，请检查`);
    return;
  }
  processDefinitionId.value = processDefinitionDetail.id;

  if (query.id) {
    await loadDetail(Number(query.id));
  }

  await getApprovalDetail();
});
</script>

<template>
  <Page>
    <Row :gutter="20" class="oa-bpm-create-shell">
      <Col :span="16">
        <section class="oa-bpm-create-panel" v-loading="formLoading">
          <header class="oa-bpm-create-panel-head">
            <div>
              <h3 class="oa-bpm-create-title">{{ getTitle }}</h3>
            </div>
            <Button type="default" @click="onBack">
              <IconifyIcon icon="lucide:arrow-left" />
              返回
            </Button>
          </header>
          <Form />
          <div class="oa-bpm-create-actions">
            <Space warp :size="12">
              <Button type="primary" @click="onSubmit" :loading="formLoading">
                提交
              </Button>
            </Space>
          </div>
        </section>
      </Col>
      <Col :span="8">
        <aside class="oa-bpm-create-panel" v-loading="processTimeLineLoading">
          <ProcessInstanceTimeline
            :activity-nodes="activityNodes"
            :show-status-icon="false"
            @select-user-confirm="selectUserConfirm"
          />
        </aside>
      </Col>
    </Row>
  </Page>
</template>

<style lang="scss" scoped>
.oa-bpm-create-shell {
  align-items: start;
}

.oa-bpm-create-panel {
  min-width: 0;
  border-top: 1px solid var(--oa-shell-border);
  padding-top: 18px;
}

.oa-bpm-create-panel-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--oa-shell-border);
  margin-bottom: 18px;
}

.oa-bpm-create-eyebrow {
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.oa-bpm-create-title {
  margin: 6px 0 0;
  color: var(--oa-ink);
  font-size: 18px;
  font-weight: 600;
}

.oa-bpm-create-actions {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--oa-shell-border);
}
</style>
