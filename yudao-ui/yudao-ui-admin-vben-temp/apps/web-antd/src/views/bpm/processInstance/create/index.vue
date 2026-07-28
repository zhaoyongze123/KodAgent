<script lang="ts" setup>
import type { BpmCategoryApi } from '#/api/bpm/category';
import type { BpmProcessDefinitionApi } from '#/api/bpm/definition';

import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { Page } from '@vben/common-ui';
import { groupBy } from '@vben/utils';

import {
  Col,
  InputSearch,
  message,
  Row,
  Space,
  Tabs,
  Tooltip,
} from 'ant-design-vue';

import { getApprovalTemplateList } from '#/api/bpm/approvalTemplate';
import { getCategorySimpleList } from '#/api/bpm/category';
import { getProcessInstance } from '#/api/bpm/processInstance';

import ProcessDefinitionDetail from './modules/form.vue';

defineOptions({ name: 'BpmProcessInstanceCreate' });

const route = useRoute();

const loading = ref(true); // 加载中
const processInstanceId: any = route.query.processInstanceId; // 流程实例编号。场景：重新发起时
const processDefinitionIdQuery = computed(() => {
  const value = route.query.processDefinitionId;
  return Array.isArray(value) ? value[0] : value;
});

const categoryList: any = ref([]); // 分类的列表
const activeCategory = ref(''); // 当前选中的分类

const searchName = ref(''); // 当前搜索关键字
const processDefinitionList = ref<BpmProcessDefinitionApi.ProcessDefinition[]>(
  [],
); // 流程定义的列表
const filteredProcessDefinitionList = ref<
  BpmProcessDefinitionApi.ProcessDefinition[]
>([]); // 用于存储搜索过滤后的流程定义

const selectProcessDefinition = ref(); // 选择的流程定义
const processDefinitionDetailRef = ref();

/** 查询列表 */
async function getList() {
  loading.value = true;
  try {
    // 1.1 所有流程分类数据
    await loadCategoryList();
    // 1.2 所有流程定义数据
    await loadProcessDefinitionList();

    // 2. 如果 processInstanceId 非空，说明是重新发起
    if (processInstanceId?.length > 0) {
      const processInstance = await getProcessInstance(processInstanceId);
      if (!processInstance) {
        message.error('重新发起流程失败，原因：流程实例不存在');
        return;
      }
      const processDefinition = processDefinitionList.value.find(
        (item: any) => item.key === processInstance.processDefinition?.key,
      );
      if (!processDefinition) {
        message.error('重新发起流程失败，原因：流程定义不存在');
        return;
      }
      await handleSelect(processDefinition, processInstance.formVariables);
      return;
    }

    // 3. 如果 processDefinitionId 非空，直接进入对应流程定义
    if (processDefinitionIdQuery.value) {
      const processDefinition = processDefinitionList.value.find(
        (item) => item.id === processDefinitionIdQuery.value,
      );
      if (!processDefinition) {
        message.error('发起流程失败，原因：流程定义不存在');
        return;
      }
      await handleSelect(processDefinition);
    }
  } finally {
    loading.value = false;
  }
}

/** 获取所有流程分类数据 */
async function loadCategoryList() {
  categoryList.value = await getCategorySimpleList();
}

/** 获取所有流程定义数据 */
async function loadProcessDefinitionList() {
  processDefinitionList.value = await getApprovalTemplateList();

  // 空搜索，初始化相关数据
  handleQuery();
}

/** 搜索流程 */
function handleQuery() {
  if (searchName.value.trim()) {
    // 如果有搜索关键字，进行过滤
    filteredProcessDefinitionList.value = processDefinitionList.value.filter(
      (definition: any) =>
        definition.name.toLowerCase().includes(searchName.value.toLowerCase()),
    );
    // 如果有匹配，切换到第一个包含匹配结果的分类
    activeCategory.value = availableCategories.value[0]?.name;
  } else {
    // 如果没有搜索关键字，恢复所有数据
    filteredProcessDefinitionList.value = processDefinitionList.value;
    // 恢复到第一个可用分类
    if (availableCategories.value.length > 0) {
      activeCategory.value = availableCategories.value[0].code;
    }
  }
}

/** 流程定义的分组 */
const processDefinitionGroup = computed(() => {
  if (!processDefinitionList.value?.length) {
    return {};
  }
  // 按照 categoryList 的顺序重新组织数据
  const grouped = groupBy(filteredProcessDefinitionList.value, 'category');
  const orderedGroup: Record<
    string,
    BpmProcessDefinitionApi.ProcessDefinition[]
  > = {};
  categoryList.value.forEach((category: BpmCategoryApi.Category) => {
    if (grouped[category.code]) {
      orderedGroup[category.code] = grouped[
        category.code
      ] as BpmProcessDefinitionApi.ProcessDefinition[];
    }
  });
  return orderedGroup;
});

/** 处理选择流程的按钮操作 */
async function handleSelect(
  row: BpmProcessDefinitionApi.ProcessDefinition,
  formVariables?: any,
) {
  // 设置选择的流程
  selectProcessDefinition.value = row;
  // 初始化流程定义详情
  await nextTick();
  processDefinitionDetailRef.value?.initProcessInfo(row, formVariables);
}

