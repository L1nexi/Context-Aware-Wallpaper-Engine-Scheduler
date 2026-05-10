<script setup lang="ts">
import { computed } from 'vue'

import { Label } from '@/components/ui/label'

const props = withDefaults(
  defineProps<{
    id?: string
    pathKey: string
    label: string
    description?: string
    errors?: string[]
  }>(),
  {
    description: '',
    errors: () => [],
  },
)

const inputId = computed(
  () => props.id ?? `config-${props.pathKey.replace(/[^a-zA-Z0-9_-]/g, '-')}`,
)
const hasErrors = computed(() => props.errors.length > 0)
</script>

<template>
  <div class="grid gap-3 py-4 md:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] md:gap-6">
    <div class="space-y-1">
      <Label :for="inputId" class="text-sm font-medium">
        {{ label }}
      </Label>
      <p v-if="description" class="text-sm leading-5 text-muted-foreground">
        {{ description }}
      </p>
    </div>

    <div class="min-w-0 space-y-2">
      <slot :id="inputId" :invalid="hasErrors" />

      <div v-if="hasErrors" class="space-y-1">
        <p v-for="error in errors" :key="error" class="text-sm leading-5 text-destructive">
          {{ error }}
        </p>
      </div>
    </div>
  </div>
</template>
