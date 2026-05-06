# Config UI Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Advanced" placeholder tab with functional Policies and Tags editors, add dirty-state guard, batch tag add in playlist editor, and restructure ConfigView layout.

**Architecture:** Two new components (PolicyEditor, TagEditor) follow the same left-list/right-detail pattern. ConfigView orchestrates them via `provide`/`inject` for shared state. `useConfig` gains dirty-state tracking (`isDirty` ref). No backend changes.

**Tech Stack:** Vue 3 + TypeScript + Element Plus 2.13.7 (el-tabs, el-slider, el-input-number, el-select, el-switch, el-input password)

---

### Task 1: Add i18n keys

**Files:**
- Modify: `dashboard/src/i18n/en.json`
- Modify: `dashboard/src/i18n/zh.json`

- [ ] **Step 1: Add English i18n keys**

In `dashboard/src/i18n/en.json`, replace the placeholder keys (`config_advanced`, `config_advanced_placeholder`, `config_advanced_placeholder2`) and add new keys:

```json
"config_policies": "Policies",
"config_tags_tab": "Tags",
"config_playlists_intro": "Configure your Wallpaper Engine playlists and their tag affinities. Each playlist is matched against environmental signals using the tag vector space.",
"config_policies_intro": "Manage environmental sensing policies. Each policy contributes a weighted signal to the playlist matching algorithm.",
"config_tags_intro": "When a policy emits a tag not present in any playlist, energy cascades along fallback edges until a known tag is reached.",
"config_scheduling_intro": "Control when and how playlist switches occur based on system conditions.",

"policy_activity": "Activity",
"policy_time": "Time",
"policy_season": "Season",
"policy_weather": "Weather",
"policy_enabled": "Enabled",
"policy_weight_scale": "Weight Scale",
"policy_weight_scale_tip": "Global priority multiplier for this policy's signal",

"activity_process_rules": "Process Rules",
"activity_title_rules": "Title Rules",
"activity_smoothing_window": "Smoothing Window",
"activity_add_rule": "Add Rule",
"activity_process_placeholder": "e.g. code.exe",
"activity_title_placeholder": "e.g. Visual Studio",

"time_auto": "Auto",
"time_day_start": "Day Start Hour",
"time_night_start": "Night Start Hour",
"time_day_start_tip": "Hour when daytime period begins (0-24)",
"time_night_start_tip": "Hour when nighttime period begins (0-24)",

"season_spring_peak": "Spring Peak",
"season_summer_peak": "Summer Peak",
"season_autumn_peak": "Autumn Peak",
"season_winter_peak": "Winter Peak",

"weather_api_key": "API Key",
"weather_lat": "Latitude",
"weather_lon": "Longitude",
"weather_fetch_interval": "Fetch Interval (s)",
"weather_request_timeout": "Request Timeout (s)",
"weather_warmup_timeout": "Warmup Timeout (s)",

"tags_add_tag": "Add Tag",
"tags_fallbacks_for": "Fallbacks for",
"tags_target_tag": "Target Tag",
"tags_add_fallback": "Add Fallback",
"tags_weight": "Weight",
"tags_no_fallbacks": "No fallback edges defined",

"validation_required": "This field is required",
"validation_invalid_path": "Must be a valid .exe path",
"validation_invalid_name": "Only letters, numbers, and underscores",
"validation_need_tags": "At least one tag is required",
"validation_weight_range": "Weight must be 0.0 – 2.0",
"validation_hour_range": "Hour must be 0 – 24",
"validation_lat_range": "Latitude must be -90 to 90",
"validation_lon_range": "Longitude must be -180 to 180",

"config_unsaved_changes": "You have unsaved changes. Leave anyway?",
"config_auto_detect": "Auto-detect"
```

Remove these keys:
- `config_advanced`
- `config_advanced_placeholder`
- `config_advanced_placeholder2`

- [ ] **Step 2: Add Chinese i18n keys**

In `dashboard/src/i18n/zh.json`, add matching Chinese translations:

