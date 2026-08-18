<script lang="ts" setup>
import type { Key } from 'ant-design-vue/es/table/interface';

import type { SystemDeptApi } from '#/api/system/dept';
import type { SystemUserApi } from '#/api/system/user';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { handleTree } from '@vben/utils';

import {
  Button,
  Col,
  Input,
  message,
  Pagination,
  Row,
  Transfer,
  Tree,
} from 'ant-design-vue';

import { getSimpleDeptList } from '#/api/system/dept';
import { getUserPage } from '#/api/system/user';
import { getSimpleUserList } from '#/api/system/user';

/** 部门树节点接口 */
interface DeptTreeNode {
  key: string;
  title: string;
  children?: DeptTreeNode[];
  name: string;
}

interface Props {
  cancelText?: string;
  confirmText?: string;
  multiple?: boolean;
  title?: string;
  value?: number[];
}

defineOptions({ name: 'UserSelectModal' });

const props = withDefaults(defineProps<Props>(), {
  title: '选择用户',
  multiple: true,
  value: () => [],
  confirmText: '确定',
  cancelText: '取消',
});

const emit = defineEmits<{
  cancel: [];
  closed: [];
  confirm: [value: SystemUserApi.User[]];
  'update:value': [value: number[]];
}>();

// 部门树数据
const deptTree = ref<any[]>([]);
const deptList = ref<SystemDeptApi.Dept[]>([]);
const expandedKeys = ref<Key[]>([]);
const selectedDeptId = ref<number>();
const deptSearchKeys = ref('');

// 用户数据管理
const userList = ref<SystemUserApi.User[]>([]); // 存储所有已知用户
const selectedUserIds = ref<string[]>([]);

const [Modal, modalApi] = useVbenModal({
  onCancel: handleCancel,
  onClosed: handleClosed,
  async onOpenChange(isOpen: boolean) {
    if (!isOpen) {
      resetData();
      return;
    }
    // 加载数据
    const data = modalApi.getData();
    if (!data) {
      return;
    }
    modalApi.lock();
    try {
      // 加载部门数据
      const deptData = await getSimpleDeptList();
      deptList.value = deptData;
      const treeData = handleTree(deptData);
      deptTree.value = treeData.map((node) => processDeptNode(node));
      expandedKeys.value = deptTree.value.map((node) => node.key);

      // 加载初始用户数据
      await loadUserData(1, leftListState.value.pagination.pageSize);

      // 设置已选用户
      if (data.userIds?.length) {
        selectedUserIds.value = data.userIds.map(String);
        // 加载已选用户的完整信息  TODO   目前接口暂不支持 多个用户ID 查询， 需要后端支持
        const { list } = await getUserPage({
          pageNo: 1,
          pageSize: 100, // 临时使用固定值确保能加载所有已选用户
          userIds: data.userIds,
        });
        // 使用 Map 来去重，以用户 ID 为 key
        const userMap = new Map(userList.value.map((user) => [user.id, user]));
        list.forEach((user) => {
          if (!userMap.has(user.id)) {
            userMap.set(user.id, user);
          }
        });
        userList.value = [...userMap.values()];
        updateRightListData();
      }

      modalApi.open();
    } finally {
      modalApi.unlock();
    }
  },
  destroyOnClose: true,
});

const leftListState = ref({
  searchValue: '',
  dataSource: [] as SystemUserApi.User[],
  pagination: {
    current: 1,
    pageSize: 10,
    total: 0,
  },
}); // 左侧列表状态

const rightListState = ref({
  searchValue: '',
  dataSource: [] as SystemUserApi.User[],
  pagination: {
    current: 1,
    pageSize: 10,
    total: 0,
  },
}); // 右侧列表状态

const transferDataSource = computed(() => {
  return [
    ...leftListState.value.dataSource,
    ...rightListState.value.dataSource,
  ];
}); // 计算属性：Transfer 数据源

