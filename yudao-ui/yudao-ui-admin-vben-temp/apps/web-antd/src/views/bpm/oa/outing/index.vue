<script lang="ts" setup>
import { getOutingPage } from '#/api/bpm/oa/outing';
import OAIndexPage from '#/views/bpm/oa/shared/index-page.vue';
</script>

<template>
  <OAIndexPage module-key="outing" :fetch-page="getOutingPage" />
</template>
