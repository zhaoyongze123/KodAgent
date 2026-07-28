<!-- 审批详情的右侧：审批流 -->
<script lang="ts" setup>
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';

import { ref } from 'vue';
import { useRouter } from 'vue-router';

import { useVbenModal } from '@vben/common-ui';
import {
  BpmCandidateStrategyEnum,
  BpmNodeTypeEnum,
  BpmTaskStatusEnum,
} from '@vben/constants';
import { IconifyIcon } from '@vben/icons';
import { formatDateTime, isEmpty } from '@vben/utils';

import { Avatar, Button, Image, Timeline, Tooltip } from 'ant-design-vue';

import { UserSelectModal } from '#/views/system/user/components';

defineOptions({ name: 'BpmProcessInstanceTimeline' });

const props = withDefaults(
  defineProps<{
    activityNodes: BpmProcessInstanceApi.ApprovalNodeInfo[]; // 审批节点信息
    enableApproveUserSelect?: boolean; // 是否开启审批人自选功能
    showStatusIcon?: boolean; // 是否显示头像右下角状态图标
  }>(),
  {
    showStatusIcon: true, // 默认值为 true
    enableApproveUserSelect: false, // 默认值为 false
  },
);

const emit = defineEmits<{
  selectUserConfirm: [activityId: string, userList: any[]];
}>();

const { push } = useRouter();

const statusIconMap: Record<
  string,
  { animation?: string; color: string; icon: string }
> = {
  '-2': { color: '#909398', icon: 'lucide:skip-forward' }, // 跳过
  '-1': { color: '#909398', icon: 'lucide:clock-3' }, // 审批未开始
  '0': { color: '#ff943e', icon: 'lucide:loader-circle', animation: 'animate-spin' }, // 待审批
  '1': { color: '#448ef7', icon: 'lucide:loader-circle', animation: 'animate-spin' }, // 审批中
  '2': { color: '#00b32a', icon: 'lucide:check' }, // 审批通过
  '3': { color: '#f46b6c', icon: 'lucide:x' }, // 审批不通过
  '4': { color: '#cccccc', icon: 'lucide:ban' }, // 已取消
  '5': { color: '#f46b6c', icon: 'lucide:corner-up-left' }, // 退回
  '6': { color: '#448ef7', icon: 'lucide:clock-3' }, // 委派中
  '7': { color: '#00b32a', icon: 'lucide:badge-check' }, // 审批通过中
}; // 状态图标映射
const nodeTypeThemeMap = {
  // 结束节点
  [BpmNodeTypeEnum.END_EVENT_NODE]: {
    icon: 'lucide:flag',
    ring: '#E2E8F0',
    shadow: '0 10px 22px rgba(148, 163, 184, 0.2)',
    surface:
      'linear-gradient(180deg, rgba(248,250,252,0.98) 0%, rgba(226,232,240,0.95) 100%)',
  },
  // 开始节点
  [BpmNodeTypeEnum.START_USER_NODE]: {
    icon: 'lucide:user-round',
    ring: '#BBD7FF',
    shadow: '0 12px 26px rgba(37, 99, 235, 0.22)',
    surface:
      'linear-gradient(135deg, #5BB6FF 0%, #2F80FF 55%, #1D5DFF 100%)',
  },
  // 用户任务节点
  [BpmNodeTypeEnum.USER_TASK_NODE]: {
    icon: 'lucide:badge-check',
    ring: '#FFD39F',
    shadow: '0 12px 26px rgba(249, 115, 22, 0.24)',
    surface:
      'linear-gradient(135deg, #FFB45A 0%, #FF8A3D 52%, #FF6A3D 100%)',
  },
  // 事务节点
  [BpmNodeTypeEnum.TRANSACTOR_NODE]: {
    icon: 'lucide:file-pen-line',
    ring: '#FFCDAA',
    shadow: '0 12px 26px rgba(234, 88, 12, 0.22)',
    surface:
      'linear-gradient(135deg, #FFBA7A 0%, #FB923C 52%, #F97316 100%)',
  },
  // 复制任务节点
  [BpmNodeTypeEnum.COPY_TASK_NODE]: {
    icon: 'lucide:copy',
    ring: '#BFE3FF',
    shadow: '0 12px 26px rgba(14, 116, 244, 0.2)',
    surface:
      'linear-gradient(135deg, #53D6FF 0%, #2EA7FF 52%, #2078FF 100%)',
  },
  // 条件分支节点
  [BpmNodeTypeEnum.CONDITION_NODE]: {
    icon: 'lucide:git-branch-plus',
    ring: '#BDEFD8',
    shadow: '0 12px 26px rgba(5, 150, 105, 0.22)',
    surface:
      'linear-gradient(135deg, #61E7BC 0%, #24C38A 52%, #129C74 100%)',
  },
  // 并行分支节点
  [BpmNodeTypeEnum.PARALLEL_BRANCH_NODE]: {
    icon: 'lucide:split',
    ring: '#C8F3DE',
    shadow: '0 12px 26px rgba(22, 163, 74, 0.22)',
    surface:
      'linear-gradient(135deg, #62E4A6 0%, #34C759 52%, #16A34A 100%)',
  },
  // 子流程节点
  [BpmNodeTypeEnum.CHILD_PROCESS_NODE]: {
    icon: 'lucide:workflow',
    ring: '#DDD6FE',
    shadow: '0 12px 26px rgba(109, 40, 217, 0.2)',
    surface:
      'linear-gradient(135deg, #B49CFF 0%, #8B6CFF 52%, #6D4BFF 100%)',
  },
} as Record<
  BpmNodeTypeEnum,
  { icon: string; ring: string; shadow: string; surface: string }
