<script setup lang="ts">
import type { PrimitiveProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { Primitive } from "reka-ui"
import { cn } from "@/lib/utils"

interface Props extends PrimitiveProps {
  class?: HTMLAttributes["class"]
}

const props = withDefaults(defineProps<Props>(), {
  as: "aside",
})
</script>

<template>
  <Primitive
    data-slot="workbench-sidebar"
    :as="as"
    :as-child="asChild"
    :class="cn('workbench-sidebar', props.class)"
  >
    <slot />
  </Primitive>
</template>
