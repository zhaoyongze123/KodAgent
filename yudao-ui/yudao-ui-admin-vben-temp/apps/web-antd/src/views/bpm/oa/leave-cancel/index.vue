<script lang="ts" setup>
import { getLeaveCancelPage } from '#/api/bpm/oa/leave-cancel';
import OAIndexPage from '#/views/bpm/oa/shared/index-page.vue';
</script>

<template>
  <OAIndexPage module-key="leaveCancel" :fetch-page="getLeaveCancelPage" />
</template>