>; // 节点类型图标映射
const onlyStatusIconShow = [-1, 0, 1]; // 只有状态是 -1、0、1 才展示头像右小角状态小 icon

/** 获取审批节点类型图标 */
function getApprovalNodeTypeIcon(nodeType: BpmNodeTypeEnum) {
  return nodeTypeThemeMap[nodeType]?.icon;
}

function getNodeTheme(nodeType: BpmNodeTypeEnum) {
  return (
    nodeTypeThemeMap[nodeType] || {
      icon: 'lucide:circle',
      ring: '#D7E3F4',
      shadow: '0 10px 20px rgba(15, 23, 42, 0.14)',
      surface:
        'linear-gradient(135deg, #93C5FD 0%, #60A5FA 52%, #3B82F6 100%)',
    }
  );
}

/** 获取审批节点图标 */
function getApprovalNodeIcon(taskStatus: number, nodeType: BpmNodeTypeEnum) {
  if (taskStatus === BpmTaskStatusEnum.NOT_START) {
    return statusIconMap[taskStatus]?.icon || 'mdi:clock-outline';
  }
  if (
    [
      BpmNodeTypeEnum.CHILD_PROCESS_NODE,
      BpmNodeTypeEnum.END_EVENT_NODE,
      BpmNodeTypeEnum.START_USER_NODE,
      BpmNodeTypeEnum.TRANSACTOR_NODE,
      BpmNodeTypeEnum.USER_TASK_NODE,
    ].includes(nodeType)
  ) {
    return statusIconMap[taskStatus]?.icon || 'mdi:clock-outline';
  }
  return 'mdi:clock-outline';
}

/** 获取审批节点颜色 */
function getApprovalNodeColor(taskStatus: number) {
  return statusIconMap[taskStatus]?.color;
}

function getApprovalNodeDotStyle(activity: BpmProcessInstanceApi.ApprovalNodeInfo) {
  const theme = getNodeTheme(activity.nodeType);
  const pending =
    activity.status === BpmTaskStatusEnum.NOT_START ||
    activity.status === BpmTaskStatusEnum.CANCEL;
  return {
    background: pending
      ? 'linear-gradient(180deg, rgba(241,245,249,0.98) 0%, rgba(226,232,240,0.98) 100%)'
      : theme.surface,
    borderColor: pending ? 'rgba(148, 163, 184, 0.24)' : theme.ring,
    boxShadow: pending
      ? '0 8px 18px rgba(148, 163, 184, 0.14)'
      : theme.shadow,
    color: pending ? '#94A3B8' : '#FFFFFF',
  };
}

