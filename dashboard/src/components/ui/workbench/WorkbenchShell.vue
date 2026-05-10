<script setup lang="ts">
import type { PrimitiveProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { Primitive } from "reka-ui"
import { cn } from "@/lib/utils"

interface Props extends PrimitiveProps {
  sidebar?: "full" | "rail"
  class?: HTMLAttributes["class"]
}

const props = withDefaults(defineProps<Props>(), {
  as: "div",
  sidebar: "full",
})
</script>

<template>
  <Primitive
    data-slot="workbench-shell"
    :data-sidebar="sidebar"
    :as="as"
    :as-child="asChild"
    :class="cn('workbench-shell', props.class)"
  >
    <slot />
  </Primitive>
</template>
