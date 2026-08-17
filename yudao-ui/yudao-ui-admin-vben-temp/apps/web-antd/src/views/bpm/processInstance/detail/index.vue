<script lang="ts" setup>
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';
import type { SystemUserApi } from '#/api/system/user';

import { nextTick, onMounted, ref, shallowRef, watch } from 'vue';

import { Page, useVbenModal } from '@vben/common-ui';
import {
  BpmFieldPermissionType,
  BpmModelFormType,
  BpmModelType,
  BpmProcessInstanceStatus,
  DICT_TYPE,
} from '@vben/constants';
import {
  IconifyIcon,
  SvgBpmApproveIcon,
  SvgBpmCancelIcon,
  SvgBpmRejectIcon,
  SvgBpmRunningIcon,
} from '@vben/icons';
import { formatDateTime } from '@vben/utils';

import { Avatar, Col, message, Row, TabPane, Tabs } from 'ant-design-vue';

import {
  getApprovalDetail as getApprovalDetailApi,
  getProcessInstanceBpmnModelView,
} from '#/api/bpm/processInstance';
import { getSimpleUserList } from '#/api/system/user';
import DictTag from '#/components/dict-tag/dict-tag.vue';
import {
  getFlowFormLayoutMode,
  normalizeFlowFormRulesForDisplay,
  setConfAndFields2,
} from '#/components/form-create';
import { registerComponent } from '#/utils';

import ProcessInstanceBpmnViewer from './modules/bpm-viewer.vue';
import ProcessInstanceOperationButton from './modules/operation-button.vue';
import ProcessssPrint from './modules/process-print.vue';
import ProcessInstanceSimpleViewer from './modules/simple-bpm-viewer.vue';
import BpmProcessInstanceTaskList from './modules/task-list.vue';
import ProcessInstanceTimeline from './modules/time-line.vue';

defineOptions({ name: 'BpmProcessInstanceDetail' });

const props = defineProps<{
  activityId?: string; // 流程活动编号，用于抄送查看
  id: string; // 流程实例的编号
  taskId?: string; // 任务编号
}>();

const processInstanceLoading = ref(false); // 流程实例的加载中
const processInstance = ref<BpmProcessInstanceApi.ProcessInstance>(); // 流程实例
const processDefinition = ref<any>({}); // 流程定义
const processModelView = ref<any>({}); // 流程模型视图
const operationButtonRef = ref(); // 操作按钮组件 ref
const activeTab = ref('form');
const taskListRef = ref();
const auditIconsMap: {
  [key: string]:
    | typeof SvgBpmApproveIcon
    | typeof SvgBpmCancelIcon
    | typeof SvgBpmRejectIcon
    | typeof SvgBpmRunningIcon;
} = {
  [BpmProcessInstanceStatus.RUNNING]: SvgBpmRunningIcon,
  [BpmProcessInstanceStatus.APPROVE]: SvgBpmApproveIcon,
  [BpmProcessInstanceStatus.REJECT]: SvgBpmRejectIcon,
  [BpmProcessInstanceStatus.CANCEL]: SvgBpmCancelIcon,
};
const activityNodes = ref<BpmProcessInstanceApi.ApprovalNodeInfo[]>([]); // 审批节点信息
const userOptions = ref<SystemUserApi.User[]>([]); // 用户列表

const fApi = ref<any>();
const detailForm = ref({
  rule: [],
  option: {},
  value: {},
}); // 流程实例的表单详情
const writableFields: Array<string> = []; // 表单可以编辑的字段

const BusinessFormComponent = shallowRef<any>(null); // 异步组件(业务表单）

const businessKeyIsValid = () => {
  const businessKey = processInstance.value?.businessKey;
  return typeof businessKey === 'string'
    ? /^\d+$/.test(businessKey)
    : typeof businessKey === 'number' && Number.isSafeInteger(businessKey);
};

/** 获取详情 */
async function getDetail() {
  // 获得审批详情
  await getApprovalDetail();
  // 获得流程模型视图
  await getProcessModelView();
}