function getApprovalNodeRingStyle(activity: BpmProcessInstanceApi.ApprovalNodeInfo) {
  const theme = getNodeTheme(activity.nodeType);
  return {
    backgroundColor: theme.ring,
  };
}

/** 获取审批节点时间 */
function getApprovalNodeTime(node: BpmProcessInstanceApi.ApprovalNodeInfo) {
  if (node.nodeType === BpmNodeTypeEnum.START_USER_NODE && node.startTime) {
    return formatDateTime(node.startTime);
  }
  if (node.endTime) {
    return formatDateTime(node.endTime);
  }
  if (node.startTime) {
    return formatDateTime(node.startTime);
  }
  return '';
}

function getTimelineUser(task: any) {
  return task?.assigneeUser || task?.ownerUser;
}

function getTimelineUserRole(activity: BpmProcessInstanceApi.ApprovalNodeInfo) {
  return activity.name || '审批节点';
}

function getTimelineUserDept(user: any) {
  return user?.deptName || user?.dept?.name || '';
}

const [UserSelectModalComp, userSelectModalApi] = useVbenModal({
  connectedComponent: UserSelectModal,
  destroyOnClose: true,
});
const selectedActivityNodeId = ref<string>();
const customApproveUsers = ref<Record<string, any[]>>({}); // key：activityId，value：用户列表

/** 打开选择用户弹窗 */
const handleSelectUser = (activityId: string, selectedList: any[]) => {
  selectedActivityNodeId.value = activityId;
  userSelectModalApi
    .setData({ userIds: selectedList.map((item) => item.id) })
    .open();
};

/** 选择用户完成 */
const selectedUsers = ref<number[]>([]);
function handleUserSelectConfirm(userList: any[]) {
  if (!selectedActivityNodeId.value) {
    return;
  }
  customApproveUsers.value[selectedActivityNodeId.value] = userList || [];

  emit('selectUserConfirm', selectedActivityNodeId.value, userList);
}

/** 跳转子流程 */
function handleChildProcess(activity: any) {
  if (!activity.processInstanceId) {
    return;
  }
  push({
    name: 'BpmProcessInstanceDetail',
    query: {
      id: activity.processInstanceId,
    },
  });
}

/** 判断是否需要显示自定义选择审批人 */
function shouldShowCustomUserSelect(
  activity: BpmProcessInstanceApi.ApprovalNodeInfo,
) {
  return (
    isEmpty(activity.tasks) &&
    ((BpmCandidateStrategyEnum.START_USER_SELECT ===
      activity.candidateStrategy &&
      isEmpty(activity.candidateUsers)) ||
      (props.enableApproveUserSelect &&
        BpmCandidateStrategyEnum.APPROVE_USER_SELECT ===
          activity.candidateStrategy))
  );
}

/** 判断是否需要显示审批意见 */
function shouldShowApprovalReason(task: any, nodeType: BpmNodeTypeEnum) {
  return (
    task.reason &&
    [BpmNodeTypeEnum.END_EVENT_NODE, BpmNodeTypeEnum.USER_TASK_NODE].includes(
      nodeType,
    )
  );
}

/** 用户选择弹窗关闭 */
function handleUserSelectClosed() {
  selectedUsers.value = [];
}

/** 用户选择弹窗取消 */
function handleUserSelectCancel() {
  selectedUsers.value = [];
}

/** 设置自定义审批人 */
const setCustomApproveUsers = (activityId: string, users: any[]) => {
  customApproveUsers.value[activityId] = users || [];
};

/** 批量设置多个节点的自定义审批人 */
const batchSetCustomApproveUsers = (data: Record<string, any[]>) => {
  Object.keys(data).forEach((activityId) => {
    customApproveUsers.value[activityId] = data[activityId] || [];
  });
};

defineExpose({ setCustomApproveUsers, batchSetCustomApproveUsers });
</script>

