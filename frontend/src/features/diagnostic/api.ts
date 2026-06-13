import type { DiagnosticWindowResponse } from './types'

export const DIAGNOSTIC_WINDOW_COUNT = 900
export const DIAGNOSTIC_POLL_INTERVAL_MS = 1000

function resolveDiagnosticApiUrl(path: string): string {
  const baseUrl = import.meta.env.VITE_DASHBOARD_API_BASE_URL?.trim()
  if (!baseUrl) {
    return path
  }

  const normalizedBaseUrl = baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
  return new URL(path, normalizedBaseUrl).toString()
}

export async function fetchDiagnosticWindow(
  signal?: AbortSignal,
): Promise<DiagnosticWindowResponse> {
  const response = await fetch(
    resolveDiagnosticApiUrl(`/api/analysis/window?count=${DIAGNOSTIC_WINDOW_COUNT}`),
    {
      headers: {
        Accept: 'application/json',
      },
      signal,
    },
  )

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`)
  }

  return (await response.json()) as DiagnosticWindowResponse
}
