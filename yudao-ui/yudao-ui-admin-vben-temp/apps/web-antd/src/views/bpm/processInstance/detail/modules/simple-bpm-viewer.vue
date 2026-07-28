<script lang="ts" setup>
import type { SimpleFlowNode } from '#/views/bpm/components/simple-process-design';

import { ref, watch } from 'vue';

import { BpmNodeTypeEnum, BpmTaskStatusEnum } from '@vben/constants';

import { SimpleProcessViewer } from '#/views/bpm/components/simple-process-design';

defineOptions({ name: 'BpmProcessInstanceSimpleViewer' });

const props = withDefaults(
  defineProps<{
    loading?: boolean; // 是否加载中
    modelView?: any;
    simpleJson?: string; // Simple 模型结构数据 (json 格式)
  }>(),
  {
    loading: false,
    modelView: () => ({}),
    simpleJson: '',
  },
);

const simpleModel = ref<any>({});
const tasks = ref([]); // 用户任务
const processInstance = ref(); // 流程实例

/** 监控模型视图 包括任务列表、进行中的活动节点编号等 */
watch(
  () => props.modelView,
  async (newModelView) => {
    if (newModelView) {
      tasks.value = Array.isArray(newModelView.tasks) ? newModelView.tasks : [];
      processInstance.value = newModelView.processInstance;
      simpleModel.value = newModelView.simpleModel || {};
      // 已经拒绝的活动节点编号集合，只包括 UserTask
      const rejectedTaskActivityIds: string[] = Array.isArray(
        newModelView.rejectedTaskActivityIds,
      )
        ? newModelView.rejectedTaskActivityIds
        : [];
      // 进行中的活动节点编号集合， 只包括 UserTask
      const unfinishedTaskActivityIds: string[] = Array.isArray(
        newModelView.unfinishedTaskActivityIds,
      )
        ? newModelView.unfinishedTaskActivityIds
        : [];
      // 已经完成的活动节点编号集合， 包括 UserTask、Gateway 等
      const finishedActivityIds: string[] = Array.isArray(
        newModelView.finishedTaskActivityIds,
      )
        ? newModelView.finishedTaskActivityIds
        : [];
      // 已经完成的连线节点编号集合，只包括 SequenceFlow
      const finishedSequenceFlowActivityIds: string[] = Array.isArray(
        newModelView.finishedSequenceFlowActivityIds,
      )
        ? newModelView.finishedSequenceFlowActivityIds
        : [];
      setSimpleModelNodeTaskStatus(
        simpleModel.value,
        newModelView.processInstance?.status,
        rejectedTaskActivityIds,
        unfinishedTaskActivityIds,
        finishedActivityIds,
        finishedSequenceFlowActivityIds,
      );
    }
  },
  { immediate: true },
);

/** 监控模型结构数据 */
watch(
  () => props.simpleJson,
  async (value) => {
    if (value) {
      simpleModel.value = JSON.parse(value);
    }
  },
  { immediate: true },
);

