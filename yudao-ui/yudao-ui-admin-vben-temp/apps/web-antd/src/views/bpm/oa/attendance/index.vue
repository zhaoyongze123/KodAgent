<script lang="ts" setup>
import { getAttendancePage } from '#/api/bpm/oa/attendance';
import OAIndexPage from '#/views/bpm/oa/shared/index-page.vue';
</script>

<template>
  <OAIndexPage module-key="attendance" :fetch-page="getAttendancePage" />
</template>