```json
"config_policies": "策略",
"config_tags_tab": "标签",
"config_playlists_intro": "配置 Wallpaper Engine 播放列表及其标签亲和力权重。每个播放列表通过标签向量空间与环境信号进行匹配。",
"config_policies_intro": "管理环境感知策略。每个策略向播放列表匹配算法贡献一个加权信号。",
"config_tags_intro": "当策略发出一个不存在于任何播放列表中的标签时，能量沿回退边级联传递，直到到达一个已知标签。",
"config_scheduling_intro": "控制系统条件和调度参数如何影响播放列表切换。",

"policy_activity": "活动",
"policy_time": "时间",
"policy_season": "季节",
"policy_weather": "天气",
"policy_enabled": "启用",
"policy_weight_scale": "权重比例",
"policy_weight_scale_tip": "该策略信号的全局优先级乘数",

"activity_process_rules": "进程规则",
"activity_title_rules": "标题规则",
"activity_smoothing_window": "平滑窗口",
"activity_add_rule": "添加规则",
"activity_process_placeholder": "如 code.exe",
"activity_title_placeholder": "如 Visual Studio",

"time_auto": "自动",
"time_day_start": "白天开始时间",
"time_night_start": "夜晚开始时间",
"time_day_start_tip": "白天时段开始的小时数 (0-24)",
"time_night_start_tip": "夜晚时段开始的小时数 (0-24)",

"season_spring_peak": "春峰值日",
"season_summer_peak": "夏峰值日",
"season_autumn_peak": "秋峰值日",
"season_winter_peak": "冬峰值日",

"weather_api_key": "API 密钥",
"weather_lat": "纬度",
"weather_lon": "经度",
"weather_fetch_interval": "获取间隔 (秒)",
"weather_request_timeout": "请求超时 (秒)",
"weather_warmup_timeout": "预热超时 (秒)",

"tags_add_tag": "添加标签",
"tags_fallbacks_for": "回退目标",
"tags_target_tag": "目标标签",
"tags_add_fallback": "添加回退",
"tags_weight": "权重",
"tags_no_fallbacks": "无回退边",

"validation_required": "此字段为必填",
"validation_invalid_path": "必须是有效的 .exe 路径",
"validation_invalid_name": "只能包含字母、数字和下划线",
"validation_need_tags": "至少需要一个标签",
"validation_weight_range": "权重必须在 0.0 – 2.0 之间",
"validation_hour_range": "小时必须在 0 – 24 之间",
"validation_lat_range": "纬度必须在 -90 到 90 之间",
"validation_lon_range": "经度必须在 -180 到 180 之间",

"config_unsaved_changes": "有未保存的修改，确定离开吗？",
"config_auto_detect": "自动检测"
```

Remove these keys:
- `config_advanced`
- `config_advanced_placeholder`
- `config_advanced_placeholder2`

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/i18n/en.json dashboard/src/i18n/zh.json
git commit -m "feat: add i18n keys for config UI completion"
```

---

### Task 2: Add dirty-state tracking to useConfig

**Files:**
- Modify: `dashboard/src/composables/useConfig.ts`

- [ ] **Step 1: Add `isDirty` computed and snapshot tracking**

In `useConfig()`, add after the existing refs:

```typescript
import { ref, computed } from 'vue'

// ... inside useConfig(), after const wePlaylists = ref<string[]>([])
let savedSnapshot = ''

const isDirty = computed(() => {
  if (!config.value) return false
  return JSON.stringify(config.value) !== savedSnapshot
})
```

- [ ] **Step 2: Update snapshot on fetch and save**

In `fetchConfig()`, after `config.value = await res.json()` add:

```typescript
savedSnapshot = JSON.stringify(config.value)
```

In `saveConfig()`, in the success branch (`if (!res.ok)` else), after `config.value = data` add:

```typescript
savedSnapshot = JSON.stringify(data)
```

- [ ] **Step 3: Export `isDirty`**

In the return object, add:

```typescript
isDirty,
```

The full return should be:

```typescript
return {
  config, loading, saveError, saving, isDirty,
  tagPresets, wePlaylists,
  fetchConfig, saveConfig, fetchTagPresets, scanPlaylists,
}
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/composables/useConfig.ts
git commit -m "feat: add dirty-state tracking to useConfig"
```

---

### Task 3: Create TagEditor.vue

**Files:**
- Create: `dashboard/src/components/TagEditor.vue`

- [ ] **Step 1: Create TagEditor component**

Write `dashboard/src/components/TagEditor.vue`:

```vue
<script setup lang="ts">
import { ref, computed, inject, type Ref } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import type { AppConfig } from '@/composables/useConfig'

const config = inject<Ref<AppConfig | null>>('config')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

const tagPresets = inject<string[]>('tagPresets')!

const selectedTag = ref<string | null>(null)

const tagList = computed(() => {
  if (!config.value) return []
  return Object.keys(config.value.tags).sort()
})

const allKnownTags = computed(() => [...new Set([...tagPresets, ...tagList.value])].sort())

const fallbacks = computed(() => {
  if (!config.value || !selectedTag.value) return []
  const fb = config.value.tags[selectedTag.value]?.fallback
  if (!fb) return []
  return Object.entries(fb).map(([target, weight]) => ({ target, weight }))
})

