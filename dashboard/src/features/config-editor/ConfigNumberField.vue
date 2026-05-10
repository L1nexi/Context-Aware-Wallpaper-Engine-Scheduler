<script setup lang="ts">
import { computed } from 'vue'

import { Input } from '@/components/ui/input'
import { useI18n } from '@/composables/useI18n'
import { useConfigDocumentStore } from '@/stores/configDocument'

import ConfigFieldRow from './ConfigFieldRow.vue'

type UnitKind = 'seconds' | 'percent' | 'count'

const props = withDefaults(
  defineProps<{
    pathKey: string
    label: string
    description?: string
    modelValue: number
    min?: number
    max?: number
    integer?: boolean
    unit?: UnitKind
    disabled?: boolean
  }>(),
  {
    description: '',
    integer: false,
    unit: 'seconds',
    disabled: false,
  },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: number): void
}>()

const { t } = useI18n()
const configStore = useConfigDocumentStore()

const errors = computed(() => configStore.fieldMessages(props.pathKey))
const displayValue = computed(
  () => configStore.fieldBuffers[props.pathKey] ?? String(props.modelValue),
)

function formatNumber(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1).replace(/\.0$/, '')
}

function formatDuration(value: number): string {
  if (!Number.isFinite(value)) {
    return ''
  }

  if (Math.abs(value) < 60) {
    return `${formatNumber(value)} s`
  }

  if (Math.abs(value) < 3600) {
    return `${formatNumber(value)} s · ${formatNumber(value / 60)} min`
  }

  return `${formatNumber(value)} s · ${formatNumber(value / 3600)} h`
}

const unitHint = computed(() => {
  if (props.unit === 'percent') {
    return `${formatNumber(props.modelValue)}%`
  }

  if (props.unit === 'count') {
    return String(props.modelValue)
  }

  return formatDuration(props.modelValue)
})

function validate(raw: string): number | string {
  const value = raw.trim()

  if (value.length === 0) {
    return t('config_validation_required')
  }

  const numberPattern = props.integer ? /^-?\d+$/ : /^-?\d+(?:\.\d+)?$/
  if (!numberPattern.test(value)) {
    return props.integer ? t('config_validation_integer') : t('config_validation_number')
  }

  const parsed = Number(value)
  if (!Number.isFinite(parsed)) {
    return t('config_validation_number')
  }

  if (props.min !== undefined && parsed < props.min) {
    return t('config_validation_min', { min: props.min })
  }

  if (props.max !== undefined && parsed > props.max) {
    return t('config_validation_max', { max: props.max })
  }

  return parsed
}

function handleInput(value: string | number): void {
  const raw = String(value)
  const parsed = validate(raw)

  if (typeof parsed === 'string') {
    configStore.setFieldBuffer(props.pathKey, raw, parsed)
    return
  }

  configStore.clearFieldBuffer(props.pathKey)
  emit('update:modelValue', parsed)
}
</script>

<template>
  <ConfigFieldRow :path-key="pathKey" :label="label" :description="description" :errors="errors">
    <template #default="{ id, invalid }">
      <div class="flex flex-col gap-2 sm:max-w-sm">
        <div class="flex items-center gap-3">
          <Input
            :id="id"
            :model-value="displayValue"
            :disabled="disabled"
            :aria-invalid="invalid"
            inputmode="decimal"
            class="font-mono"
            @update:model-value="handleInput"
          />
          <span class="shrink-0 text-sm text-muted-foreground data-mono">
            {{ unitHint }}
          </span>
        </div>
      </div>
    </template>
  </ConfigFieldRow>
</template>