const filteredDeptTree = computed(() => {
  if (!deptSearchKeys.value) return deptTree.value;

  const filterNode = (node: any, depth = 0): any => {
    // 添加深度限制，防止过深的递归导致爆栈
    if (depth > 100) return null;

    // 按部门名称搜索
    const name = node?.name?.toLowerCase();
    const search = deptSearchKeys.value.toLowerCase();

    // 如果当前节点匹配，直接返回节点，不处理子节点
    if (name?.includes(search)) {
      return {
        ...node,
        children: node.children,
      };
    }

    // 如果当前节点不匹配，检查子节点
    if (node.children) {
      const filteredChildren = node.children
        .map((child: any) => filterNode(child, depth + 1))
        .filter(Boolean);

      if (filteredChildren.length > 0) {
        return {
          ...node,
          children: filteredChildren,
        };
      }
    }

    return null;
  };

  return deptTree.value.map((node: any) => filterNode(node)).filter(Boolean);
}); // 过滤部门树数据

/** 加载用户数据 */
async function loadUserData(pageNo: number, pageSize: number) {
  try {
    const allowedUserIds = modalApi.getData()?.allowedUserIds as
      | number[]
      | undefined;
    if (allowedUserIds?.length) {
      const list = await getSimpleUserList();
      const allowedUserIdSet = new Set(allowedUserIds);
      const allowedUsers = list.filter((user) => allowedUserIdSet.has(user.id!));
      leftListState.value.dataSource = allowedUsers;
      leftListState.value.pagination.total = allowedUsers.length;
      leftListState.value.pagination.current = 1;
      leftListState.value.pagination.pageSize = pageSize;
      const knownUserIds = new Set(userList.value.map((user) => user.id));
      userList.value.push(
        ...allowedUsers.filter((user) => !knownUserIds.has(user.id)),
      );
      return;
    }
    const { list, total } = await getUserPage({
      pageNo,
      pageSize,
      deptId: selectedDeptId.value,
      username: leftListState.value.searchValue || undefined,
    });

    leftListState.value.dataSource = list;
    leftListState.value.pagination.total = total;
    leftListState.value.pagination.current = pageNo;
    leftListState.value.pagination.pageSize = pageSize;

    // 更新用户列表缓存
    const newUsers = list.filter(
      (user) => !userList.value.some((u) => u.id === user.id),
    );
    if (newUsers.length > 0) {
      userList.value.push(...newUsers);
    }
  } finally {
    //
  }
}

/** 更新右侧列表数据 */
function updateRightListData() {
  // 使用 Set 来去重选中的用户 ID
  const uniqueSelectedIds = new Set(selectedUserIds.value);

  // 获取选中的用户，确保不重复
  const selectedUsers = userList.value.filter((user) =>
    uniqueSelectedIds.has(String(user.id)),
  );

  // 应用搜索过滤
  const filteredUsers = rightListState.value.searchValue
    ? selectedUsers.filter((user) =>
        user.nickname
          .toLowerCase()
          .includes(rightListState.value.searchValue.toLowerCase()),
      )
    : selectedUsers;

  // 更新总数（使用 Set 确保唯一性）
  rightListState.value.pagination.total = new Set(
    filteredUsers.map((user) => user.id),
  ).size;

  // 应用分页
  const { current, pageSize } = rightListState.value.pagination;
  const startIndex = (current - 1) * pageSize;
  const endIndex = startIndex + pageSize;

  rightListState.value.dataSource = filteredUsers.slice(startIndex, endIndex);
}

/** 处理左侧分页变化 */
async function handleLeftPaginationChange(page: number, pageSize: number) {
  await loadUserData(page, pageSize);
}

/** 处理右侧分页变化 */
function handleRightPaginationChange(page: number, pageSize: number) {
  rightListState.value.pagination.current = page;
  rightListState.value.pagination.pageSize = pageSize;
  updateRightListData();
}

/** 处理用户搜索 */
async function handleUserSearch(direction: string, value: string) {
  if (direction === 'left') {
    leftListState.value.searchValue = value;
    leftListState.value.pagination.current = 1;
    await loadUserData(1, leftListState.value.pagination.pageSize);
  } else {
    rightListState.value.searchValue = value;
    rightListState.value.pagination.current = 1;
    updateRightListData();
  }
}

