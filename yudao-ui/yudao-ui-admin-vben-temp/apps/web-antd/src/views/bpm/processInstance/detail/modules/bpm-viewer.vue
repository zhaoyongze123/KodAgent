<script setup lang="ts">
import { ref, watch } from 'vue';

import { MyProcessViewer } from '#/views/bpm/components/bpmn-process-designer/package';

defineOptions({ name: 'ProcessInstanceBpmnViewer' });

const props = withDefaults(
  defineProps<{
    bpmnXml?: string;
    loading?: boolean; // 是否加载中
    modelView?: object;
  }>(),
  {
    loading: false,
    modelView: () => ({}),
    bpmnXml: '',
  },
);

// BPMN 流程图数据
const view = ref({
  bpmnXml: '',
});

/** 监控 modelView 更新 */
watch(
  () => props.modelView,
  async (newModelView) => {
    // 加载最新
    if (newModelView) {
      // @ts-expect-error: viewer instance type is broader than local ref typing
      view.value = newModelView;
    }
  },
  { immediate: true },
);

/** 监听 bpmnXml */
watch(
  () => props.bpmnXml,
  (value) => {
    view.value.bpmnXml = value;
  },
  { immediate: true },
);
</script>

<template>
  <div v-loading="loading" class="oa-bpmn-viewer-shell">
    <div class="oa-bpmn-viewer-body">
      <MyProcessViewer
        key="processViewer"
        :xml="view.bpmnXml"
        :view="view"
        class="oa-bpmn-viewer-canvas h-full min-h-[500px] w-full"
      />
    </div>
  </div>
</template>

<style scoped>
.oa-bpmn-viewer-shell {
  display: flex;
  min-height: 520px;
  flex-direction: column;
  min-width: 0;
  border-top: 1px solid var(--oa-shell-border);
  background: transparent;
}

.oa-bpmn-viewer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 0 14px;
  border-bottom: 1px solid var(--oa-shell-border);
}

.oa-bpmn-viewer-eyebrow {
  color: var(--oa-ink-faint);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.02em;
  text-transform: uppercase;
}

.oa-bpmn-viewer-title {
  margin-top: 6px;
  color: var(--oa-ink);
  font-size: 18px;
  font-weight: 600;
}

.oa-bpmn-viewer-caption {
  color: var(--oa-ink-soft);
  font-size: 12px;
  line-height: 1.6;
  text-align: right;
}

.oa-bpmn-viewer-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 18px 0 0;
  background:
    linear-gradient(
      180deg,
      color-mix(in srgb, var(--oa-grid-line) 100%, transparent),
      color-mix(in srgb, var(--oa-grid-line) 100%, transparent)
    )
    0 0 / 100% 1px no-repeat;
}

.oa-bpmn-viewer-canvas :deep(.bpmn-js-container),
.oa-bpmn-viewer-canvas :deep(svg) {
  border-radius: 0;
}
</style>