function selectTag(tag: string) {
  // Ensure tags dict exists
  if (!config.value) return
  if (!config.value.tags[tag]) {
    config.value.tags[tag] = { fallback: {} }
  }
  selectedTag.value = tag
}

function addTag() {
  if (!config.value) return
  const name = prompt('Tag name:')
  if (!name || !name.trim()) return
  const key = name.trim()
  if (!key.startsWith('#')) return
  if (!config.value.tags[key]) {
    config.value.tags[key] = { fallback: {} }
  }
  selectedTag.value = key
}

function addFallback() {
  if (!config.value || !selectedTag.value) return
  config.value.tags[selectedTag.value]!.fallback[''] = 0.5
}

function removeFallback(target: string) {
  if (!config.value || !selectedTag.value) return
  delete config.value.tags[selectedTag.value]!.fallback[target]
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
            v-model="fb.weight"
            :min="0" :max="2" :step="0.1"
            :format-tooltip="(val: number) => val.toFixed(1)"
            style="width: 160px; margin: 0 8px"
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
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/components/TagEditor.vue
git commit -m "feat: add TagEditor component for fallback graph editing"
```

---

### Task 4: Create PolicyEditor.vue

**Files:**
- Create: `dashboard/src/components/PolicyEditor.vue`

- [ ] **Step 1: Create PolicyEditor component (script)**

Write `dashboard/src/components/PolicyEditor.vue`. Activity rules use local reactive arrays (not generated keys) to avoid Vue key instability:

```vue
<script setup lang="ts">
import { ref, computed, inject, watch, reactive } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import type { AppConfig } from '@/composables/useConfig'

const config = inject<Ref<AppConfig | null>>('config')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const tagPresets = inject<string[]>('tagPresets')!

const KNOWN_POLICIES = ['activity', 'time', 'season', 'weather'] as const
type PolicyName = (typeof KNOWN_POLICIES)[number]

const selectedPolicy = ref<PolicyName | null>(null)

const policyList = computed(() => {
  if (!config.value) return []
  const policies = config.value.policies || {}
  return KNOWN_POLICIES.filter(p => p in policies)
})

type PolicyRecord = Record<string, unknown>

function getPolicyData(): PolicyRecord | null {
  if (!config.value || !selectedPolicy.value) return null
  return (config.value.policies as Record<string, PolicyRecord>)[selectedPolicy.value] ?? null
}

function isEnabled(policy?: string): boolean {
  const name = policy ?? selectedPolicy.value
  if (!name || !config.value) return true
  const d = (config.value.policies as Record<string, PolicyRecord>)?.[name]
  if (!d) return true
  return d.enabled !== false
}

function toggleEnabled() {
  const d = getPolicyData()
  if (!d) return
  d.enabled = !isEnabled()
}

function weightScale(): number {
  const d = getPolicyData()
  if (!d || d.weight_scale == null) return 1.0
  return d.weight_scale as number
}

// -- Activity rules: local reactive arrays, synced on mutation --
interface RuleRow { input: string; tag: string }

const processRules = reactive<RuleRow[]>([])
const titleRules = reactive<RuleRow[]>([])

function loadRules(data: PolicyRecord) {
  processRules.length = 0
  titleRules.length = 0
  for (const [input, tag] of Object.entries((data.process_rules as Record<string, string>) || {})) {
    processRules.push({ input, tag })
  }
  for (const [input, tag] of Object.entries((data.title_rules as Record<string, string>) || {})) {
    titleRules.push({ input, tag })
  }
}

function syncRulesToConfig(type: 'process_rules' | 'title_rules') {
  const d = getPolicyData()
  if (!d) return
  const rows = type === 'process_rules' ? processRules : titleRules
  const obj: Record<string, string> = {}
  for (const r of rows) {
    if (r.input.trim() && r.tag.trim()) obj[r.input.trim()] = r.tag.trim()
  }
  d[type] = obj
}

function addRule(type: 'process_rules' | 'title_rules') {
  const arr = type === 'process_rules' ? processRules : titleRules
  arr.push({ input: '', tag: '' })
  syncRulesToConfig(type)
}

function removeRule(type: 'process_rules' | 'title_rules', idx: number) {
  const arr = type === 'process_rules' ? processRules : titleRules
  arr.splice(idx, 1)
  syncRulesToConfig(type)
}

// Reload local state when policy switches
watch(selectedPolicy, (name) => {
  const d = name ? getPolicyData() : null
  if (d) loadRules(d)
})
</script>
```

- [ ] **Step 2: Create PolicyEditor component (template)**

```html
<template>
  <div class="policy-editor">
    <!-- Left: policy list -->
    <div class="editor-left">
      <div class="editor-left-header">{{ t('config_policies') }}</div>
      <div
        v-for="p in policyList"
        :key="p"
        class="editor-item"
        :class="{ selected: selectedPolicy === p }"
        @click="selectedPolicy = p"
      >
        <span class="policy-dot" :class="{ on: isEnabled(p) }"></span>
        {{ t('policy_' + p) }}
      </div>
    </div>

    <!-- Right: detail panel -->
    <div class="editor-right">
      <template v-if="selectedPolicy && getPolicyData()">
        <div class="detail-header">
          <span class="detail-title">{{ t('policy_' + selectedPolicy) }}</span>
          <el-switch :model-value="isEnabled()" size="small" @change="toggleEnabled()" />
        </div>

        <div class="detail-row">
          <span class="detail-label">{{ t('policy_weight_scale') }}</span>
          <el-slider
            :model-value="weightScale()"
            :min="0" :max="3" :step="0.1"
            show-input
            style="flex: 1; margin: 0 12px"
            @update:model-value="(val: number | undefined) => {
              const d = getPolicyData(); if (d) d.weight_scale = val ?? 1.0
            }"
          />
        </div>

        <!-- Activity -->
        <template v-if="selectedPolicy === 'activity'">
          <div class="rules-section">
            <div class="rules-title">{{ t('activity_process_rules') }}</div>
            <div v-for="(rule, idx) in processRules" :key="idx" class="rule-row">
              <el-input
                v-model="rule.input"
                :placeholder="t('activity_process_placeholder')"
                size="small"
                style="width: 160px"
                @change="syncRulesToConfig('process_rules')"
              />
              <span style="color: #909399; margin: 0 4px">→</span>
              <el-select
                v-model="rule.tag"
                :placeholder="t('config_tags')"
                filterable allow-create default-first-option
                size="small"
                style="flex: 1"
                @change="syncRulesToConfig('process_rules')"
              >
                <el-option v-for="t in tagPresets" :key="t" :label="t" :value="t" />
              </el-select>
              <el-button size="small" type="danger" :icon="Delete" circle @click="removeRule('process_rules', idx)" />
            </div>
            <el-button size="small" :icon="Plus" style="margin-top: 4px" @click="addRule('process_rules')">
              {{ t('activity_add_rule') }}
            </el-button>
          </div>

          <div class="rules-section">
            <div class="rules-title">{{ t('activity_title_rules') }}</div>
            <div v-for="(rule, idx) in titleRules" :key="idx" class="rule-row">
              <el-input
                v-model="rule.input"
                :placeholder="t('activity_title_placeholder')"
                size="small"
                style="width: 160px"
                @change="syncRulesToConfig('title_rules')"
              />
              <span style="color: #909399; margin: 0 4px">→</span>
              <el-select
                v-model="rule.tag"
                :placeholder="t('config_tags')"
                filterable allow-create default-first-option
                size="small"
                style="flex: 1"
                @change="syncRulesToConfig('title_rules')"
              >
                <el-option v-for="t in tagPresets" :key="t" :label="t" :value="t" />
              </el-select>
              <el-button size="small" type="danger" :icon="Delete" circle @click="removeRule('title_rules', idx)" />
            </div>
            <el-button size="small" :icon="Plus" style="margin-top: 4px" @click="addRule('title_rules')">
              {{ t('activity_add_rule') }}
            </el-button>
          </div>

          <div class="rules-section">
            <div class="rules-title">{{ t('activity_smoothing_window') }}</div>
            <el-input-number
              :model-value="(getPolicyData()!.smoothing_window as number) || 60"
              :min="1" size="small" style="width: 160px"
              @update:model-value="(val: number | undefined) => { getPolicyData()!.smoothing_window = val }"
            />
            <span style="font-size: 12px; color: #909399; margin-left: 6px">seconds</span>
          </div>
        </template>

        <!-- Time -->
        <template v-if="selectedPolicy === 'time'">
          <div class="rules-section">
            <div class="rules-title">{{ t('time_auto') }}</div>
            <el-switch
              :model-value="getPolicyData()!.auto !== false" size="small"
              @change="(val: boolean) => { getPolicyData()!.auto = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('time_day_start') }}</div>
            <el-input-number
              :model-value="(getPolicyData()!.day_start_hour as number) || 8"
              :min="0" :max="24" :disabled="getPolicyData()!.auto !== false" size="small" style="width: 120px"
              @update:model-value="(val: number | undefined) => { getPolicyData()!.day_start_hour = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('time_night_start') }}</div>
            <el-input-number
              :model-value="(getPolicyData()!.night_start_hour as number) || 20"
              :min="0" :max="24" :disabled="getPolicyData()!.auto !== false" size="small" style="width: 120px"
              @update:model-value="(val: number | undefined) => { getPolicyData()!.night_start_hour = val }"
            />
          </div>
        </template>

        <!-- Season -->
        <template v-if="selectedPolicy === 'season'">
          <div v-for="s in ['spring', 'summer', 'autumn', 'winter']" :key="s" class="rules-section">
            <div class="rules-title">{{ t('season_' + s + '_peak') }}</div>
            <el-input-number
              :model-value="(getPolicyData()![s + '_peak'] as number) || 80"
              :min="1" :max="365" size="small" style="width: 140px"
              @update:model-value="(val: number | undefined) => { getPolicyData()![s + '_peak'] = val }"
            />
            <span style="font-size:12px;color:#909399;margin-left:6px">day of year</span>
          </div>
        </template>

        <!-- Weather -->
        <template v-if="selectedPolicy === 'weather'">
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_api_key') }}</div>
            <el-input
              :model-value="(getPolicyData()!.api_key as string) || ''"
              type="password" show-password size="small" style="width: 280px"
              @update:model-value="(val: string) => { getPolicyData()!.api_key = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_lat') }}</div>
            <el-input-number
              :model-value="(getPolicyData()!.lat as number) || 0"
              :min="-90" :max="90" :precision="4" size="small" style="width: 180px"
              @update:model-value="(val: number | undefined) => { getPolicyData()!.lat = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_lon') }}</div>
            <el-input-number
              :model-value="(getPolicyData()!.lon as number) || 0"
              :min="-180" :max="180" :precision="4" size="small" style="width: 180px"
              @update:model-value="(val: number | undefined) => { getPolicyData()!.lon = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_fetch_interval') }}</div>
            <el-input-number
              :model-value="(getPolicyData()!.fetch_interval as number) || 600"
              :min="1" size="small" style="width: 140px"
              @update:model-value="(val: number | undefined) => { getPolicyData()!.fetch_interval = val }"
            />
            <span style="font-size:12px;color:#909399;margin-left:6px">seconds</span>
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_request_timeout') }}</div>
            <el-input-number
              :model-value="(getPolicyData()!.request_timeout as number) || 10"
              :min="1" size="small" style="width: 140px"
              @update:model-value="(val: number | undefined) => { getPolicyData()!.request_timeout = val }"
            />
            <span style="font-size:12px;color:#909399;margin-left:6px">seconds</span>
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_warmup_timeout') }}</div>
            <el-input-number
              :model-value="(getPolicyData()!.warmup_timeout as number) || 3"
              :min="1" size="small" style="width: 140px"
              @update:model-value="(val: number | undefined) => { getPolicyData()!.warmup_timeout = val }"
            />
            <span style="font-size:12px;color:#909399;margin-left:6px">seconds</span>
          </div>
        </template>
      </template>
      <el-empty v-else :image-size="48" :description="t('noData')" style="margin-top: 40px" />
    </div>
  </div>