/** 处理用户选择变化 */
function handleUserChange(targetKeys: string[]) {
  // 白名单审批节点只能指定一名审批人；普通用户选择仍保留原有多选行为。
  const uniqueUserIds = [...new Set(targetKeys)];
  selectedUserIds.value = props.multiple
    ? uniqueUserIds
    : uniqueUserIds.slice(-1);
  emit('update:value', selectedUserIds.value.map(Number));
  updateRightListData();
}

/** 重置数据 */
function resetData() {
  userList.value = [];
  selectedUserIds.value = [];

  // 取消部门选中
  selectedDeptId.value = undefined;
  // 取消选中的用户
  selectedUserIds.value = [];

  leftListState.value = {
    searchValue: '',
    dataSource: [],
    pagination: {
      current: 1,
      pageSize: 10,
      total: 0,
    },
  };

  rightListState.value = {
    searchValue: '',
    dataSource: [],
    pagination: {
      current: 1,
      pageSize: 10,
      total: 0,
    },
  };
}

// TODO   后端接口目前仅支持  username 检索， 筛选条件需要跟后端请求参数保持一致。
function filterOption(inputValue: string, option: any) {
  return option.username.toLowerCase().includes(inputValue.toLowerCase());
}

/** 处理部门树展开/折叠 */
function handleExpand(keys: Key[]) {
  expandedKeys.value = keys;
}

/** 处理部门搜索 */
function handleDeptSearch(value: string) {
  deptSearchKeys.value = value;

  // 如果有搜索结果，自动展开所有节点
  if (value) {
    const getAllKeys = (nodes: any[]): string[] => {
      const keys: string[] = [];
      for (const node of nodes) {
        keys.push(node.key);
        if (node.children) {
          keys.push(...getAllKeys(node.children));
        }
      }
      return keys;
    };
    expandedKeys.value = getAllKeys(deptTree.value);
  } else {
    // 清空搜索时，只展开第一级节点
    expandedKeys.value = deptTree.value.map((node) => node.key);
  }
}

/** 处理部门选择 */
async function handleDeptSelect(selectedKeys: Key[], _info: any) {
  // 更新选中的部门 ID
  const newDeptId =
    selectedKeys.length > 0 ? Number(selectedKeys[0]) : undefined;
  selectedDeptId.value =
    newDeptId === selectedDeptId.value ? undefined : newDeptId;

  // 重置分页并加载数据
  const { pageSize } = leftListState.value.pagination;
  leftListState.value.pagination.current = 1;
  await loadUserData(1, pageSize);
}

/** 确认选择 */
function handleConfirm() {
  if (selectedUserIds.value.length === 0) {
    message.warning('请选择用户');
    return;
  }
  emit(
    'confirm',
    userList.value.filter((user) =>
      selectedUserIds.value.includes(String(user.id)),
    ),
  );
  modalApi.close();
}

/** 取消选择 */
function handleCancel() {
  emit('cancel');
  modalApi.close();
  // 确保在动画结束后再重置数据
  setTimeout(() => {
    resetData();
  }, 300);
}

/** 关闭弹窗 */
function handleClosed() {
  emit('closed');
  resetData();
}

/** 递归处理部门树节点 */
function processDeptNode(node: any): DeptTreeNode {
  return {
    key: String(node.id),
    title: `${node.name} (${node.id})`,
    name: node.name,
    children: node.children?.map((child: any) => processDeptNode(child)),
  };
}
</script>