const setSimpleModelNodeTaskStatus = (
  simpleModel: SimpleFlowNode | undefined,
  processStatus: number,
  rejectedTaskActivityIds: string[],
  unfinishedTaskActivityIds: string[],
  finishedActivityIds: string[],
  finishedSequenceFlowActivityIds: string[],
) => {
  if (!simpleModel) {
    return;
  }
  // 结束节点
  if (simpleModel.type === BpmNodeTypeEnum.END_EVENT_NODE) {
    simpleModel.activityStatus = finishedActivityIds.includes(simpleModel.id)
      ? processStatus
      : BpmTaskStatusEnum.NOT_START;
    return;
  }
  // 审批节点
  if (
    simpleModel.type === BpmNodeTypeEnum.START_USER_NODE ||
    simpleModel.type === BpmNodeTypeEnum.USER_TASK_NODE ||
    simpleModel.type === BpmNodeTypeEnum.TRANSACTOR_NODE ||
    simpleModel.type === BpmNodeTypeEnum.CHILD_PROCESS_NODE
  ) {
    simpleModel.activityStatus = BpmTaskStatusEnum.NOT_START;
    if (rejectedTaskActivityIds.includes(simpleModel.id)) {
      simpleModel.activityStatus = BpmTaskStatusEnum.REJECT;
    } else if (unfinishedTaskActivityIds.includes(simpleModel.id)) {
      simpleModel.activityStatus = BpmTaskStatusEnum.RUNNING;
    } else if (finishedActivityIds.includes(simpleModel.id)) {
      simpleModel.activityStatus = BpmTaskStatusEnum.APPROVE;
    }
    // TODO 是不是还缺一个 cancel 的状态 @jason：
  }
  // 抄送节点
  if (simpleModel.type === BpmNodeTypeEnum.COPY_TASK_NODE) {
    // 抄送节点,只有通过和未执行状态
    simpleModel.activityStatus = finishedActivityIds.includes(simpleModel.id)
      ? BpmTaskStatusEnum.APPROVE
      : BpmTaskStatusEnum.NOT_START;
  }
  // 延迟器节点
  if (simpleModel.type === BpmNodeTypeEnum.DELAY_TIMER_NODE) {
    // 延迟器节点,只有通过和未执行状态
    simpleModel.activityStatus = finishedActivityIds.includes(simpleModel.id)
      ? BpmTaskStatusEnum.APPROVE
      : BpmTaskStatusEnum.NOT_START;
  }
  // 触发器节点
  if (simpleModel.type === BpmNodeTypeEnum.TRIGGER_NODE) {
    // 触发器节点,只有通过和未执行状态
    simpleModel.activityStatus = finishedActivityIds.includes(simpleModel.id)
      ? BpmTaskStatusEnum.APPROVE
      : BpmTaskStatusEnum.NOT_START;
  }

  // 条件节点对应 SequenceFlow
  if (simpleModel.type === BpmNodeTypeEnum.CONDITION_NODE) {
    // 条件节点,只有通过和未执行状态
    simpleModel.activityStatus = finishedSequenceFlowActivityIds.includes(
      simpleModel.id,
    )
      ? BpmTaskStatusEnum.APPROVE
      : BpmTaskStatusEnum.NOT_START;
  }
  // 网关节点
  if (
    simpleModel.type === BpmNodeTypeEnum.CONDITION_BRANCH_NODE ||
    simpleModel.type === BpmNodeTypeEnum.PARALLEL_BRANCH_NODE ||
    simpleModel.type === BpmNodeTypeEnum.INCLUSIVE_BRANCH_NODE ||
    simpleModel.type === BpmNodeTypeEnum.ROUTER_BRANCH_NODE
  ) {
    // 网关节点。只有通过和未执行状态
    simpleModel.activityStatus = finishedActivityIds.includes(simpleModel.id)
      ? BpmTaskStatusEnum.APPROVE
      : BpmTaskStatusEnum.NOT_START;
    simpleModel.conditionNodes?.forEach((node) => {
      setSimpleModelNodeTaskStatus(
        node,
        processStatus,
        rejectedTaskActivityIds,
        unfinishedTaskActivityIds,
        finishedActivityIds,
        finishedSequenceFlowActivityIds,
      );
    });
  }

  setSimpleModelNodeTaskStatus(
    simpleModel.childNode,
    processStatus,
    rejectedTaskActivityIds,
    unfinishedTaskActivityIds,
    finishedActivityIds,
    finishedSequenceFlowActivityIds,
  );
};
</script>
<template>
  <div v-loading="loading" class="oa-process-viewer-shell">
    <div class="oa-process-viewer-body">
      <SimpleProcessViewer
        :flow-node="simpleModel"
        :tasks="tasks"
        :process-instance="processInstance"
      />
    </div>
  </div>
</template>

<style scoped>
.oa-process-viewer-shell {
  display: flex;
  min-height: 520px;
  flex-direction: column;
  min-width: 0;
  border-top: 1px solid var(--oa-shell-border);
  background: transparent;
}

.oa-process-viewer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 0 14px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-process-viewer-eyebrow {
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.oa-process-viewer-title {
  margin-top: 6px;
  color: var(--oa-ink);
  font-size: 18px;
  font-weight: 600;
}

.oa-process-viewer-caption {
  color: var(--oa-ink-soft);
  font-size: 12px;
  line-height: 1.6;
  text-align: right;
}

.oa-process-viewer-body {
  flex: 1;
  min-height: 0;
  padding: 18px 0 0;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--oa-grid-line) 100%, transparent),
      color-mix(in srgb, var(--oa-grid-line) 100%, transparent)
    )
    0 0 / 100% 1px no-repeat;
}

.oa-process-viewer-body :deep(.simple-process-viewer) {
  border: 0;
  border-radius: 0;
  background: transparent;
}
</style>
