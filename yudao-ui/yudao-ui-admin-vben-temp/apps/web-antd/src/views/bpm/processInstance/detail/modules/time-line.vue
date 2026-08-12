<!-- 审批详情的右侧：审批流 -->
<script lang="ts" setup>
import type { BpmProcessInstanceApi } from '#/api/bpm/processInstance';

import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useVbenModal } from '@vben/common-ui';
import {
  BpmCandidateStrategyEnum,
  BpmNodeTypeEnum,
  BpmTaskStatusEnum,
} from '@vben/constants';
import { IconifyIcon } from '@vben/icons';
import { formatDateTime, isEmpty } from '@vben/utils';

import { Button, Image, Timeline, Tooltip } from 'ant-design-vue';

import { UserSelectModal } from '#/views/system/user/components';
import { getSimpleUserList } from '#/api/system/user';

defineOptions({ name: 'BpmProcessInstanceTimeline' });

// 审批详情接口的候选人仅保证返回用户 ID；部门名称以用户管理数据为准。
const timelineUserMap = ref<Record<string, any>>({});
let loadTimelineUsersPromise: null | Promise<void> = null;

async function ensureTimelineUsers() {
  if (Object.keys(timelineUserMap.value).length > 0) {
    return;
  }
  loadTimelineUsersPromise ||= getSimpleUserList().then((users) => {
    timelineUserMap.value = Object.fromEntries(
      users.map((user) => [String(user.id), user]),
    );
  });
  await loadTimelineUsersPromise;
}

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

onMounted(() => {
  void ensureTimelineUsers();
});

const statusIconMap: Record<
  string,
  { animation?: string; color: string; icon: string }
> = {
  '-2': { color: '#909398', icon: 'lucide:skip-forward' }, // 跳过
  '-1': { color: '#909398', icon: 'lucide:clock-3' }, // 审批未开始
  '0': {
    color: '#ff943e',
    icon: 'lucide:loader-circle',
    animation: 'animate-spin',
  }, // 待审批
  '1': {
    color: '#448ef7',
    icon: 'lucide:loader-circle',
    animation: 'animate-spin',
  }, // 审批中
  '2': { color: '#00b32a', icon: 'lucide:check' }, // 审批通过
  '3': { color: '#f46b6c', icon: 'lucide:x' }, // 审批不通过
  '4': { color: '#cccccc', icon: 'lucide:ban' }, // 已取消
  '5': { color: '#f46b6c', icon: 'lucide:corner-up-left' }, // 退回
  '6': { color: '#448ef7', icon: 'lucide:clock-3' }, // 委派中
  '7': { color: '#00b32a', icon: 'lucide:badge-check' }, // 审批通过中
}; // 状态图标映射
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
  return statusIconMap[taskStatus]?.color || '#94a3b8';
}

function getTimelineNodeIcon(nodeType: BpmNodeTypeEnum) {
  if (nodeType === BpmNodeTypeEnum.START_USER_NODE) {
    return 'lucide:user-round';
  }
  if (nodeType === BpmNodeTypeEnum.END_EVENT_NODE) {
    return 'lucide:power';
  }
  if (nodeType === BpmNodeTypeEnum.COPY_TASK_NODE) {
    return 'lucide:copy';
  }
  return 'lucide:stamp';
}

function getTimelineStatusColor(
  activity: BpmProcessInstanceApi.ApprovalNodeInfo,
) {
  return getApprovalNodeColor(activity.status);
}

function getTimelineStatusIcon(
  activity: BpmProcessInstanceApi.ApprovalNodeInfo,
) {
  return getApprovalNodeIcon(activity.status, activity.nodeType);
}

function shouldShowTimelineStatus(
  activity: BpmProcessInstanceApi.ApprovalNodeInfo,
) {
  return (
    props.showStatusIcon && activity.status !== BpmTaskStatusEnum.NOT_START
  );
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
  return enrichTimelineUser(task?.assigneeUser || task?.ownerUser);
}

function enrichTimelineUser(user: any) {
  if (!user?.id) {
    return user;
  }
  const fullUser = timelineUserMap.value[String(user.id)];
  if (!fullUser) {
    return user;
  }
  return {
    ...fullUser,
    ...user,
    deptName: user.deptName || user.departmentName || fullUser.deptName,
  };
}

