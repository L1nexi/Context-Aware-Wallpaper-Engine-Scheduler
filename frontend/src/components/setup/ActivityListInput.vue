<script setup lang="ts">
import { PlusIcon, XIcon } from "@lucide/vue"
import { ref } from "vue"

import { Badge } from "@/components/ui/badge"
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupInput,
} from "@/components/ui/input-group"

const props = defineProps<{
  id: string
  placeholder: string
  addLabel: string
  removeLabel: string
  emptyLabel: string
}>()

const values = defineModel<string[]>({ required: true })
const input = ref("")

function addValue(): void {
  const value = input.value.trim()
  if (!value) return
  if (!values.value.some((existing) => existing.toLocaleLowerCase() === value.toLocaleLowerCase())) {
    values.value = [...values.value, value]
  }
  input.value = ""
}

function removeValue(value: string): void {
  values.value = values.value.filter((existing) => existing !== value)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <InputGroup>
      <InputGroupInput
        :id="props.id"
        v-model="input"
        :placeholder="props.placeholder"
        @keydown.enter.prevent="addValue"
      />
      <InputGroupAddon align="inline-end">
        <InputGroupButton :aria-label="props.addLabel" @click="addValue">
          <PlusIcon />
          <span>{{ props.addLabel }}</span>
        </InputGroupButton>
      </InputGroupAddon>
    </InputGroup>

    <div v-if="values.length" class="flex flex-wrap gap-2">
      <Badge
        v-for="value in values"
        :key="value"
        as="button"
        type="button"
        variant="secondary"
        :aria-label="`${props.removeLabel}: ${value}`"
        @click="removeValue(value)"
      >
        {{ value }}
        <XIcon data-icon="inline-end" />
      </Badge>
    </div>
    <p v-else class="text-sm text-muted-foreground">{{ props.emptyLabel }}</p>
  </div>
</template>
