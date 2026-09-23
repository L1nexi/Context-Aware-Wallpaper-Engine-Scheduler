import { useColorMode } from "@vueuse/core"

export const themeMode = useColorMode({
  storageKey: "wescheduler-theme",
  emitAuto: true,
})
