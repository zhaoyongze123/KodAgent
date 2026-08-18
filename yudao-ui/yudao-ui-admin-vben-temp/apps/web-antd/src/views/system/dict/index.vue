<script lang="ts" setup>
import { ref } from 'vue';

import { DocAlert, Page } from '@vben/common-ui';

import DataGrid from './modules/data-grid.vue';
import TypeGrid from './modules/type-grid.vue';

const searchDictType = ref<string>(); // 搜索的字典类型

function handleDictTypeSelect(dictType: string) {
  searchDictType.value = dictType;
}
</script>

<template>
  <Page auto-content-height title="字典管理">
    <template #doc>
      <DocAlert title="字典管理" url="https://doc.iocoder.cn/system-dict/" />
    </template>

    <div class="oa-workspace-page">

      <section class="oa-workspace-panel">
        <div class="oa-workspace-panel-header">
          <div>
            <h3 class="oa-workspace-panel-title">字典配置工作区</h3>
          </div>
        </div>
        <div class="oa-workspace-panel-body">
          <div class="flex h-full gap-4 max-md:flex-col">
            <div class="min-w-0 flex-1">
              <TypeGrid @select="handleDictTypeSelect" />
            </div>
            <div class="min-w-0 flex-1">
              <DataGrid :dict-type="searchDictType" />
            </div>
          </div>
        </div>
      </section>
    </div>
  </Page>
</template>
