<script setup lang="ts">
import type { PrimitiveProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { Primitive } from "reka-ui"
import { cn } from "@/lib/utils"

interface Props extends PrimitiveProps {
  class?: HTMLAttributes["class"]
}

const props = withDefaults(defineProps<Props>(), {
  as: "main",
})
</script>

<template>
  <Primitive
    data-slot="workbench-main"
    :as="as"
    :as-child="asChild"
    :class="cn('workbench-main', props.class)"
  >
    <slot />
  </Primitive>
</template>
