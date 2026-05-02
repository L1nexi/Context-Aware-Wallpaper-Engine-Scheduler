import type { VariantProps } from "class-variance-authority"
import { cva } from "class-variance-authority"

export const workbenchPanelVariants = cva("workbench-panel", {
  variants: {
    tone: {
      default: "",
      muted: "bg-surface-muted/92",
      accent: "border-primary/20 bg-primary/5",
      ghost: "border-transparent bg-transparent shadow-none backdrop-blur-0",
    },
    padding: {
      none: "",
      sm: "p-4",
      md: "p-5",
      lg: "p-6",
    },
  },
  defaultVariants: {
    tone: "default",
    padding: "md",
  },
})

export type WorkbenchPanelVariants = VariantProps<typeof workbenchPanelVariants>
