<script lang="ts" setup>
import { getTripPage } from '#/api/bpm/oa/trip';
import OAIndexPage from '#/views/bpm/oa/shared/index-page.vue';
</script>

<template>
  <OAIndexPage module-key="trip" :fetch-page="getTripPage" />
</template>
