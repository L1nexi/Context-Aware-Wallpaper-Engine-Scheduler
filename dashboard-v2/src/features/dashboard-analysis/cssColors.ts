const colorCache = new Map<string, string>()

let probeElement: HTMLSpanElement | null = null

function getProbeElement(): HTMLSpanElement | null {
  if (typeof window === 'undefined') {
    return null
  }

  if (probeElement && probeElement.isConnected) {
    return probeElement
  }

  const probe = document.createElement('span')
  probe.setAttribute('aria-hidden', 'true')
  probe.style.position = 'absolute'
  probe.style.width = '0'
  probe.style.height = '0'
  probe.style.overflow = 'hidden'
  probe.style.opacity = '0'
  probe.style.pointerEvents = 'none'

  const parent = document.body ?? document.documentElement
  parent.appendChild(probe)
  probeElement = probe
  return probeElement
}

function resolveCssColorValue(value: string, fallback: string): string {
  if (typeof window === 'undefined') {
    return fallback
  }

  const normalized = value.trim()
  if (!normalized) {
    return fallback
  }

  const cached = colorCache.get(normalized)
  if (cached) {
    return cached
  }

  const probe = getProbeElement()
  if (!probe) {
    return fallback
  }

  probe.style.color = fallback
  probe.style.color = normalized

  const resolved = getComputedStyle(probe).color || fallback
  colorCache.set(normalized, resolved)
  return resolved
}

export function getCssColor(variableName: string, fallback: string): string {
  if (typeof window === 'undefined') {
    return fallback
  }

  const rawValue = getComputedStyle(document.documentElement)
    .getPropertyValue(variableName)
    .trim()

  return resolveCssColorValue(rawValue, fallback)
}
