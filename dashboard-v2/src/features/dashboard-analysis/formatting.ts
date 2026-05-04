export function formatPercent(
  value: number | null | undefined,
  locale: string,
  maximumFractionDigits = 1,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }

  return new Intl.NumberFormat(locale, {
    maximumFractionDigits,
    minimumFractionDigits: maximumFractionDigits === 0 ? 0 : Math.min(1, maximumFractionDigits),
  }).format(value)
}

export function formatSeconds(
  value: number | null | undefined,
  locale: string,
  maximumFractionDigits = 0,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }

  return new Intl.NumberFormat(locale, {
    maximumFractionDigits,
  }).format(value)
}

export function formatWeight(
  value: number | null | undefined,
  locale: string,
  maximumFractionDigits = 3,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }

  return new Intl.NumberFormat(locale, {
    maximumFractionDigits,
    minimumFractionDigits: 0,
  }).format(value)
}

export function formatTimestamp(
  value: number | null | undefined,
  locale: string,
  options?: Intl.DateTimeFormatOptions,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '—'
  }

  return new Intl.DateTimeFormat(
    locale,
    options ?? {
      dateStyle: 'medium',
      timeStyle: 'medium',
    },
  ).format(new Date(value * 1000))
}

export function formatShortTime(value: number | null | undefined, locale: string): string {
  return formatTimestamp(value, locale, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}