<template>
  <div class="oa-process-timeline">
    <Timeline class="oa-process-timeline-list">
      <!-- 遍历每个审批节点 -->
      <Timeline.Item
        v-for="(activity, index) in activityNodes"
        :key="index"
        :color="getApprovalNodeColor(activity.status)"
      >
        <template #dot>
          <div class="oa-process-timeline-dot-wrap">
            <div
              class="oa-process-timeline-dot-ring"
              :style="getApprovalNodeRingStyle(activity)"
            ></div>
            <div
              class="oa-process-timeline-dot"
              :style="getApprovalNodeDotStyle(activity)"
            >
              <IconifyIcon
                :icon="getApprovalNodeTypeIcon(activity.nodeType)"
                class="oa-process-timeline-dot-icon"
              />
            </div>
            <div
              v-if="showStatusIcon"
              class="oa-process-timeline-status"
              :style="{
                backgroundColor: getApprovalNodeColor(activity.status),
              }"
            >
              <IconifyIcon
                :icon="getApprovalNodeIcon(activity.status, activity.nodeType)"
                class="oa-process-timeline-status-icon"
                :class="[statusIconMap[activity.status]?.animation]"
              />
            </div>
          </div>
        </template>

        <div
          class="oa-process-timeline-card"
          :id="`activity-task-${activity.id}-${index}`"
        >
          <!-- 第一行：节点名称、时间 -->
          <div class="oa-process-timeline-head">
            <div class="oa-process-timeline-title">
              {{ activity.name }}
              <span v-if="activity.status === BpmTaskStatusEnum.SKIP">
                【跳过】
              </span>
            </div>
            <!-- 信息：时间 -->
            <div
              v-if="activity.status !== BpmTaskStatusEnum.NOT_START"
              class="oa-process-timeline-time"
            >
              {{ getApprovalNodeTime(activity) }}
            </div>
          </div>

          <!-- 子流程节点 -->
          <div v-if="activity.nodeType === BpmNodeTypeEnum.CHILD_PROCESS_NODE">
            <Button
              type="primary"
              ghost
              size="small"
              @click="handleChildProcess(activity)"
              :disabled="!activity.processInstanceId"
            >
              查看子流程
            </Button>
          </div>

          <!-- 需要自定义选择审批人 -->
          <div
            v-if="shouldShowCustomUserSelect(activity)"
            class="oa-process-timeline-users"
          >
            <Tooltip title="添加用户" placement="left">
              <Button
                type="primary"
                size="middle"
                ghost
                class="oa-process-timeline-add-user"
                @click="
                  handleSelectUser(
                    activity.id,
                    customApproveUsers[activity.id] ?? [],
                  )
                "
              >
                <template #icon>
                  <IconifyIcon icon="lucide:user-plus" class="size-4" />
                </template>
              </Button>
            </Tooltip>

            <div
              v-for="(user, userIndex) in customApproveUsers[activity.id]"
              :key="user.id || userIndex"
              class="oa-process-timeline-user-chip"
            >
              <Avatar
                class="!m-1"
                :size="28"
                v-if="user.avatar"
                :src="user.avatar"
              />

              <Avatar class="!m-1" :size="28" v-else>
                <span>{{ user.nickname.substring(0, 1) }}</span>
              </Avatar>
              <span class="oa-process-timeline-user-copy">
                <span class="oa-process-timeline-user-name">{{ user.nickname }}</span>
                <span class="oa-process-timeline-user-role">
                  {{ getTimelineUserRole(activity) }}
                </span>
              </span>
            </div>
          </div>

          <div v-else class="oa-process-timeline-users">
            <!-- 情况一：遍历每个审批节点下的【进行中】task 任务 -->
            <div
              v-for="(task, idx) in activity.tasks"
              :key="idx"
              class="flex flex-col gap-2 pr-2"
            >
              <div
                class="oa-process-timeline-task-user"
                v-if="task.assigneeUser || task.ownerUser"
              >
                <!-- 信息：头像昵称 -->
                <div class="oa-process-timeline-user-chip">
                  <template v-if="getTimelineUser(task)">
                    <Avatar
                      class="!m-1"
                      :size="28"
                      v-if="getTimelineUser(task)?.avatar"
                      :src="getTimelineUser(task)?.avatar"
                    />
                    <Avatar class="!m-1" :size="28" v-else>
                      {{ getTimelineUser(task)?.nickname?.substring(0, 1) }}
                    </Avatar>
                    <span class="oa-process-timeline-user-copy">
                      <span class="oa-process-timeline-user-name">
                        {{ getTimelineUser(task)?.nickname || '-' }}
                      </span>
                      <span class="oa-process-timeline-user-role">
                        {{ getTimelineUserRole(activity) }}
                      </span>
                      <span
                        v-if="getTimelineUserDept(getTimelineUser(task))"
                        class="oa-process-timeline-user-dept"
                      >
                        {{ getTimelineUserDept(getTimelineUser(task)) }}
                      </span>
                    </span>
                  </template>

                  <!-- 信息：任务状态图标 -->
                  <div
                    v-if="
                      showStatusIcon && onlyStatusIconShow.includes(task.status)
                    "
                    class="oa-process-timeline-mini-status"
                    :style="{
                      backgroundColor: statusIconMap[task.status]?.color,
                    }"
                  >
                    <IconifyIcon
                      :icon="statusIconMap[task.status]?.icon || 'lucide:clock'"
                      class="oa-process-timeline-mini-status-icon"
                      :class="[statusIconMap[task.status]?.animation]"
                    />
                  </div>
                </div>
              </div>

              <!-- 审批意见和签名 -->
              <teleport defer :to="`#activity-task-${activity.id}-${index}`">
                <div
                  v-if="shouldShowApprovalReason(task, activity.nodeType)"
                  class="oa-process-timeline-note"
                >
                  审批意见：{{ task.reason }}
                </div>
                <div
                  v-if="
                    task.signPicUrl &&
                    activity.nodeType === BpmNodeTypeEnum.USER_TASK_NODE
                  "
                  class="oa-process-timeline-note oa-process-timeline-signature"
                >
                  签名：
                  <Image
                    class="ml-2"
                    :width="180"
                    :height="60"
                    :src="task.signPicUrl"
                    :preview="{ src: task.signPicUrl }"
                  />
                </div>
              </teleport>
            </div>

            <!-- 情况二：遍历每个审批节点下的【候选的】task 任务 -->
            <div
              v-for="(user, userIndex) in activity.candidateUsers"
              :key="userIndex"
              class="oa-process-timeline-user-chip"
            >
              <Avatar
                class="!m-1"
                :size="28"
                v-if="user.avatar"
                :src="user.avatar"
              />
              <Avatar class="!m-1" :size="28" v-else>
                {{ user.nickname.substring(0, 1) }}
              </Avatar>
              <span class="oa-process-timeline-user-copy">
                <span class="oa-process-timeline-user-name">{{ user.nickname }}</span>
                <span class="oa-process-timeline-user-role">
                  {{ getTimelineUserRole(activity) }}
                </span>
                <span
                  v-if="getTimelineUserDept(user)"
                  class="oa-process-timeline-user-dept"
                >
                  {{ getTimelineUserDept(user) }}
                </span>
              </span>

              <!-- 候选任务状态图标 -->
              <div
                v-if="showStatusIcon"
                class="oa-process-timeline-mini-status"
                :style="{ backgroundColor: statusIconMap['-1']?.color }"
              >
                <IconifyIcon
                  class="oa-process-timeline-mini-status-icon"
                  :icon="statusIconMap['-1']?.icon || 'lucide:clock'"
                />
              </div>
            </div>
          </div>
        </div>
      </Timeline.Item>
    </Timeline>

    <!-- 用户选择弹窗 -->
    <UserSelectModalComp
      class="w-3/5"
      v-model:value="selectedUsers"
      :multiple="true"
      title="选择用户"
      @confirm="handleUserSelectConfirm"
      @closed="handleUserSelectClosed"
      @cancel="handleUserSelectCancel"
    />
  </div>