/** 获得审批详情 */
async function getApprovalDetail() {
  processInstanceLoading.value = true;
  try {
    const param = {
      processInstanceId: props.id,
      activityId: props.activityId,
      taskId: props.taskId,
    };
    const data = await getApprovalDetailApi(param);
    if (!data) {
      message.error('查询不到审批详情信息！');
    }
    if (!data.processDefinition || !data.processInstance) {
      message.error('查询不到流程信息！');
    }

    processInstance.value = data.processInstance;
    processDefinition.value = data.processDefinition;

    // 设置表单信息
    if (processDefinition.value.formType === BpmModelFormType.NORMAL) {
      // 获取表单字段权限
      const formFieldsPermission = data.formFieldsPermission;
      // 清空可编辑字段为空
      writableFields.splice(0);
      if (detailForm.value.rule?.length > 0) {
        // 避免刷新 form-create 显示不了
        detailForm.value.value = processInstance.value.formVariables;
      } else {
        setConfAndFields2(
          detailForm,
          processDefinition.value.formConf,
          processDefinition.value.formFields,
          processInstance.value.formVariables,
        );
        const layoutMode = getFlowFormLayoutMode(detailForm.value.option);
        detailForm.value.rule = normalizeFlowFormRulesForDisplay(
          detailForm.value.rule,
          layoutMode,
        );
      }
      await nextTick();
      fApi.value?.btn.show(false);
      fApi.value?.resetBtn.show(false);
      fApi.value?.disabled(true);
      // 设置表单字段权限
      if (formFieldsPermission) {
        Object.keys(data.formFieldsPermission).forEach((item) => {
          setFieldPermission(item, formFieldsPermission[item]);
        });
      }
    } else {
      // 注意：data.processDefinition.formCustomViewPath 是组件的全路径，例如说：/crm/contract/detail/index.vue
      BusinessFormComponent.value = registerComponent(
        data?.processDefinition?.formCustomViewPath || '',
      );
    }

    // 获取审批节点，显示 Timeline 的数据
    activityNodes.value = data.activityNodes;

    // 获取待办任务显示操作按钮
    operationButtonRef.value?.loadTodoTask(data.todoTask);
  } catch {
    message.error('获取审批详情失败！');
  } finally {
    processInstanceLoading.value = false;
  }
}

/** 获取流程模型视图*/
async function getProcessModelView() {
  if (BpmModelType.BPMN === processDefinition.value?.modelType) {
    // 重置，解决 BPMN 流程图刷新不会重新渲染问题
    processModelView.value = {
      bpmnXml: '',
    };
  }
  const data = await getProcessInstanceBpmnModelView(props.id);
  if (data) {
    processModelView.value = data;
  }
}

/** 设置表单权限 */
function setFieldPermission(field: string, permission: string) {
  if (permission === BpmFieldPermissionType.READ) {
    fApi.value?.disabled(true, field);
  }
  if (permission === BpmFieldPermissionType.WRITE) {
    fApi.value?.disabled(false, field);
    // 加入可以编辑的字段
    writableFields.push(field);
  }
  if (permission === BpmFieldPermissionType.NONE) {
    fApi.value?.hidden(true, field);
  }
}

/** 操作成功后刷新 */
const refresh = () => {
  // 重新获取详情
  getDetail();
};

const [PrintModal, printModalApi] = useVbenModal({
  connectedComponent: ProcessssPrint,
  destroyOnClose: true,
});

/** 打开打印对话框 */
function handlePrint() {
  printModalApi.setData({ processInstanceId: props.id }).open();
}

