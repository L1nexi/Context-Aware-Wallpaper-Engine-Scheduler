<script setup lang="ts">
import { inject, computed, type Ref } from 'vue'
import type { TickState } from '@/composables/useApi'
import { CollectionTag } from '@element-plus/icons-vue'

const state = inject<Ref<TickState | null>>('state')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const loading = inject<Ref<boolean>>('loading')!

const tags = computed(() => state.value?.top_tags ?? [])
const maxWeight = computed(() => {
  if (tags.value.length === 0) return 1
  return Math.max(...tags.value.map(t => t.weight), 0.001)
})
const isEmpty = computed(() => !loading.value && tags.value.length === 0)
</script>

<template>
  <div class="panel">
    <div class="panel-header">
      <el-icon><CollectionTag /></el-icon>
      <span>{{ t('topTags') }}</span>
    </div>
    <div class="panel-body">
      <el-skeleton v-if="loading" :rows="4" animated />
      <el-empty v-else-if="isEmpty" :description="t('noData')" :image-size="60" />
      <div v-else class="tag-list">
        <div v-for="{ tag, weight } in tags" :key="tag" class="tag-row">
          <span class="tag-label">{{ tag }}</span>
          <div class="tag-bar-bg">
            <div
              class="tag-bar-fill"
              :style="{ width: (weight / maxWeight * 100).toFixed(1) + '%' }"
            />
          </div>
          <span class="tag-weight">{{ weight.toFixed(3) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