</template>

<style scoped>
.oa-process-timeline {
  padding-top: 6px;
}

.oa-process-timeline-list {
  padding-top: 0;
}

.oa-process-timeline :deep(.ant-timeline-item-tail) {
  inset-inline-start: 18px;
  border-inline-start: 2px solid rgba(207, 223, 243, 0.92);
}

.oa-process-timeline :deep(.ant-timeline-item-head) {
  inset-inline-start: 6px;
}

.oa-process-timeline :deep(.ant-timeline-item-content) {
  margin-inline-start: 48px;
}

.oa-process-timeline-dot-wrap {
  position: relative;
  width: 26px;
  height: 26px;
}

.oa-process-timeline-dot-ring {
  position: absolute;
  inset: -3px;
  border-radius: 11px;
  opacity: 0.42;
  filter: blur(0.2px);
}

.oa-process-timeline-dot {
  display: flex;
  position: relative;
  width: 26px;
  height: 26px;
  align-items: center;
  justify-content: center;
  border: 1px solid transparent;
  border-radius: 10px;
  color: #fff;
  overflow: hidden;
}

.oa-process-timeline-dot-icon {
  font-size: 14px;
  color: inherit;
  stroke-width: 2;
}

.oa-process-timeline-status {
  position: absolute;
  right: -4px;
  bottom: -4px;
  display: flex;
  width: 15px;
  height: 15px;
  align-items: center;
  justify-content: center;
  border: 2px solid #fff;
  border-radius: 999px;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.16);
}