/** 监听 Tab 切换，当切换到 "record" 标签时刷新任务列表 */
watch(
  () => activeTab.value,
  async (newVal) => {
    if (newVal === 'record') {
      // 如果切换到流转记录标签，刷新任务列表
      await nextTick();
      taskListRef.value?.refresh();
    }
  },
);
const loading = ref(false);
/** 初始化 */
onMounted(async () => {
  try {
    loading.value = true;
    await getDetail();
    // 获得用户列表
    userOptions.value = await getSimpleUserList();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <Page auto-content-height v-loading="loading">
    <section class="oa-process-detail-page">
      <header class="oa-process-detail-head">
        <div class="oa-process-detail-meta">
          <span class="oa-process-detail-id">编号：{{ id || '-' }}</span>
          <button
            type="button"
            class="oa-process-detail-print"
            aria-label="打印流程"
            @click="handlePrint"
          >
            <IconifyIcon icon="lucide:printer" />
          </button>
        </div>

        <div class="oa-process-detail-summary">
          <div class="oa-process-detail-title-row">
            <div class="oa-process-detail-title">
              {{ processInstance?.name }}
            </div>
            <DictTag
              v-if="processInstance?.status"
              :type="DICT_TYPE.BPM_PROCESS_INSTANCE_STATUS"
              :value="processInstance.status"
            />
          </div>

          <div class="oa-process-detail-author">
            <div class="oa-process-detail-author-user">
              <Avatar
                :size="28"
                v-if="processInstance?.startUser?.avatar"
                :src="processInstance?.startUser?.avatar"
              />
              <Avatar
                :size="28"
                v-else-if="processInstance?.startUser?.nickname"
              >
                {{ processInstance?.startUser?.nickname.substring(0, 1) }}
              </Avatar>
              <span class="text-sm">
                {{ processInstance?.startUser?.nickname }}
              </span>
            </div>
            <div class="oa-process-detail-author-time">
              {{ formatDateTime(processInstance?.startTime) }} 提交
            </div>
          </div>

          <component
            v-if="processInstance?.status"
            :is="auditIconsMap[processInstance?.status]"
            class="oa-process-detail-status-mark"
          />
        </div>
      </header>

      <div class="oa-process-detail-body">
        <Tabs v-model:active-key="activeTab">
          <TabPane tab="审批详情" key="form" class="pb-20 pr-3">
            <div class="oa-process-detail-pane">
              <Row :gutter="[48, 24]">
                <Col :xs="24" :sm="24" :md="18" :lg="18" :xl="16">
                  <!-- 流程表单 -->
                  <div
                    v-if="
                      processDefinition?.formType === BpmModelFormType.NORMAL
                    "
                  >
                    <form-create
                      v-model="detailForm.value"
                      v-model:api="fApi"
                      :option="detailForm.option"
                      :rule="detailForm.rule"
                    />
                  </div>
                  <div
                    v-else-if="
                      processDefinition?.formType === BpmModelFormType.CUSTOM
                    "
                  >
                    <BusinessFormComponent
                      v-if="BusinessFormComponent && businessKeyIsValid()"
                      :id="String(processInstance?.businessKey)"
                    />
                    <div v-else class="py-8 text-center text-gray-500">
                      暂无可加载的业务表单信息
                    </div>
                  </div>
                </Col>
                <Col :xs="24" :sm="24" :md="6" :lg="6" :xl="8">
                  <ProcessInstanceTimeline :activity-nodes="activityNodes" />
                </Col>
              </Row>
            </div>
          </TabPane>
          <TabPane
            tab="流程图"
            key="diagram"
            class="pb-20 pr-3"
            :force-render="true"
          >
            <ProcessInstanceSimpleViewer
              v-show="
                processDefinition.modelType &&
                processDefinition.modelType === BpmModelType.SIMPLE
              "
              :loading="processInstanceLoading"
              :model-view="processModelView"
            />
            <ProcessInstanceBpmnViewer
              v-show="
                processDefinition.modelType &&
                processDefinition.modelType === BpmModelType.BPMN
              "
              :loading="processInstanceLoading"
              :model-view="processModelView"
            />
          </TabPane>
          <TabPane tab="流转记录" key="record" class="pb-20 pr-3">
            <BpmProcessInstanceTaskList
              ref="taskListRef"
              :loading="processInstanceLoading"
              :id="id"
            />
          </TabPane>
          <!-- TODO 待开发 -->
          <TabPane tab="流转评论" key="comment" v-if="false" class="pr-3">
            <div class="h-full">待开发</div>
          </TabPane>
        </Tabs>
      </div>

      <footer class="oa-process-detail-actions">
        <ProcessInstanceOperationButton
          ref="operationButtonRef"
          :process-instance="processInstance"
          :process-definition="processDefinition"
          :user-options="userOptions"
          :normal-form="detailForm"
          :normal-form-api="fApi"
          :writable-fields="writableFields"
          @success="refresh"
        />
      </footer>
    </section>
    <!-- 打印对话框 -->
    <PrintModal />
  </Page>
</template>

<style lang="scss" scoped>
.oa-process-detail-page {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
}

.oa-process-detail-head {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0 18px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-process-detail-meta {
  display: flex;
  align-items: center;
  gap: 12px;
}

.oa-process-detail-id {
  color: var(--oa-ink-faint);
  font-size: 12px;
}

.oa-process-detail-print {
  display: inline-flex;
  width: 28px;
  height: 28px;
  align-items: center;
  justify-content: center;
  border: 0;
  background: transparent;
  color: var(--oa-ink-soft);
}

.oa-process-detail-summary {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.oa-process-detail-title-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.oa-process-detail-title {
  color: var(--oa-ink);
  font-size: 26px;
  font-weight: 600;
  line-height: 1.2;
}

.oa-process-detail-author {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
}

.oa-process-detail-author-user {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding-right: 16px;
  border-right: 1px solid var(--oa-shell-border);
}

.oa-process-detail-author-time {
  color: var(--oa-ink-soft);
  font-size: 13px;
}

.oa-process-detail-status-mark {
  position: absolute;
  top: -12px;
  right: 0;
  width: 112px;
  height: 112px;
  opacity: 0.9;
  pointer-events: none;
}

.oa-process-detail-body {
  min-height: 0;
  flex: 1;
  padding-top: 18px;
}

.oa-process-detail-pane {
  padding-top: 4px;
}

.oa-process-detail-actions {
  padding: 14px 0 0;
  border-top: 1px solid var(--oa-shell-border);
}

:deep(.ant-tabs) {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;

  .ant-tabs-content {
    height: 100%;
    min-height: 0;
  }
}

:deep(.ant-tabs-nav) {
  margin-bottom: 18px;
}

:deep(.ant-tabs-tab) {
  padding-right: 2px;
  padding-left: 2px;
}

:deep(.ant-tabs-tabpane) {
  height: 100%;
  overflow-y: auto;
}
</style>
