<script lang="ts" setup>
import { getOvertimePage } from '#/api/bpm/oa/overtime';
import OAIndexPage from '#/views/bpm/oa/shared/index-page.vue';
</script>

<template>
  <OAIndexPage module-key="overtime" :fetch-page="getOvertimePage" />
</template>