<template>
  <Modal class="w-2/5 oa-user-select-modal" key="user-select-modal" :title="title">
    <Row :gutter="[18, 16]" class="oa-user-select-layout">
      <Col :span="6">
        <div class="oa-user-select-dept-panel h-[500px] overflow-auto">
          <div class="oa-user-select-dept-search">
            <Input
              v-model:value="deptSearchKeys"
              placeholder="搜索部门"
              allow-clear
              @input="(e) => handleDeptSearch(e.target?.value ?? '')"
            />
          </div>
          <Tree
            :tree-data="filteredDeptTree"
            :expanded-keys="expandedKeys"
            :selected-keys="selectedDeptId ? [String(selectedDeptId)] : []"
            @select="handleDeptSelect"
            @expand="handleExpand"
          />
        </div>
      </Col>
      <Col :span="18">
        <Transfer
          :row-key="(record) => String(record.id)"
          :data-source="transferDataSource"
          v-model:target-keys="selectedUserIds"
          :titles="['未选', '已选']"
          :show-search="true"
          :show-select-all="props.multiple"
          :filter-option="filterOption"
          @change="handleUserChange"
          @search="handleUserSearch"
        >
          <template #render="item">
            <span>{{ item?.nickname }} ({{ item?.username }})</span>
          </template>

          <template #footer="{ direction }">
            <div v-if="direction === 'left'">
              <Pagination
                v-model:current="leftListState.pagination.current"
                v-model:page-size="leftListState.pagination.pageSize"
                :total="leftListState.pagination.total"
                :show-size-changer="true"
                :show-total="(total) => `共 ${total} 条`"
                size="small"
                @change="handleLeftPaginationChange"
              />
            </div>

            <div v-if="direction === 'right'">
              <Pagination
                v-model:current="rightListState.pagination.current"
                v-model:page-size="rightListState.pagination.pageSize"
                :total="rightListState.pagination.total"
                :show-size-changer="true"
                :show-total="(total) => `共 ${total} 条`"
                size="small"
                @change="handleRightPaginationChange"
              />
            </div>
          </template>
        </Transfer>
      </Col>
    </Row>
    <template #footer>
      <Button
        type="primary"
        :disabled="selectedUserIds.length === 0"
        @click="handleConfirm"
      >
        {{ confirmText }}
      </Button>
      <Button @click="handleCancel">{{ cancelText }}</Button>
    </template>
  </Modal>
</template>

<style lang="scss" scoped>
.oa-user-select-layout {
  min-height: 500px;
}

.oa-user-select-dept-panel {
  border-top: 1px solid var(--oa-shell-border);
  border-bottom: 1px solid var(--oa-shell-border);
  border-left: 0;
  border-right: 0;
}

.oa-user-select-dept-search {
  padding: 10px 0 12px;
  border-bottom: 1px solid var(--oa-shell-border);
}

:deep(.ant-transfer) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 500px;
}

:deep(.ant-transfer-list) {
  display: flex;
  flex: 1;
  flex-direction: column;
  width: 300px !important;
  height: 100%;
  border-radius: 0;
  border-left: 0;
  border-right: 0;
}

:deep(.ant-transfer-list-header) {
  flex-shrink: 0;
  padding-inline: 0;
}

:deep(.ant-transfer-list-search) {
  flex-shrink: 0;
  padding: 10px 0 12px;
}

:deep(.ant-transfer-list-body) {
  flex: 1;
  overflow: auto;
}

:deep(.ant-transfer-list-content) {
  height: auto !important;
}

:deep(.ant-transfer-list-content-item) {
  padding: 6px 12px;
}

:deep(.ant-transfer-operation) {
  padding: 0 8px;
}

:deep(.ant-transfer-list-footer) {
  flex-shrink: 0;
}

:deep(.ant-tree) {
  background: transparent;
}

:deep(.ant-tree-node-content-wrapper) {
  border-radius: 0;
}

:deep(.ant-pagination) {
  margin: 8px;
  font-size: 12px;
  text-align: right;
}

:deep(.ant-pagination-options) {
  margin-left: 8px;
}

:deep(.ant-pagination-options-size-changer) {
  margin-right: 8px;
}
</style>

<style lang="scss">
body.oa-lite-theme-light .oa-user-select-modal,
body.oa-lite-theme-dark .oa-user-select-modal {
  background: var(--oa-shell-surface) !important;
  color: var(--oa-ink) !important;
  border-color: var(--oa-shell-border) !important;
  box-shadow: none !important;
}

