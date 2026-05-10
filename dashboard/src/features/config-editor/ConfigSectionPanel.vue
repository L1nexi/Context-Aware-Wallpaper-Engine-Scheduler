<script setup lang="ts">
import { AlertCircle, RotateCcw } from 'lucide-vue-next'

import { Button } from '@/components/ui/button'
import { WorkbenchPanel } from '@/components/ui/workbench'

withDefaults(
  defineProps<{
    eyebrow: string
    title: string
    description: string
    restoreLabel: string
    errors?: string[]
    disabled?: boolean
  }>(),
  {
    errors: () => [],
    disabled: false,
  },
)

const emit = defineEmits<{
  (event: 'restore'): void
}>()
</script>

<template>
  <WorkbenchPanel padding="lg" class="flex flex-col gap-6">
    <div class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
      <div class="max-w-3xl">
        <p class="chrome-kicker">{{ eyebrow }}</p>
        <h2 class="mt-2 text-xl font-semibold tracking-tight">
          {{ title }}
        </h2>
        <p class="mt-2 text-sm leading-6 text-muted-foreground">
          {{ description }}
        </p>
      </div>

      <Button
        variant="outline"
        size="sm"
        :disabled="disabled"
        class="shrink-0"
        @click="emit('restore')"
      >
        <RotateCcw class="size-4" aria-hidden="true" />
        {{ restoreLabel }}
      </Button>
    </div>

    <div
      v-if="errors.length > 0"
      class="rounded-lg border border-destructive/20 bg-destructive/8 px-4 py-3"
    >
      <div class="flex items-start gap-3">
        <AlertCircle class="mt-0.5 size-4 shrink-0 text-destructive" aria-hidden="true" />
        <div class="space-y-1">
          <p class="text-sm font-medium text-destructive">
            <slot name="error-title" />
          </p>
          <p v-for="error in errors" :key="error" class="text-sm leading-5 text-destructive/90">
            {{ error }}
          </p>
        </div>
      </div>
    </div>

    <slot />
  </WorkbenchPanel>
</template>
