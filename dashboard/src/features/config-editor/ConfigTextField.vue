<script setup lang="ts">
import { computed } from 'vue'

import { Input } from '@/components/ui/input'
import { useConfigDocumentStore } from '@/stores/configDocument'

import ConfigFieldRow from './ConfigFieldRow.vue'

const props = withDefaults(
  defineProps<{
    pathKey: string
    label: string
    description?: string
    modelValue: string
    placeholder?: string
    disabled?: boolean
  }>(),
  {
    description: '',
    placeholder: '',
    disabled: false,
  },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: string): void
}>()

const configStore = useConfigDocumentStore()
const errors = computed(() => configStore.fieldMessages(props.pathKey))
</script>

<template>
  <ConfigFieldRow :path-key="pathKey" :label="label" :description="description" :errors="errors">
    <template #default="{ id, invalid }">
      <div class="flex flex-col gap-2 sm:flex-row">
        <Input
          :id="id"
          :model-value="modelValue"
          :placeholder="placeholder"
          :disabled="disabled"
          :aria-invalid="invalid"
          class="min-w-0 flex-1 font-mono"
          @update:model-value="emit('update:modelValue', String($event))"
        />
        <slot name="actions" />
      </div>
    </template>
  </ConfigFieldRow>
</template>
