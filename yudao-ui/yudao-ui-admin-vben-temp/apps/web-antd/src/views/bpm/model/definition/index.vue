<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { BpmProcessDefinitionApi } from '#/api/bpm/definition';

import { onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { Page, useVbenModal } from '@vben/common-ui';
import { BpmModelFormType } from '@vben/constants';

import { Button, Tooltip } from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getProcessDefinitionPage } from '#/api/bpm/definition';

import FormCreateDetail from '../../form/modules/detail.vue';
import { useGridColumns } from './data';

defineOptions({ name: 'BpmProcessDefinition' });

const route = useRoute();
const router = useRouter();

const [FormCreateDetailModal, formCreateDetailModalApi] = useVbenModal({
  connectedComponent: FormCreateDetail,
  destroyOnClose: true,
});

/** 刷新表格 */
function handleRefresh() {
  gridApi.query();
}

/** 查看表单详情 */
async function handleFormDetail(
  row: BpmProcessDefinitionApi.ProcessDefinition,
) {
  if (row.formType === BpmModelFormType.NORMAL) {
    const data = {
      id: row.formId,
    };
    formCreateDetailModalApi.setData(data).open();
  } else {
    await router.push({
      path: row.formCustomCreatePath,
    });
  }
}

/** 恢复流程模型 */
async function handleRecover(row: BpmProcessDefinitionApi.ProcessDefinition) {
  await router.push({
    name: 'BpmModelUpdate',
    params: { id: row.id, type: 'definition' },
  });
}

const [Grid, gridApi] = useVbenVxeGrid({
  gridOptions: {
    columns: useGridColumns(),
    height: 'auto',
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }) => {
          return await getProcessDefinitionPage({
            pageNo: page.currentPage,
            pageSize: page.pageSize,
            key: route.query.key as string,
          });
        },
      },
    },
    rowConfig: {
      keyField: 'id',
      isHover: true,
    },
    toolbarConfig: {
      refresh: true,
    },
  } as VxeTableGridOptions<BpmProcessDefinitionApi.ProcessDefinition>,
});

/** 初始化 */
onMounted(() => {
  handleRefresh();
});
</script>

<template>
  <Page auto-content-height title="流程定义">
    <FormCreateDetailModal />
    <Grid table-title="流程定义列表">
      <template #startUsers="{ row }">
        <template
          v-if="
            (!row.startUsers || row.startUsers.length === 0) &&
            (!row.startDepts || row.startDepts.length === 0)
          "
        >
          全部可发起
        </template>
        <template v-else-if="row.startUsers?.length === 1">
          {{ row.startUsers[0]!.nickname }}
        </template>
        <template v-else-if="row.startDepts?.length === 1">
          {{ row.startDepts[0]!.name }}
        </template>
        <template v-else-if="row.startDepts && row.startDepts.length > 1">
          <Tooltip
            placement="top"
            :title="row.startDepts.map((dept: any) => dept.name).join('、')"
          >
            {{ row.startDepts[0]!.name }}等
            {{ row.startDepts.length }} 个部门可发起
          </Tooltip>
        </template>
        <template v-else-if="row.startUsers && row.startUsers.length > 1">
          <Tooltip
            placement="top"
            :title="row.startUsers.map((user: any) => user.nickname).join(',')"
          >
            {{ row.startUsers[0]!.nickname }}等
            {{ row.startUsers.length }} 人可发起
          </Tooltip>
        </template>
        <template v-else>-</template>
      </template>
      <template #visible="{ row }">
        <span v-if="row.visible">上架中</span>
        <span v-else>已下架</span>
      </template>
      <template #suspensionState="{ row }">
        <span v-if="row.suspensionState === 1">运行中</span>
        <span v-else>已停用</span>
      </template>
      <template #formInfo="{ row }">
        <Button
          v-if="row.formType === BpmModelFormType.NORMAL"
          type="link"
          @click="handleFormDetail(row)"
        >
          <span>{{ row.formName }}</span>
        </Button>
        <Button
          v-else-if="row.formType === BpmModelFormType.CUSTOM"
          type="link"
          @click="handleFormDetail(row)"
        >
          <span>{{ row.formCustomCreatePath }}</span>
        </Button>
        <span v-else>暂无表单</span>
      </template>
      <template #actions="{ row }">
        <TableAction
          :actions="[
            {
              label: '恢复',
              type: 'link',
              auth: ['bpm:model:update'],
              onClick: handleRecover.bind(null, row),
            },
          ]"
        />
      </template>
    </Grid>
  </Page>
</template>