body.oa-lite-theme-light .oa-user-select-modal .text-foreground,
body.oa-lite-theme-light .oa-user-select-modal .text-foreground\/80,
body.oa-lite-theme-light .oa-user-select-modal .text-muted-foreground,
body.oa-lite-theme-light .oa-user-select-modal [class*='text-foreground'],
body.oa-lite-theme-light .oa-user-select-modal [class*='text-muted-foreground'],
body.oa-lite-theme-dark .oa-user-select-modal .text-foreground,
body.oa-lite-theme-dark .oa-user-select-modal .text-foreground\/80,
body.oa-lite-theme-dark .oa-user-select-modal .text-muted-foreground,
body.oa-lite-theme-dark .oa-user-select-modal [class*='text-foreground'],
body.oa-lite-theme-dark .oa-user-select-modal [class*='text-muted-foreground'] {
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .border-border,
body.oa-lite-theme-light .oa-user-select-modal [class*='border-border'],
body.oa-lite-theme-dark .oa-user-select-modal .border-border,
body.oa-lite-theme-dark .oa-user-select-modal [class*='border-border'] {
  border-color: var(--oa-shell-border) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .bg-background,
body.oa-lite-theme-light .oa-user-select-modal .bg-card,
body.oa-lite-theme-light .oa-user-select-modal .bg-popover,
body.oa-lite-theme-dark .oa-user-select-modal .bg-background,
body.oa-lite-theme-dark .oa-user-select-modal .bg-card,
body.oa-lite-theme-dark .oa-user-select-modal .bg-popover {
  background: var(--oa-shell-surface) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .bg-accent,
body.oa-lite-theme-light .oa-user-select-modal .bg-secondary,
body.oa-lite-theme-light .oa-user-select-modal .bg-muted,
body.oa-lite-theme-dark .oa-user-select-modal .bg-accent,
body.oa-lite-theme-dark .oa-user-select-modal .bg-secondary,
body.oa-lite-theme-dark .oa-user-select-modal .bg-muted {
  background: var(--oa-shell-surface-muted) !important;
}

body.oa-lite-theme-light .oa-user-select-modal input,
body.oa-lite-theme-light .oa-user-select-modal textarea,
body.oa-lite-theme-light .oa-user-select-modal .ant-input,
body.oa-lite-theme-light .oa-user-select-modal .ant-input-affix-wrapper,
body.oa-lite-theme-light .oa-user-select-modal .ant-select-selector,
body.oa-lite-theme-dark .oa-user-select-modal input,
body.oa-lite-theme-dark .oa-user-select-modal textarea,
body.oa-lite-theme-dark .oa-user-select-modal .ant-input,
body.oa-lite-theme-dark .oa-user-select-modal .ant-input-affix-wrapper,
body.oa-lite-theme-dark .oa-user-select-modal .ant-select-selector {
  background: var(--oa-shell-surface) !important;
  color: var(--oa-ink) !important;
  border-color: var(--oa-shell-border) !important;
  box-shadow: none !important;
}

body.oa-lite-theme-light .oa-user-select-modal .ant-input::placeholder,
body.oa-lite-theme-light .oa-user-select-modal .ant-input-affix-wrapper input::placeholder,
body.oa-lite-theme-light .oa-user-select-modal .ant-select-selection-placeholder,
body.oa-lite-theme-dark .oa-user-select-modal .ant-input::placeholder,
body.oa-lite-theme-dark .oa-user-select-modal .ant-input-affix-wrapper input::placeholder,
body.oa-lite-theme-dark .oa-user-select-modal .ant-select-selection-placeholder {
  color: var(--oa-ink-faint) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .ant-transfer,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-header,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-body,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-content,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-content-item,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-search,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-footer,
body.oa-lite-theme-light .oa-user-select-modal .ant-tree,
body.oa-lite-theme-light .oa-user-select-modal .ant-tree-list,
body.oa-lite-theme-light .oa-user-select-modal .ant-tree-treenode,
body.oa-lite-theme-light .oa-user-select-modal .ant-tree-node-content-wrapper,
body.oa-lite-theme-light .oa-user-select-modal .ant-pagination,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-header,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-body,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-content,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-content-item,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-search,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-footer,
body.oa-lite-theme-dark .oa-user-select-modal .ant-tree,
body.oa-lite-theme-dark .oa-user-select-modal .ant-tree-list,
body.oa-lite-theme-dark .oa-user-select-modal .ant-tree-treenode,
body.oa-lite-theme-dark .oa-user-select-modal .ant-tree-node-content-wrapper,
body.oa-lite-theme-dark .oa-user-select-modal .ant-pagination {
  background: var(--oa-shell-surface) !important;
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list,
body.oa-lite-theme-light .oa-user-select-modal .ant-tree,
body.oa-lite-theme-light .oa-user-select-modal .oa-user-select-dept-panel,
body.oa-lite-theme-light .oa-user-select-modal .oa-user-select-dept-search,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list,
body.oa-lite-theme-dark .oa-user-select-modal .ant-tree,
body.oa-lite-theme-dark .oa-user-select-modal .oa-user-select-dept-panel,
body.oa-lite-theme-dark .oa-user-select-modal .oa-user-select-dept-search {
  border-color: var(--oa-shell-border) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-content-item:hover,
body.oa-lite-theme-light .oa-user-select-modal .ant-tree-node-content-wrapper:hover,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-content-item:hover,
body.oa-lite-theme-dark .oa-user-select-modal .ant-tree-node-content-wrapper:hover {
  background: var(--oa-shell-surface-muted) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-content-item-checked,
body.oa-lite-theme-light .oa-user-select-modal .ant-tree-node-selected,
body.oa-lite-theme-light .oa-user-select-modal .ant-tree-node-content-wrapper.ant-tree-node-selected,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-content-item-checked,
body.oa-lite-theme-dark .oa-user-select-modal .ant-tree-node-selected,
body.oa-lite-theme-dark .oa-user-select-modal .ant-tree-node-content-wrapper.ant-tree-node-selected {
  background: transparent !important;
  color: var(--oa-accent) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-header-title,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-content-item-text,
body.oa-lite-theme-light .oa-user-select-modal .ant-pagination-total-text,
body.oa-lite-theme-light .oa-user-select-modal .ant-pagination-options,
body.oa-lite-theme-light .oa-user-select-modal .ant-pagination-item a,
body.oa-lite-theme-light .oa-user-select-modal .ant-btn:not(.ant-btn-primary),
body.oa-lite-theme-light .oa-user-select-modal .ant-btn:not(.ant-btn-primary) > span,
body.oa-lite-theme-light .oa-user-select-modal .anticon,
body.oa-lite-theme-light .oa-user-select-modal .ant-input-prefix,
body.oa-lite-theme-light .oa-user-select-modal .ant-transfer-list-header .ant-checkbox + span,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-header-title,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-content-item-text,
body.oa-lite-theme-dark .oa-user-select-modal .ant-pagination-total-text,
body.oa-lite-theme-dark .oa-user-select-modal .ant-pagination-options,
body.oa-lite-theme-dark .oa-user-select-modal .ant-pagination-item a,
body.oa-lite-theme-dark .oa-user-select-modal .ant-btn:not(.ant-btn-primary),
body.oa-lite-theme-dark .oa-user-select-modal .ant-btn:not(.ant-btn-primary) > span,
body.oa-lite-theme-dark .oa-user-select-modal .anticon,
body.oa-lite-theme-dark .oa-user-select-modal .ant-input-prefix,
body.oa-lite-theme-dark .oa-user-select-modal .ant-transfer-list-header .ant-checkbox + span {
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .ant-btn,
body.oa-lite-theme-dark .oa-user-select-modal .ant-btn {
  border-color: var(--oa-shell-border) !important;
}

body.oa-lite-theme-light .oa-user-select-modal .ant-btn-primary,
body.oa-lite-theme-dark .oa-user-select-modal .ant-btn-primary {
  color: var(--oa-accent-contrast) !important;
}
</style>
