import { computed, ref, shallowRef, watch } from "vue"
import type { Ref } from "vue"

import type { PlaylistScanResult } from "@/api/profile"
import { scanPlaylists } from "@/api/profile"

export type ScanStatus = "idle" | "loading" | "success" | "empty" | "error"

export function usePlaylistScan(path: Ref<string>) {
  const status = ref<ScanStatus>("idle")
  const error = shallowRef<unknown>(null)
  const scannedPath = ref("")
  const playlists = ref<PlaylistScanResult["playlists"]>([])
  let latestRequest = 0
  let requestedPath = ""

  const usablePlaylists = computed(() =>
    status.value === "success" && scannedPath.value === path.value
      ? playlists.value.filter((playlist) => playlist.item_count > 0)
      : [],
  )
  const ready = computed(() => usablePlaylists.value.length > 0)

  watch(path, (value) => {
    const normalized = value.trim()
    if (normalized === scannedPath.value) return
    if (status.value === "loading" && normalized === requestedPath) return
    latestRequest += 1
    status.value = "idle"
    error.value = null
    scannedPath.value = ""
    playlists.value = []
  })

  async function scan(): Promise<void> {
    const normalized = path.value.trim()
    const requestId = ++latestRequest
    requestedPath = normalized
    status.value = "loading"
    error.value = null
    try {
      const result = await scanPlaylists(normalized)
      if (requestId !== latestRequest || path.value.trim() !== normalized) return
      scannedPath.value = result.wallpaper_engine_path
      path.value = result.wallpaper_engine_path
      playlists.value = result.playlists
      status.value = result.playlists.some((playlist) => playlist.item_count > 0) ? "success" : "empty"
    } catch (failure) {
      if (requestId !== latestRequest || path.value.trim() !== normalized) return
      playlists.value = []
      scannedPath.value = ""
      status.value = "error"
      error.value = failure
    }
  }

  return { status, error, playlists, usablePlaylists, ready, scan }
}