function getActivityTasks(activity: BpmProcessInstanceApi.ApprovalNodeInfo) {
  const seen = new Set<string>();
  return (activity.tasks || []).filter((task) => {
    const user = getTimelineUser(task);
    if (!user) {
      return true;
    }
    const key = String(user.id || user.nickname || '');
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function getActivityCandidateUsers(
  activity: BpmProcessInstanceApi.ApprovalNodeInfo,
) {
  const seen = new Set<string>();
  return (activity.candidateUsers || []).map(enrichTimelineUser).filter((user) => {
    const key = String(user.id || user.nickname || '');
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function getActivityUsers(activity: BpmProcessInstanceApi.ApprovalNodeInfo) {
  const users = [
    ...(customApproveUsers.value[activity.id] || []),
    ...getActivityTasks(activity).map((task) => getTimelineUser(task)),
    ...getActivityCandidateUsers(activity),
  ].filter(Boolean);
  const seen = new Set<string>();
  return users.filter((user) => {
    const key = String(user.id || user.nickname || '');
    if (seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function getActivityPrimaryUser(
  activity: BpmProcessInstanceApi.ApprovalNodeInfo,
) {
  return getActivityUsers(activity)[0];
}

function getTimelineUserPosition(
  user: any,
) {
  return user?.deptName || user?.departmentName || '-';
}

function isEndActivity(activity: BpmProcessInstanceApi.ApprovalNodeInfo) {
  return activity.nodeType === BpmNodeTypeEnum.END_EVENT_NODE;
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
            <div class="oa-process-timeline-node-icon">
              <IconifyIcon :icon="getTimelineNodeIcon(activity.nodeType)" />
            </div>
            <div
              v-if="shouldShowTimelineStatus(activity)"
              class="oa-process-timeline-status"
              :style="{
                backgroundColor: getTimelineStatusColor(activity),
              }"
            >
              <IconifyIcon
                :icon="getTimelineStatusIcon(activity)"
                class="oa-process-timeline-status-icon"
                :class="statusIconMap[activity.status]?.animation"
              />
            </div>
          </div>
        </template>

        <div
          class="oa-process-timeline-card"
          :id="`activity-task-${activity.id}-${index}`"
        >
          <!-- 节点人员、职位与时间 -->
          <div class="oa-process-timeline-head">
            <div class="oa-process-timeline-person">
              <span class="oa-process-timeline-title">
                {{
                  getActivityPrimaryUser(activity)?.nickname ||
                  activity.name ||
                  '审批节点'
                }}
              </span>
              <span
                v-if="!isEndActivity(activity)"
                class="oa-process-timeline-user-role"
              >
                （{{
                  getTimelineUserPosition(getActivityPrimaryUser(activity))
                }}）
              </span>
              <span v-if="activity.status === BpmTaskStatusEnum.SKIP">
                【跳过】
              </span>
            </div>
            <div
              v-if="activity.status !== BpmTaskStatusEnum.NOT_START"
              class="oa-process-timeline-time"
            >
              {{ getApprovalNodeTime(activity) }}
            </div>
          </div>

          <div
            v-if="getActivityUsers(activity).length > 1"
            class="oa-process-timeline-extra-users"
          >
            <span
              v-for="user in getActivityUsers(activity).slice(1)"
              :key="user.id || user.nickname"
              class="oa-process-timeline-extra-user"
            >
              <template v-if="!isEndActivity(activity)">
                {{ user.nickname || '-' }}（{{
                  getTimelineUserPosition(user)
                }}）
              </template>
              <template v-else>{{ user.nickname || '-' }}</template>
            </span>
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
          </div>

          <div v-else>
            <!-- 情况一：遍历每个审批节点下的【进行中】task 任务 -->
            <div
              v-for="(task, idx) in getActivityTasks(activity)"
              :key="idx"
              class="flex flex-col gap-2 pr-2"
            >
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
  border-inline-start: 2px solid #e5e7eb;
}

.oa-process-timeline :deep(.ant-timeline-item-head) {
  inset-inline-start: 6px;
}

.oa-process-timeline :deep(.ant-timeline-item-content) {
  margin-inline-start: 48px;
}

.oa-process-timeline-dot-wrap {
  position: relative;
  width: 34px;
  height: 34px;
}

.oa-process-timeline-node-icon {
  display: flex;
  width: 36px;
  height: 36px;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  border: 1px solid #9ec0ff;
  border-radius: 999px;
  background: #4f8df7;
  box-shadow: 0 2px 7px rgb(31 111 235 / 22%);
  color: #fff;
  font-size: 18px;
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
  right: -5px;
  bottom: -5px;
  display: flex;
  width: 17px;
  height: 17px;
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
  border-bottom: 1px solid
    color-mix(in srgb, var(--oa-shell-border) 88%, transparent);
  background: transparent;
}

.oa-process-timeline-head {
  display: flex;
  width: 100%;
  gap: 12px;
  align-items: baseline;
}

.oa-process-timeline-person {
  display: inline-flex;
  min-width: 0;
  align-items: baseline;
  gap: 4px;
  flex-wrap: wrap;
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

.oa-process-timeline-extra-users {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 18px;
  color: var(--oa-ink-soft);
  font-size: 13px;
}

.oa-process-timeline-extra-user {
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
