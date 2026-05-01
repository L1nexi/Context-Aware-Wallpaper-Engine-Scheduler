<script setup lang="ts">
import { ref, computed, inject, type Ref } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import type { AppConfig } from '@/composables/useConfig'

const config = inject<Ref<AppConfig | null>>('config')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

const tagPresets = inject<Ref<string[]>>('tagPresets')!

const selectedTag = ref<string | null>(null)

const tagList = computed(() => {
  if (!config.value) return []
  return Object.keys(config.value.tags).sort()
})

const allKnownTags = computed(() => [...new Set([...tagPresets.value, ...tagList.value])].sort())

const fallbacks = computed(() => {
  if (!config.value || !selectedTag.value) return []
  const fb = config.value.tags[selectedTag.value]?.fallback
  if (!fb) return []
  return Object.entries(fb).map(([target, weight]) => ({ target, weight }))
})

function selectTag(tag: string) {
  if (!config.value) return
  if (!config.value.tags[tag]) {
    config.value.tags[tag] = { fallback: {} }
  }
  selectedTag.value = tag
}

function addTag() {
  if (!config.value) return
  ElMessageBox.prompt(t('tags_enter_name_hint'), t('tags_add_tag'), {
    inputPattern: /^#/,
    inputErrorMessage: t('tags_enter_name_error'),
  }).then(({ value }) => {
    const key = value.trim()
    if (!config.value!.tags[key]) {
      config.value!.tags[key] = { fallback: {} }
    }
    selectedTag.value = key
  }).catch(() => {})
}

function addFallback() {
  if (!config.value || !selectedTag.value) return
  config.value.tags[selectedTag.value]!.fallback[''] = 0.5
}

function removeFallback(target: string) {
  if (!config.value || !selectedTag.value) return
  delete config.value.tags[selectedTag.value]!.fallback[target]
}

function updateFallbackWeight(target: string, weight: number) {
  if (!config.value || !selectedTag.value) return
  const fb = config.value.tags[selectedTag.value]!.fallback
  if (fb[target] !== undefined) {
    fb[target] = weight
  }
}

function updateFallbackTarget(oldTarget: string, newTarget: string) {
  if (!config.value || !selectedTag.value) return
  const fb = config.value.tags[selectedTag.value]!.fallback
  const weight = fb[oldTarget]
  delete fb[oldTarget]
  if (newTarget.trim()) {
    fb[newTarget.trim()] = weight ?? 0.5
  }
}
</script>

<template>
  <div class="tag-editor">
    <!-- Left: tag list -->
    <div class="editor-left">
      <div class="editor-left-header">{{ t('config_tags_tab') }}</div>
      <div
        v-for="tag in tagList"
        :key="tag"
        class="editor-item"
        :class="{ selected: selectedTag === tag }"
        @click="selectTag(tag)"
      >{{ tag }}</div>
      <el-button size="small" :icon="Plus" style="margin-top: 8px; width: 100%" @click="addTag">
        {{ t('tags_add_tag') }}
      </el-button>
    </div>

    <!-- Right: fallback table -->
    <div class="editor-right">
      <template v-if="selectedTag">
        <div class="editor-right-header">{{ t('tags_fallbacks_for') }} <strong>{{ selectedTag }}</strong></div>

        <div v-if="fallbacks.length === 0" style="color: #909399; font-size: 13px; padding: 12px 0">
          {{ t('tags_no_fallbacks') }}
        </div>

        <div v-for="(fb, idx) in fallbacks" :key="idx" class="fallback-row">
          <el-select
            :model-value="fb.target"
            :placeholder="t('tags_target_tag')"
            filterable
            allow-create
            default-first-option
            style="flex: 1"
            @update:model-value="(val: string) => updateFallbackTarget(fb.target, val)"
          >
            <el-option
              v-for="t in allKnownTags" :key="t"
              :label="t" :value="t"
            />
          </el-select>
          <el-slider
            :model-value="fb.weight"
            :min="0" :max="2" :step="0.1"
            :format-tooltip="(val: number) => val.toFixed(1)"
            style="width: 160px; margin: 0 8px"
            @update:model-value="(val: number) => updateFallbackWeight(fb.target, val)"
          />
          <el-button size="small" type="danger" :icon="Delete" circle @click="removeFallback(fb.target)" />
        </div>

        <el-button size="small" :icon="Plus" style="margin-top: 8px" @click="addFallback">
          {{ t('tags_add_fallback') }}
        </el-button>
      </template>
      <el-empty v-else :image-size="48" :description="t('noData')" style="margin-top: 40px" />
    </div>
  </div>
</template>

<style scoped>
.tag-editor {
  display: flex; gap: 16px; height: 100%; min-height: 300px;
}
.editor-left {
  width: 180px; flex-shrink: 0;
  border-right: 1px solid var(--el-border-color, #e4e7ed);
  padding-right: 8px; overflow-y: auto;
}
.editor-left-header {
  font-size: 12px; color: #909399; margin-bottom: 8px; font-weight: 600;
}
.editor-item {
  padding: 6px 10px; font-size: 13px; cursor: pointer;
  border-radius: 4px; transition: background 0.15s;
}
.editor-item:hover { background: #f0f2f5; }
.editor-item.selected { background: #ecf5ff; color: #409eff; font-weight: 600; }
.editor-right {
  flex: 1; overflow-y: auto; min-width: 0;
}
.editor-right-header {
  font-size: 13px; margin-bottom: 12px; color: #606266;
}
.fallback-row {
  display: flex; align-items: center; padding: 4px 0; gap: 4px;
}
</style>
