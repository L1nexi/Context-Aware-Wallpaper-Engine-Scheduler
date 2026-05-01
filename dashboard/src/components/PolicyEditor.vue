<script setup lang="ts">
import { ref, computed, inject, watch, reactive, type Ref } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import type { AppConfig } from '@/composables/useConfig'

const config = inject<Ref<AppConfig | null>>('config')!
const t = inject<(key: string, params?: Record<string, string | number>) => string>('t')!
const tagPresets = inject<Ref<string[]>>('tagPresets')!

const KNOWN_POLICIES = ['activity', 'time', 'season', 'weather'] as const
type PolicyName = (typeof KNOWN_POLICIES)[number]

const selectedPolicy = ref<PolicyName | null>(null)

const policyList = computed(() => {
  if (!config.value) return []
  const policies = config.value.policies || {}
  return KNOWN_POLICIES.filter(p => p in policies)
})

const policyData = computed<Record<string, unknown>>(() => {
  if (!config.value || !selectedPolicy.value) return {}
  return (config.value.policies as Record<string, Record<string, unknown>>)[selectedPolicy.value] ?? {}
})

function isEnabled(policy?: string): boolean {
  const name = policy ?? selectedPolicy.value
  if (!name || !config.value) return true
  const d = (config.value.policies as Record<string, Record<string, unknown>>)[name]
  if (!d) return true
  return d.enabled !== false
}

function toggleEnabled() {
  if (!selectedPolicy.value) return
  policyData.value.enabled = !isEnabled()
}

function weightScale(): number {
  if (policyData.value.weight_scale == null) return 1.0
  return policyData.value.weight_scale as number
}

interface RuleRow { input: string; tag: string }

const processRules = reactive<RuleRow[]>([])
const titleRules = reactive<RuleRow[]>([])

function loadRules(data: Record<string, unknown>) {
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
  if (!selectedPolicy.value) return
  const rows = type === 'process_rules' ? processRules : titleRules
  const obj: Record<string, string> = {}
  for (const r of rows) {
    if (r.input.trim() && r.tag.trim()) obj[r.input.trim()] = r.tag.trim()
  }
  policyData.value[type] = obj
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

watch(selectedPolicy, (name) => {
  if (name) loadRules(policyData.value)
})
</script>

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
      <template v-if="selectedPolicy && policyData">
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
            @update:model-value="(val: number | undefined) => { policyData.weight_scale = val ?? 1.0 }"
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
              :model-value="(policyData.smoothing_window as number) || 60"
              :min="1" size="small" style="width: 160px"
              @update:model-value="(val: number | undefined) => { policyData.smoothing_window = val }"
            />
            <span style="font-size: 12px; color: #909399; margin-left: 6px">seconds</span>
          </div>
        </template>

        <!-- Time -->
        <template v-if="selectedPolicy === 'time'">
          <div class="rules-section">
            <div class="rules-title">{{ t('time_auto') }}</div>
            <el-switch
              :model-value="policyData.auto !== false" size="small"
              @change="(val: boolean) => { policyData.auto = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('time_day_start') }}</div>
            <el-input-number
              :model-value="(policyData.day_start_hour as number) ?? 8"
              :min="0" :max="24" :disabled="policyData.auto !== false" size="small" style="width: 120px"
              @update:model-value="(val: number | undefined) => { policyData.day_start_hour = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('time_night_start') }}</div>
            <el-input-number
              :model-value="(policyData.night_start_hour as number) ?? 20"
              :min="0" :max="24" :disabled="policyData.auto !== false" size="small" style="width: 120px"
              @update:model-value="(val: number | undefined) => { policyData.night_start_hour = val }"
            />
          </div>
        </template>

        <!-- Season -->
        <template v-if="selectedPolicy === 'season'">
          <div v-for="s in ['spring', 'summer', 'autumn', 'winter']" :key="s" class="rules-section">
            <div class="rules-title">{{ t('season_' + s + '_peak') }}</div>
            <el-input-number
              :model-value="(policyData[s + '_peak'] as number) || 80"
              :min="1" :max="365" size="small" style="width: 140px"
              @update:model-value="(val: number | undefined) => { policyData[s + '_peak'] = val }"
            />
            <span style="font-size:12px;color:#909399;margin-left:6px">day of year</span>
          </div>
        </template>

        <!-- Weather -->
        <template v-if="selectedPolicy === 'weather'">
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_api_key') }}</div>
            <el-input
              :model-value="(policyData.api_key as string) || ''"
              type="password" show-password size="small" style="width: 280px"
              @update:model-value="(val: string) => { policyData.api_key = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_lat') }}</div>
            <el-input-number
              :model-value="(policyData.lat as number) || 0"
              :min="-90" :max="90" :precision="4" size="small" style="width: 180px"
              @update:model-value="(val: number | undefined) => { policyData.lat = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_lon') }}</div>
            <el-input-number
              :model-value="(policyData.lon as number) || 0"
              :min="-180" :max="180" :precision="4" size="small" style="width: 180px"
              @update:model-value="(val: number | undefined) => { policyData.lon = val }"
            />
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_fetch_interval') }}</div>
            <el-input-number
              :model-value="(policyData.fetch_interval as number) || 600"
              :min="1" size="small" style="width: 140px"
              @update:model-value="(val: number | undefined) => { policyData.fetch_interval = val }"
            />
            <span style="font-size:12px;color:#909399;margin-left:6px">seconds</span>
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_request_timeout') }}</div>
            <el-input-number
              :model-value="(policyData.request_timeout as number) || 10"
              :min="1" size="small" style="width: 140px"
              @update:model-value="(val: number | undefined) => { policyData.request_timeout = val }"
            />
            <span style="font-size:12px;color:#909399;margin-left:6px">seconds</span>
          </div>
          <div class="rules-section">
            <div class="rules-title">{{ t('weather_warmup_timeout') }}</div>
            <el-input-number
              :model-value="(policyData.warmup_timeout as number) || 3"
              :min="1" size="small" style="width: 140px"
              @update:model-value="(val: number | undefined) => { policyData.warmup_timeout = val }"
            />
            <span style="font-size:12px;color:#909399;margin-left:6px">seconds</span>
          </div>
        </template>
      </template>
      <el-empty v-else :image-size="48" :description="t('noData')" style="margin-top: 40px" />
    </div>
  </div>
</template>

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
