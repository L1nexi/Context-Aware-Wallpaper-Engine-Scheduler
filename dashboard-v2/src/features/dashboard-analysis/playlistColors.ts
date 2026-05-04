import { getCssColor } from './cssColors'

const PLAYLIST_COLOR_VARIABLES = [
  '--chart-1',
  '--chart-2',
  '--chart-3',
  '--chart-4',
  '--chart-5',
  '--primary',
  '--ring',
  '--destructive',
]

const colorCache = new Map<string, string>()

function hashPlaylistKey(value: string): number {
  let hash = 0

  for (let index = 0; index < value.length; index += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(index)
    hash |= 0
  }

  return Math.abs(hash)
}

export function getPlaylistColor(playlist: string | null | undefined): string {
  const normalized = playlist?.trim()
  if (!normalized) {
    return getCssColor('--muted', '#dbe3ee')
  }

  const cached = colorCache.get(normalized)
  if (cached) {
    return cached
  }

  const paletteIndex = hashPlaylistKey(normalized) % PLAYLIST_COLOR_VARIABLES.length
  const fallbackPalette = [
    '#4f8cff',
    '#15b8a6',
    '#59b67a',
    '#dfab39',
    '#ed7a52',
    '#5d8cff',
    '#58a0ff',
    '#d86969',
  ]
  const variableName = PLAYLIST_COLOR_VARIABLES[paletteIndex] ?? '--chart-1'
  const fallbackColor = fallbackPalette[paletteIndex] ?? '#4f8cff'
  const color = getCssColor(
    variableName,
    fallbackColor,
  )
  colorCache.set(normalized, color)
  return color
}
