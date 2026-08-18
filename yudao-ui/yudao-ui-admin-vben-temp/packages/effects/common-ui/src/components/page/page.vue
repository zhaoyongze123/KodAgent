<script setup lang="ts">
import type { StyleValue } from 'vue';

import type { PageProps } from './types';

import { computed, nextTick, onMounted, ref, useTemplateRef } from 'vue';

import { CSS_VARIABLE_LAYOUT_CONTENT_HEIGHT } from '@vben-core/shared/constants';
import { cn } from '@vben-core/shared/utils';

defineOptions({
  name: 'Page',
});

const { autoContentHeight = false, heightOffset = 0 } =
  defineProps<PageProps>();

const headerHeight = ref(0);
const footerHeight = ref(0);
const docHeight = ref(0);
const shouldAutoHeight = ref(false);

const headerRef = useTemplateRef<HTMLDivElement>('headerRef');
const footerRef = useTemplateRef<HTMLDivElement>('footerRef');
const docRef = useTemplateRef<HTMLDivElement>('docRef');

const contentStyle = computed<StyleValue>(() => {
  if (autoContentHeight) {
    return {
      height: `calc(var(${CSS_VARIABLE_LAYOUT_CONTENT_HEIGHT}) - ${headerHeight.value}px - ${footerHeight.value}px - ${docHeight.value}px - ${typeof heightOffset === 'number' ? `${heightOffset}px` : heightOffset})`,
      overflowY: shouldAutoHeight.value ? 'auto' : 'unset',
    };
  }
  return {};
});

async function calcContentHeight() {
  if (!autoContentHeight) {
    return;
  }
  await nextTick();
  headerHeight.value = headerRef.value?.offsetHeight || 0;
  footerHeight.value = footerRef.value?.offsetHeight || 0;
  docHeight.value = docRef.value?.offsetHeight || 0;
  setTimeout(() => {
    shouldAutoHeight.value = true;
  }, 30);
}

function isDocAlertEnable(): boolean {
  return false;
}

onMounted(() => {
  calcContentHeight();
});
</script>

<template>
  <div class="oa-page-shell relative flex min-h-full min-w-0 flex-col">
    <div
      v-if="$slots.doc && isDocAlertEnable()"
      ref="docRef"
      :class="
        cn(
          'oa-page-doc border-border relative mx-4 flex items-start border-b',
        )
      "
    >
      <div class="flex-auto">
        <slot name="doc"></slot>
      </div>
    </div>

    <div
      v-if="
        description ||
        $slots.description ||
        title ||
        $slots.title ||
        $slots.extra
      "
      ref="headerRef"
      :class="
        cn(
          'oa-page-header relative flex items-end border-b border-border px-0 py-5',
          headerClass,
        )
      "
    >
      <div class="flex-auto">
        <slot name="title">
          <div v-if="title" class="oa-page-title mb-2 flex">
            {{ title }}
          </div>
        </slot>

        <slot name="description">
          <p v-if="description" class="oa-page-description">
            {{ description }}
          </p>
        </slot>
      </div>

      <div v-if="$slots.extra">
        <slot name="extra"></slot>
      </div>
    </div>

    <div
      :class="cn('oa-page-content h-full min-w-0 px-5 py-4', contentClass)"
      :style="contentStyle"
    >
      <slot></slot>
    </div>
    <div
      v-if="$slots.footer"
      ref="footerRef"
      :class="cn('oa-page-footer align-center flex px-6 py-4', footerClass)"
    >
      <slot name="footer"></slot>
    </div>
  </div>
</template>

<style scoped>
.oa-page-shell {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  border-radius: 0;
  background: transparent;
}

.oa-page-doc {
  margin-top: 16px;
  background: transparent;
  box-shadow: none;
}

.oa-page-header {
  gap: 16px;
  background: transparent;
}

.oa-page-title {
  color: var(--oa-ink);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.2;
}

.oa-page-description {
  max-width: 70ch;
  color: var(--oa-ink-soft);
  font-size: 14px;
  line-height: 1.75;
}

.oa-page-content {
  width: 100%;
  min-width: 0;
  max-width: 100%;
  background: transparent;
}

.oa-page-footer {
  border-top: 1px solid var(--oa-shell-border);
  background: transparent;
}
</style>