</template>
```

- [ ] **Step 3: Create PolicyEditor scoped styles**

```css
<style scoped>
.policy-editor {
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
  display: flex; align-items: center; gap: 6px;
}
.editor-item:hover { background: #f0f2f5; }
.editor-item.selected { background: #ecf5ff; color: #409eff; font-weight: 600; }
.policy-dot {
  width: 8px; height: 8px; border-radius: 50%; background: #c0c4cc; flex-shrink: 0;
}
.policy-dot.on { background: #67c23a; }
.editor-right {
  flex: 1; overflow-y: auto; min-width: 0;
}
.detail-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; padding-bottom: 12px;
  border-bottom: 1px solid var(--el-border-color, #e4e7ed);
}
.detail-title { font-size: 15px; font-weight: 600; }
.detail-row {
  display: flex; align-items: center; margin-bottom: 16px;
}
.detail-label { font-size: 13px; color: #606266; min-width: 120px; }
.rules-section { margin-bottom: 16px; }
.rules-title {
  font-size: 13px; font-weight: 600; color: #606266; margin-bottom: 8px;
}
.rule-row {
  display: flex; align-items: center; gap: 4px; margin-bottom: 6px;
}
</style>
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/components/PolicyEditor.vue
git commit -m "feat: add PolicyEditor component with type-specific forms"
```

- [ ] **Step 2: Commit**

```bash
git add dashboard/src/components/PolicyEditor.vue
git commit -m "feat: add PolicyEditor component with type-specific forms"
```

---

### Task 5: Add batch tag add to PlaylistEditor

**Files:**
- Modify: `dashboard/src/components/PlaylistEditor.vue`

- [ ] **Step 1: Add batch add UI below existing tag table**

After the existing `<el-button size="small" :icon="Plus" ... @click="addTag">` (for single tag add), add:

```vue
<div class="batch-add" style="margin-top: 8px; padding-top: 8px; border-top: 1px dashed var(--el-border-color, #e4e7ed)">
  <div style="font-size: 12px; color: #909399; margin-bottom: 4px">Batch add tags</div>
  <div style="display: flex; gap: 8px; align-items: center">
    <el-select
      v-model="batchTags"
      multiple
      filterable
      allow-create
      default-first-option
      :placeholder="t('config_tags')"
      style="flex: 1"
    >
      <el-option v-for="t in tagPresets" :key="t" :label="t" :value="t" />
    </el-select>
    <el-input-number
      v-model="batchWeight"
      :min="0" :max="2" :step="0.1"
      :precision="1"
      style="width: 100px"
    />
    <el-button size="small" type="primary" @click="applyBatch">Add</el-button>
  </div>
</div>
```

- [ ] **Step 2: Add batch state and applyBatch function in script**

Add after the existing `const form = reactive(...)`:

```typescript
const batchTags = ref<string[]>([])
const batchWeight = ref(1.0)

function applyBatch() {
  for (const tag of batchTags.value) {
    const trimmed = tag.trim()
    if (!trimmed) continue
    // Skip if tag already exists
    if (form.tags.some(r => r.tag === trimmed)) continue
    form.tags.push({ key: Date.now() + Math.random(), tag: trimmed, weight: batchWeight.value })
  }
  batchTags.value = []
}
```

- [ ] **Step 3: Commit**

```bash
git add dashboard/src/components/PlaylistEditor.vue
git commit -m "feat: add batch tag add to PlaylistEditor"
```

---

### Task 6: Rework ConfigView.vue

**Files:**
- Modify: `dashboard/src/views/ConfigView.vue`

- [ ] **Step 1: Rewrite script section**

Replace the entire `<script setup>` block:

```typescript
<script setup lang="ts">
import { ref, provide, inject, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { Plus, Edit, Delete, InfoFilled } from '@element-plus/icons-vue'
import { useConfig, type PlaylistConfig, type AppConfig } from '@/composables/useConfig'
import PlaylistEditor from '@/components/PlaylistEditor.vue'
import SchedulingForm from '@/components/SchedulingForm.vue'
import PolicyEditor from '@/components/PolicyEditor.vue'
import TagEditor from '@/components/TagEditor.vue'
import type { SchedulingConfig } from '@/composables/useConfig'

const {
  config, loading, saveError, saving, isDirty,
  tagPresets, wePlaylists,
  fetchConfig, saveConfig, fetchTagPresets, scanPlaylists,
} = useConfig()

const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!

provide('tagPresets', tagPresets)
provide('wePlaylists', wePlaylists)
provide('config', config)

const activeTab = ref('playlists')
const showEditor = ref(false)
const editingPlaylist = ref<PlaylistConfig | null>(null)
let editingOriginalName: string | null = null
const editingScheduling = ref<SchedulingConfig>({
  startup_delay: 15,
  idle_threshold: 60,
  switch_cooldown: 1800,
  cycle_cooldown: 600,
  force_after: 14400,
  cpu_threshold: 85,
  cpu_sample_window: 10,
  pause_on_fullscreen: true,
})
const wallpaperEnginePath = ref('')

provide('editingScheduling', editingScheduling)

// -- Dirty-state guard on page close --
function onBeforeUnload(e: BeforeUnloadEvent) {
  if (isDirty.value) {
    e.preventDefault()
    e.returnValue = t('config_unsaved_changes')
    return t('config_unsaved_changes')
  }
}

onMounted(async () => {
  await Promise.all([fetchConfig(), fetchTagPresets(), scanPlaylists()])
  if (config.value) {
    wallpaperEnginePath.value = config.value.wallpaper_engine_path || ''
    editingScheduling.value = { ...config.value.scheduling }
  }
  window.addEventListener('beforeunload', onBeforeUnload)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
})

// -- Playlist CRUD (unchanged logic from original) --
function openNewPlaylist() {
  editingPlaylist.value = null
  showEditor.value = true
}

function openEditPlaylist(pl: PlaylistConfig) {
  editingOriginalName = pl.name
  editingPlaylist.value = { ...pl }
  showEditor.value = true
}

function deletePlaylist(index: number) {
  if (!config.value) return
  config.value.playlists.splice(index, 1)
}

async function handleRetry() {
  saveError.value = null
  await fetchConfig()
  if (config.value) {
    wallpaperEnginePath.value = config.value.wallpaper_engine_path || ''
    editingScheduling.value = { ...config.value.scheduling }
  }
}

function handlePlaylistSave(pl: PlaylistConfig) {
  if (!config.value) return
  const searchName = editingOriginalName ?? pl.name
  const idx = config.value.playlists.findIndex(p => p.name === searchName)
  if (idx >= 0) {
    config.value.playlists[idx] = pl
  } else {
    config.value.playlists.push(pl)
  }
  editingOriginalName = null
}

async function handleSave() {
  if (!config.value) return
  const data: AppConfig = {
    ...config.value,
    wallpaper_engine_path: wallpaperEnginePath.value,
    scheduling: { ...editingScheduling.value },
  }
  const result = await saveConfig(data)
  if (result.ok) {
    ElMessage.success(t('config_saved'))
  }
}

// -- Auto-detect WE path --
async function autoDetectWePath() {
  const detected = await (window as any).pywebview?.api?.we_path?.()
  if (detected) wallpaperEnginePath.value = detected
}
</script>
```

- [ ] **Step 2: Rewrite template**

Replace the entire `<template>` block:

```html
<template>
  <div class="panel">
    <div class="panel-header">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ t('config') }}</span>
    </div>
    <div class="panel-body config-body">
      <el-skeleton v-if="loading" :rows="6" animated />

      <div v-else-if="!config" class="config-error">
        <el-alert v-if="saveError" :title="saveError" type="error" show-icon />
        <el-empty v-else :image-size="48" :description="t('config_load_failed')" />
        <el-button style="margin-top: 12px; display: block; margin-left: auto; margin-right: auto;" type="primary" @click="handleRetry">{{ t('config_retry') }}</el-button>
      </div>

      <template v-else>
        <!-- WE Path bar -->
        <div class="we-bar">
          <span class="we-bar-label">{{ t('config_we_path') }}</span>
          <el-input v-model="wallpaperEnginePath" :placeholder="t('config_we_placeholder')" size="small" style="flex: 1" />
          <el-button size="small" @click="autoDetectWePath">{{ t('config_auto_detect') }}</el-button>
        </div>

        <!-- Tabs -->
        <el-tabs v-model="activeTab">
          <el-tab-pane :label="t('config_playlists')" name="playlists">
            <p class="tab-intro">{{ t('config_playlists_intro') }}</p>
            <div class="playlist-list">
              <div
                v-for="(pl, idx) in config.playlists" :key="pl.name"
                class="playlist-card"
              >
                <div class="pl-info">
                  <span class="pl-name">{{ pl.display || pl.name }}</span>
                  <span class="pl-display">{{ pl.display ? pl.name : '' }}</span>
                </div>
                <div class="pl-tags">
                  <el-tag
                    v-for="(w, t) in pl.tags" :key="t"
                    size="small" type="info"
                  >
                    {{ t }} {{ (w as number).toFixed(1) }}
                  </el-tag>
                </div>
                <div class="pl-actions">
                  <el-button size="small" :icon="Edit" circle @click="openEditPlaylist(pl)" />
                  <el-button size="small" :icon="Delete" circle type="danger" @click="deletePlaylist(idx)" />
                </div>
              </div>
              <el-button :icon="Plus" style="margin-top: 8px" @click="openNewPlaylist">
                {{ t('config_add_playlist') }}
              </el-button>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="t('config_policies')" name="policies" lazy>
            <p class="tab-intro">{{ t('config_policies_intro') }}</p>
            <PolicyEditor />
          </el-tab-pane>

          <el-tab-pane :label="t('config_tags_tab')" name="tags" lazy>
            <p class="tab-intro">{{ t('config_tags_intro') }}</p>
            <TagEditor />
          </el-tab-pane>

          <el-tab-pane :label="t('config_scheduling')" name="scheduling">
            <p class="tab-intro">{{ t('config_scheduling_intro') }}</p>
            <SchedulingForm />
          </el-tab-pane>
        </el-tabs>

        <!-- Save bar -->
        <div class="save-bar">
          <span v-if="isDirty" style="font-size: 12px; color: #e6a23c">● Unsaved changes</span>
          <el-alert v-if="saveError" :title="saveError" type="error" show-icon closable @close="saveError = null" />
          <el-button type="primary" :loading="saving" @click="handleSave">
            {{ t('config_save') }}
          </el-button>
        </div>
      </template>
    </div>

    <PlaylistEditor
      v-model="showEditor"
      :playlist="editingPlaylist"
      @save="handlePlaylistSave"
    />
  </div>
</template>
```

- [ ] **Step 3: Rewrite scoped styles**

Replace the entire `<style scoped>` block:

```css
<style scoped>
.config-body { padding: 16px; overflow-y: auto; }

/* WE path bar */
.we-bar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 6px; margin-bottom: 12px;
}
.we-bar-label { font-size: 13px; font-weight: 600; white-space: nowrap; }

/* Tab intro text */
.tab-intro {
  font-size: 12px; color: #909399; margin: 0 0 12px 0; line-height: 1.5;
}

/* Playlist cards (unchanged from original) */
.playlist-list { display: flex; flex-direction: column; gap: 8px; }
.playlist-card {
  display: flex; align-items: center; gap: 16px;
  padding: 12px; background: #f0f2f5;
  border-radius: 8px;
}
.pl-info { min-width: 140px; }
.pl-name { font-weight: 600; display: block; }
.pl-display { font-size: 12px; color: #909399; display: block; }
.pl-tags { flex: 1; display: flex; gap: 4px; flex-wrap: wrap; }
.pl-actions { display: flex; gap: 4px; }

/* Save bar */
.save-bar {
  margin-top: 16px; padding-top: 16px;
  border-top: 1px solid var(--el-border-color, #e4e7ed);
  display: flex; flex-direction: column; gap: 8px; align-items: flex-end;
}

/* Error state */
.config-error {
  padding: 24px; text-align: center;
}
</style>
```

- [ ] **Step 4: Commit**

```bash
git add dashboard/src/views/ConfigView.vue
git commit -m "feat: rework ConfigView with Policies, Tags tabs and dirty-state guard"
```

---

### Task 7: Type-check and build

**Files:** None (verification only)

- [ ] **Step 1: Run type check**

```bash
cd dashboard && npm run type-check
```

Expected: Exit code 0, no errors.

- [ ] **Step 2: Run build**

```bash
cd dashboard && npm run build
```

Expected: Exit code 0, SPA built to `dashboard/dist/`.

- [ ] **Step 3: Fix any type errors**

If type-check fails, fix the errors before proceeding. Common issues:
- Missing `import { computed }` in `useConfig.ts`
- Missing `onBeforeUnmount` import in `ConfigView.vue`
- `inject()` with no default value needs `!` assertion
- `ReturnType<typeof ...>` may need adjustment — simplify to explicit type if needed

- [ ] **Step 4: Commit if fixes were needed**

```bash
git add -A
git commit -m "fix: type-check and build fixes for config UI completion"
```

---

### Task 8: Manual verification

- [ ] **Step 1: Launch the app**

```bash
python main.py --no-tray
```

- [ ] **Step 2: Open dashboard and navigate to Config tab**

Open `http://localhost:<port>` in browser. Click "Config" tab.

- [ ] **Step 3: Verify WE path bar**

Check that the WE path bar is visible above tabs, with input field and "Auto-detect" button.

- [ ] **Step 4: Verify Playlists tab**

Check that intro text appears. Create a playlist using batch tag add (multi-select → set weight → Add). Verify tags appear.

- [ ] **Step 5: Verify Policies tab**

Click "Policies" tab. Select "Activity" in left list. Toggle enabled switch. Adjust weight_scale slider. Add/remove process_rules and title_rules.

- [ ] **Step 6: Verify all policy types**

Select "Time": verify auto switch, day_start/night_start inputs (disabled when auto on).
Select "Season": verify 4 peak day inputs.
Select "Weather": verify API key with show-password toggle, lat/lon inputs.

- [ ] **Step 7: Verify Tags tab**

Click "Tags" tab. Select `#dawn` in left list. Add fallback to `#day` with weight 0.7. Add fallback to `#chill` with weight 0.3. Delete a fallback.

- [ ] **Step 8: Verify Scheduling tab**

Click "Scheduling" tab. Verify all sliders and toggle work as before.

- [ ] **Step 9: Verify dirty-state guard**

Make a change (e.g. toggle a policy off). Do NOT save. Try to close the browser tab. Verify browser shows "unsaved changes" dialog.

- [ ] **Step 10: Verify save and round-trip**

Click "Save Configuration". Verify success toast. Reload page. Verify all changes persisted.

- [ ] **Step 11: Verify unknown policy survival**

If `scheduler_config.json` has a `mood` policy key, verify it survives a save round-trip (edit something, save, check file still has mood section).
