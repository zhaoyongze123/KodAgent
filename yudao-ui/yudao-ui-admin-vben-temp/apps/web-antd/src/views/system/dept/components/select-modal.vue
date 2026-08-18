<script lang="ts" setup>
import type { DataNode } from 'ant-design-vue/es/tree';

import type { SystemDeptApi } from '#/api/system/dept';

import { ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { handleTree } from '@vben/utils';

import { Col, Row, Tree } from 'ant-design-vue';

import { getSimpleDeptList } from '#/api/system/dept';

defineOptions({ name: 'DeptSelectModal' });

const props = withDefaults(
  defineProps<{
    cancelText?: string; // 取消按钮文本
    checkStrictly?: boolean; // checkable 状态下节点选择完全受控
    confirmText?: string; // 确认按钮文本
    multiple?: boolean; // 是否支持多选
    title?: string; // 标题
  }>(),
  {
    cancelText: '取消',
    checkStrictly: false,
    confirmText: '确认',
    multiple: true,
    title: '部门选择',
  },
);

const emit = defineEmits<{
  confirm: [deptList: SystemDeptApi.Dept[]];
}>();

type checkedKeys = number[] | { checked: number[]; halfChecked: number[] };
const deptTree = ref<DataNode[]>([]); // 部门树形结构
const selectedDeptIds = ref<checkedKeys>([]); // 选中的部门 ID 列表
const deptData = ref<SystemDeptApi.Dept[]>([]); // 部门数据

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    // 获取选中的部门 ID
    const selectedIds: number[] = Array.isArray(selectedDeptIds.value)
      ? selectedDeptIds.value
      : selectedDeptIds.value.checked || [];
    const deptArray = deptData.value.filter((dept) =>
      selectedIds.includes(dept.id!),
    );
    emit('confirm', deptArray);
    // 关闭并提示
    await modalApi.close();
  },
  async onOpenChange(isOpen: boolean) {
    if (!isOpen) {
      deptTree.value = [];
      selectedDeptIds.value = [];
      return;
    }
    // 加载数据
    const data = modalApi.getData();
    if (!data) {
      return;
    }
    modalApi.lock();
    try {
      deptData.value = await getSimpleDeptList();
      deptTree.value = handleTree(deptData.value) as DataNode[];
      // // 设置已选择的部门
      if (data.selectedList?.length) {
        const selectedIds = data.selectedList
          .map((dept: SystemDeptApi.Dept) => dept.id)
          .filter((id: number) => id !== undefined);
        selectedDeptIds.value = props.checkStrictly
          ? {
              checked: selectedIds,
              halfChecked: [],
            }
          : selectedIds;
      }
    } finally {
      modalApi.unlock();
    }
  },
  destroyOnClose: true,
});

/** 处理选中状态变化 */
function handleCheck() {
  if (!props.multiple) {
    // 单选模式下，只保留最后选择的节点
    if (Array.isArray(selectedDeptIds.value)) {
      const lastSelectedId =
        selectedDeptIds.value[selectedDeptIds.value.length - 1];
      if (lastSelectedId) {
        selectedDeptIds.value = [lastSelectedId];
      }
    } else {
      // checkStrictly 为 true 时，selectedDeptIds 是一个对象
      const checked = selectedDeptIds.value.checked || [];
      if (checked.length > 0) {
        const lastSelectedId = checked[checked.length - 1];
        selectedDeptIds.value = {
          checked: [lastSelectedId!],
          halfChecked: [],
        };
      }
    }
  }
}
</script>
<template>
  <Modal :title="title" key="dept-select-modal" class="w-2/5 oa-dept-select-modal">
    <Row class="h-full oa-dept-select-shell">
      <Col :span="24">
        <div class="oa-dept-select-tree-shell h-full">
          <Tree
            :tree-data="deptTree"
            v-if="deptTree.length > 0"
            v-model:checked-keys="selectedDeptIds"
            :checkable="true"
            :check-strictly="checkStrictly"
            :field-names="{ title: 'name', key: 'id' }"
            :default-expand-all="true"
            @check="handleCheck"
          />
        </div>
      </Col>
    </Row>
  </Modal>
</template>

<style lang="scss" scoped>
.oa-dept-select-shell {
  min-height: 420px;
}

.oa-dept-select-tree-shell {
  height: 100%;
  min-height: 420px;
  overflow: auto;
  border-top: 1px solid var(--oa-shell-border);
  border-bottom: 1px solid var(--oa-shell-border);
  padding: 12px 0;
}

.oa-dept-select-tree-shell :deep(.ant-tree) {
  background: transparent;
}

.oa-dept-select-tree-shell :deep(.ant-tree-treenode) {
  padding: 2px 0;
}

.oa-dept-select-tree-shell :deep(.ant-tree-node-content-wrapper) {
  border-radius: 0;
}
</style>

<style lang="scss">
body.oa-lite-theme-light .oa-dept-select-modal,
body.oa-lite-theme-dark .oa-dept-select-modal {
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-light .oa-dept-select-modal .ant-tree,
body.oa-lite-theme-dark .oa-dept-select-modal .ant-tree {
  background: transparent !important;
  color: var(--oa-ink) !important;
}

body.oa-lite-theme-light .oa-dept-select-modal .ant-tree-node-content-wrapper:hover,
body.oa-lite-theme-dark .oa-dept-select-modal .ant-tree-node-content-wrapper:hover {
  background: var(--oa-shell-surface-muted) !important;
}

body.oa-lite-theme-light .oa-dept-select-modal .ant-tree-node-content-wrapper.ant-tree-node-selected,
body.oa-lite-theme-light .oa-dept-select-modal .ant-tree-treenode-checkbox-checked .ant-tree-node-content-wrapper,
body.oa-lite-theme-dark .oa-dept-select-modal .ant-tree-node-content-wrapper.ant-tree-node-selected,
body.oa-lite-theme-dark .oa-dept-select-modal .ant-tree-treenode-checkbox-checked .ant-tree-node-content-wrapper {
  background: transparent !important;
  color: var(--oa-accent) !important;
}
</style>