/** 过滤出有流程的分类列表。目的：只展示有流程的分类 */
const availableCategories = computed(() => {
  if (!categoryList.value?.length || !processDefinitionGroup.value) {
    return [];
  }
  // 获取所有有流程的分类代码
  const availableCategoryCodes = Object.keys(processDefinitionGroup.value);
  // 过滤出有流程的分类
  return categoryList.value.filter((category: BpmCategoryApi.Category) =>
    availableCategoryCodes.includes(category.code),
  );
});

/** 监听可用分类变化，自动设置正确的活动分类 */
watch(
  availableCategories,
  (newCategories) => {
    if (newCategories.length > 0) {
      // 如果当前活动分类不在可用分类中，切换到第一个可用分类
      const currentCategoryExists = newCategories.some(
        (category: BpmCategoryApi.Category) =>
          category.code === activeCategory.value,
      );
      if (!currentCategoryExists) {
        activeCategory.value = newCategories[0].code;
      }
    }
  },
  { immediate: true },
);

/** 初始化 */
onMounted(() => {
  getList();
});
</script>

<template>
  <Page auto-content-height>
    <!-- TODO @jason：这里交互，可以做成类似 vue3 + element-plus 那个一样，滚动切换分类哈？对标钉钉、飞书哈； -->
    <!-- 第一步，通过流程定义的列表，选择对应的流程 -->
    <template v-if="!selectProcessDefinition">
      <section
        class="oa-process-create-shell"
        :class="{
          'process-definition-container': filteredProcessDefinitionList?.length,
        }"
        v-loading="loading"
      >
        <header class="oa-process-create-head">
          <div class="oa-process-create-search">
            <InputSearch
              v-model:value="searchName"
              class="!w-50%"
              placeholder="请输入流程名称检索"
              allow-clear
              @input="handleQuery"
              @clear="handleQuery"
            />
          </div>
        </header>

        <div v-if="filteredProcessDefinitionList?.length" class="oa-process-create-body">
          <Tabs v-model:active-key="activeCategory" tab-position="left">
            <Tabs.TabPane
              v-for="category in availableCategories"
              :key="category.code"
              :tab="category.name"
            >
              <Row :gutter="[16, 16]" :wrap="true">
                <Col
                  v-for="definition in processDefinitionGroup[category.code]"
                  :key="definition.id"
                  :xs="24"
                  :sm="12"
                  :md="8"
                  :lg="8"
                  :xl="6"
                >
                  <button
                    type="button"
                    class="oa-process-create-item"
                    :class="{
                      'animate-bounce-once !bg-[rgb(63_115_247_/_10%)]':
                        searchName.trim().length > 0,
                    }"
                    @click="handleSelect(definition)"
                  >
                    <div class="oa-process-create-item-row">
                      <img
                        v-if="definition.icon"
                        :src="definition.icon"
                        class="oa-process-create-item-icon"
                        alt="流程图标"
                      />
                      <div
                        v-else
                        class="oa-process-create-item-fallback"
                      >
                        <span class="oa-process-create-item-fallback-text">
                          {{ definition.name?.slice(0, 2) }}
                        </span>
                      </div>
                      <span class="oa-process-create-item-text">
                        <Tooltip
                          placement="topLeft"
                          :title="`${definition.description}`"
                        >
                          {{ definition.name }}
                        </Tooltip>
                      </span>
                    </div>
                  </button>
                </Col>
              </Row>
            </Tabs.TabPane>
          </Tabs>
        </div>
        <div v-else class="oa-process-create-empty">
          <Space direction="vertical" size="large">
            <span class="text-gray-500">没有找到搜索结果</span>
          </Space>
        </div>
      </section>
    </template>

    <!-- 第二步，填写表单，进行流程的提交 -->
    <ProcessDefinitionDetail
      v-else
      ref="processDefinitionDetailRef"
      :select-process-definition="selectProcessDefinition"
      @cancel="selectProcessDefinition = undefined"
    />
  </Page>
</template>

<style lang="scss" scoped>
@keyframes bounce {
  0%,
  50% {
    transform: translateY(-5px);
  }

  100% {
    transform: translateY(0);
  }
}

.animate-bounce-once {
  animation: bounce 0.5s ease;
}

.oa-process-create-shell {
  border-top: 1px solid var(--oa-shell-border);
  padding-top: 18px;
}

.oa-process-create-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-process-create-eyebrow {
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}

.oa-process-create-title {
  margin: 6px 0 0;
  color: var(--oa-ink);
  font-size: 20px;
  font-weight: 600;
}

.oa-process-create-search {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  min-width: 280px;
}

.oa-process-create-body {
  margin-top: 18px;
}

.oa-process-create-item {
  width: 100%;
  border: 0;
  border-top: 1px solid var(--oa-shell-border);
  background: transparent;
  padding: 16px 0;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.18s ease,
    color 0.18s ease;
}

.oa-process-create-item:hover {
  border-top-color: color-mix(in srgb, var(--oa-accent) 26%, var(--oa-shell-border));
}

.oa-process-create-item-row {
  display: flex;
  align-items: center;
}

.oa-process-create-item-icon {
  width: 48px;
  height: 48px;
  object-fit: contain;
}

.oa-process-create-item-fallback {
  display: flex;
  width: 48px;
  height: 48px;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--oa-shell-border);
  color: var(--oa-accent);
}

.oa-process-create-item-fallback-text {
  font-size: 12px;
  font-weight: 600;
}

.oa-process-create-item-text {
  margin-left: 12px;
  flex: 1;
  min-width: 0;
  color: var(--oa-ink);
  font-size: 15px;
}

.oa-process-create-empty {
  padding: 96px 0;
  text-align: center;
}
</style>
