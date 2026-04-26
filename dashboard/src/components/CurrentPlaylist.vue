<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import type { TickState } from '@/composables/useApi'
import { Monitor } from '@element-plus/icons-vue'

const state = inject<Ref<TickState | null>>('state')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const loading = inject<Ref<boolean>>('loading')!

const playlistName = computed(() => state.value?.current_playlist || '')
const isEmpty = computed(() => !loading.value && !playlistName.value)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <el-icon><Monitor /></el-icon>
      <span>{{ t('currentPlaylist') }}</span>
    </div>
    <div class="panel-body">
      <el-skeleton v-if="loading" :rows="2" animated />
      <el-empty v-else-if="isEmpty" :description="t('waiting')" :image-size="60" />
      <div v-else class="playlist-name">{{ playlistName }}</div>
    </div>
  </div>
</template>
