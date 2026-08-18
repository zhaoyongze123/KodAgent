<script lang="ts" setup>
import { onBeforeUnmount, onMounted } from 'vue';

import { AuthPageLayout } from '@vben/layouts';
import { preferences, updatePreferences } from '@vben/preferences';

const previousAuthPageLayout = preferences.app.authPageLayout;

onMounted(() => {
  if (preferences.app.authPageLayout !== 'panel-center') {
    updatePreferences({
      app: {
        authPageLayout: 'panel-center',
      },
    });
  }
});

onBeforeUnmount(() => {
  if (preferences.app.authPageLayout !== previousAuthPageLayout) {
    updatePreferences({
      app: {
        authPageLayout: previousAuthPageLayout,
      },
    });
  }
});
</script>

<template>
  <AuthPageLayout :copyright="false">
    <template #logo></template>
    <!-- 自定义工具栏 -->
    <!-- <template #toolbar></template> -->
  </AuthPageLayout>
</template>
