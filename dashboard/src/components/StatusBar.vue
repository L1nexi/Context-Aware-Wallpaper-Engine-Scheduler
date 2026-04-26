<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import type { TickState } from '@/composables/useApi'

const state = inject<Ref<TickState | null>>('state')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const loading = inject<Ref<boolean>>('loading')!

const isPaused = computed(() => state.value?.paused ?? false)
const isFullscreen = computed(() => state.value?.fullscreen ?? false)
</script>

<template>
  <div class="panel full-width">
    <div class="panel-header">
      <span>{{ t('context') }}</span>
    </div>
    <div class="panel-body">
      <el-skeleton v-if="loading" :rows="1" animated />
      <div v-else class="status-badges">
        <el-tag v-if="!isPaused" type="success" size="large" effect="dark">
          {{ t('running') }}
        </el-tag>
        <el-tag v-if="isPaused" type="warning" size="large" effect="dark">
          {{ t('paused') }}
        </el-tag>
        <el-tag v-if="isFullscreen" type="danger" size="large" effect="dark">
          {{ t('fullscreen') }}
        </el-tag>
        <el-tag v-if="!isPaused && !isFullscreen" size="large" effect="plain" type="info">
          {{ t('waiting') }}
        </el-tag>
      </div>
    </div>
  </div>
</template>
