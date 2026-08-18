<script lang="ts" setup>
import AuthPortal from './components/auth-portal.vue';

defineOptions({ name: 'CodeLogin' });
</script>

<template>
  <AuthPortal initial-mode="mobile" />
</template>
