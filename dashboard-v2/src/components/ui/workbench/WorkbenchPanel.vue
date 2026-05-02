<script setup lang="ts">
import type { PrimitiveProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import type { WorkbenchPanelVariants } from "./workbench"
import { Primitive } from "reka-ui"
import { cn } from "@/lib/utils"
import { workbenchPanelVariants } from "./workbench"

interface Props extends PrimitiveProps {
  tone?: WorkbenchPanelVariants["tone"]
  padding?: WorkbenchPanelVariants["padding"]
  class?: HTMLAttributes["class"]
}

const props = withDefaults(defineProps<Props>(), {
  as: "section",
  tone: "default",
  padding: "md",
})
</script>

<template>
  <Primitive
    data-slot="workbench-panel"
    :data-tone="tone"
    :as="as"
    :as-child="asChild"
    :class="cn(workbenchPanelVariants({ tone, padding }), props.class)"
  >
    <slot />
  </Primitive>
</template>
