<script setup lang="ts">
import { useI18n } from '@/composables/useI18n'

const { lang } = useI18n()
</script>

<template>
  <div class="top-bar">
    <div></div>
    <el-tag size="small" type="info">{{ lang.toUpperCase() }}</el-tag>
  </div>
</template>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 6px 16px;
  background: #ffffff;
  border-bottom: 1px solid var(--el-border-color, #e4e7ed);
  flex-shrink: 0;
}
</style>
