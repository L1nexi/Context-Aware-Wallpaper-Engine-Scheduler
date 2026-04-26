<script setup lang="ts">
import { inject } from 'vue'
import { useI18n } from '@/composables/useI18n'

const { t, lang } = useI18n()
</script>

<template>
  <div class="top-bar">
    <span class="top-bar-title">{{ t('title') }}</span>
    <el-tag size="small" type="info">{{ lang.toUpperCase() }}</el-tag>
  </div>
</template>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  -webkit-app-region: drag;
}
.top-bar-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
</style>
