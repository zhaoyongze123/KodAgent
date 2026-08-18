<script lang="ts" setup>
import { getExpensePage } from '#/api/bpm/oa/expense';
import OAIndexPage from '#/views/bpm/oa/shared/index-page.vue';
</script>

<template>
  <OAIndexPage module-key="expense" :fetch-page="getExpensePage" />
</template>