.oa-process-timeline-status-icon,
.oa-process-timeline-mini-status-icon {
  color: var(--oa-accent-contrast);
  font-size: 10px;
}

.oa-process-timeline-card {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 10px;
  padding: 2px 0 18px;
  border-bottom: 1px solid color-mix(in srgb, var(--oa-shell-border) 88%, transparent);
  background: transparent;
}

.oa-process-timeline-head {
  display: flex;
  width: 100%;
  gap: 12px;
  align-items: baseline;
}

.oa-process-timeline-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--oa-ink);
  line-height: 1.4;
}

.oa-process-timeline-time {
  margin-left: auto;
  font-size: 12px;
  color: var(--oa-ink-faint);
  white-space: nowrap;
}

.oa-process-timeline-users {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  align-items: center;
}

.oa-process-timeline-add-user {
  border-radius: 0;
}

.oa-process-timeline-user-chip {
  position: relative;
  display: inline-flex;
  min-height: 28px;
  align-items: center;
  gap: 8px;
  padding: 0 10px 0 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--oa-ink);
}

.oa-process-timeline-user-name {
  font-size: 13px;
  color: var(--oa-ink);
  font-weight: 500;
}

.oa-process-timeline-user-copy {
  display: inline-flex;
  min-width: 0;
  flex-direction: column;
  gap: 1px;
}

.oa-process-timeline-user-role,
.oa-process-timeline-user-dept {
  color: var(--oa-ink-soft);
  font-size: 11px;
  line-height: 1.35;
}

.oa-process-timeline-user-role {
  color: var(--oa-accent);
}

.oa-process-timeline-task-user {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 10px;
}

.oa-process-timeline-mini-status {
  position: absolute;
  right: 6px;
  bottom: -1px;
  display: flex;
  width: 12px;
  height: 12px;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--oa-shell-border);
  border-radius: 999px;
  background: var(--oa-shell-surface);
}

.oa-process-timeline-note {
  width: 100%;
  padding: 0 0 0 14px;
  font-size: 12px;
  color: var(--oa-ink-soft);
  line-height: 1.7;
  border-left: 1px solid var(--oa-shell-border);
  background: transparent;
}

.oa-process-timeline-signature {
  align-items: center;
}

@media (max-width: 768px) {
  .oa-process-timeline-card {
    padding: 2px 0 16px;
  }

  .oa-process-timeline-head {
    flex-direction: column;
    align-items: flex-start;
  }

  .oa-process-timeline-time {
    margin-left: 0;
  }
}
</style>
