import type { EChartsOption, SeriesOption } from 'echarts'

import type { TickSnapshot } from '@/lib/dashboardAnalysis'

import { getCssColor } from './cssColors'
import { clamp, formatShortTime, formatWeight } from './formatting'
import { getPlaylistColor } from './playlistColors'
import { getTickPlaylistLabel } from './presenters'

type Translate = (key: string, params?: Record<string, string | number>) => string

interface TimelineLabels {
  activeTrack: string
  matchedTrack: string
  switch: string
  cycle: string
  similarity: string
  gap: string
}

interface TrackSegmentDatum {
  value: [number, number, number]
  itemStyle: {
    color: string
    decal?: {
      symbol: 'rect'
      dashArrayX: number[]
      dashArrayY: number[]
      rotation: number
      color: string
    }
  }
}

function buildTrackSegments(
  ticks: TickSnapshot[],
  rowIndex: number,
  type: 'active' | 'matched',
): TrackSegmentDatum[] {
  if (ticks.length === 0) {
    return []
  }

  const mutedColor = getCssColor('--muted', '#dbe3ee')
  const borderColor = getCssColor('--border', '#cdd7e2')

  const segments: TrackSegmentDatum[] = []
  let segmentStart = 0
  let previousKey = ''
  let previousColor = mutedColor
  let previousPaused = false

  const flushSegment = (endIndex: number): void => {
    segments.push({
      value: [segmentStart, endIndex, rowIndex],
      itemStyle: {
        color: previousColor,
        ...(previousPaused
          ? {
              decal: {
                symbol: 'rect',
                dashArrayX: [1, 0],
                dashArrayY: [3, 5],
                rotation: Math.PI / 4,
                color: borderColor,
              },
            }
          : {}),
      },
    })
  }

  ticks.forEach((tick, index) => {
    const playlist =
      type === 'active' ? tick.summary.activePlaylist : tick.summary.matchedPlaylist
    const paused = tick.summary.paused
    const key = paused ? '__paused__' : playlist ?? '__none__'
    const color = paused ? mutedColor : getPlaylistColor(playlist)

    if (index === 0) {
      previousKey = key
      previousColor = color
      previousPaused = paused
      return
    }

    if (key !== previousKey || paused !== previousPaused) {
      flushSegment(index - 1)
      segmentStart = index
      previousKey = key
      previousColor = color
      previousPaused = paused
    }
  })

  flushSegment(ticks.length - 1)
  return segments
}

function buildSimilaritySeries(ticks: TickSnapshot[]): [number, number][] {
  return ticks.map((tick, index) => [index, tick.summary.similarity])
}

function buildGapSeries(ticks: TickSnapshot[]): [number, number][] {
  return ticks.map((tick, index) => [index, tick.summary.similarityGap])
}

function getGapAxisMax(ticks: TickSnapshot[]): number {
  const maxGap = ticks.reduce((currentMax, tick) => {
    return Math.max(currentMax, tick.summary.similarityGap)
  }, 0)

  if (maxGap <= 0) {
    return 0.1
  }

  return Math.max(0.1, Number((maxGap * 1.2).toFixed(3)))
}

function buildEventSeries(
  ticks: TickSnapshot[],
  type: 'switch' | 'cycle',
  t: Translate,
): SeriesOption {
  const primary = getCssColor('--primary', '#4f8cff')
  const border = getCssColor('--background', '#ffffff')

  const data = ticks
    .map((tick, index) => ({ tick, index }))
    .filter(({ tick }) => tick.summary.actionKind === type)
    .map(({ tick, index }) => {
      const label = getTickPlaylistLabel(tick, 'active', t)
      return {
        value: [index, tick.summary.similarity],
        label: {
          show: type === 'switch',
          position: 'top' as const,
          distance: 10,
          color: primary,
          fontSize: 11,
          fontFamily: 'Geist Mono, monospace',
          formatter: `${t('dashboard_timeline_switch_marker')}: ${label}`,
        },
      }
    })

  return {
    name: type === 'switch' ? t('dashboard_timeline_switch_marker') : t('dashboard_timeline_cycle_marker'),
    type: 'scatter',
    xAxisIndex: 0,
    yAxisIndex: 0,
    z: 4,
    data,
    symbol: type === 'switch' ? 'diamond' : 'circle',
    symbolSize: type === 'switch' ? 10 : 6,
    itemStyle: {
      color: primary,
      borderColor: border,
      borderWidth: 1.5,
    },
    emphasis: {
      scale: false,
    },
    tooltip: {
      show: false,
    },
  }
}

export function resolveTimelineIndexFromPixel(
  pixelX: number,
  pixelY: number,
  ticks: TickSnapshot[],
  chart: {
    convertFromPixel: (
      finder: { gridIndex: number } | { xAxisIndex: number; yAxisIndex: number },
      value: [number, number],
    ) => number[] | number
    containPixel: (finder: { gridIndex: number }, value: [number, number]) => boolean
  },
): number | null {
  if (ticks.length === 0) {
    return null
  }

  const finder = chart.containPixel({ gridIndex: 0 }, [pixelX, pixelY])
    ? ({ xAxisIndex: 0, yAxisIndex: 0 } as const)
    : chart.containPixel({ gridIndex: 1 }, [pixelX, pixelY])
      ? ({ xAxisIndex: 1, yAxisIndex: 2 } as const)
      : null

  if (finder === null) {
    return null
  }

  const result = chart.convertFromPixel(finder, [pixelX, pixelY])
  const rawIndex = Array.isArray(result) ? result[0] ?? null : result
  if (rawIndex === null || Number.isNaN(rawIndex)) {
    return null
  }

  return clamp(Math.round(rawIndex), 0, ticks.length - 1)
}

export function buildTimelineOption(
  ticks: TickSnapshot[],
  locale: string,
  labels: TimelineLabels,
  t: Translate,
): EChartsOption {
  const similarityColor = getCssColor('--primary', '#4f8cff')
  const gapColor = getCssColor('--chart-2', '#15b8a6')
  const textColor = getCssColor('--muted-foreground', '#67768d')
  const splitLineColor = getCssColor('--border', '#dce3ec')
  const panelColor = getCssColor('--surface', '#ffffff')

  const lastIndex = Math.max(ticks.length - 1, 0)
  const gapAxisMax = getGapAxisMax(ticks)
  const trackRows = [labels.activeTrack, labels.matchedTrack]

  return {
    animation: false,
    grid: [
      {
        left: 78,
        right: 78,
        top: 24,
        height: 206,
      },
      {
        left: 78,
        right: 78,
        top: 258,
        height: 86,
      },
    ],
    xAxis: [
      {
        type: 'value',
        min: 0,
        max: lastIndex,
        gridIndex: 0,
        axisLabel: { show: false },
        axisTick: { show: false },
        axisLine: { show: false },
        splitLine: { show: false },
      },
      {
        type: 'value',
        min: 0,
        max: lastIndex,
        gridIndex: 1,
        axisLabel: {
          color: textColor,
          formatter: (value: number) => formatShortTime(ticks[Math.round(value)]?.summary.ts, locale),
          hideOverlap: true,
        },
        axisTick: { show: false },
        axisLine: {
          lineStyle: {
            color: splitLineColor,
          },
        },
        splitLine: { show: false },
      },
    ],
    yAxis: [
      {
        type: 'value',
        min: 0,
        max: 1,
        gridIndex: 0,
        axisLabel: {
          color: textColor,
          formatter: (value: number) => formatWeight(value, locale),
        },
        splitLine: {
          lineStyle: {
            color: splitLineColor,
            opacity: 0.4,
          },
        },
      },
      {
        type: 'value',
        min: 0,
        max: gapAxisMax,
        gridIndex: 0,
        position: 'right',
        axisLabel: {
          color: textColor,
          formatter: (value: number) => formatWeight(value, locale),
        },
        axisLine: {
          show: true,
          lineStyle: {
            color: splitLineColor,
          },
        },
        splitLine: {
          lineStyle: {
            color: splitLineColor,
            opacity: 0.32,
          },
        },
      },
      {
        type: 'category',
        data: trackRows,
        gridIndex: 1,
        axisTick: { show: false },
        axisLine: { show: false },
        axisLabel: {
          color: textColor,
          fontSize: 11,
          fontFamily: 'Geist Mono, monospace',
        },
        splitLine: { show: false },
      },
    ],
    axisPointer: {
      link: [{ xAxisIndex: [0, 1, 2] }],
      lineStyle: {
        color: similarityColor,
        opacity: 0.2,
      },
      label: {
        show: false,
      },
    },
    tooltip: {
      trigger: 'axis',
      triggerOn: 'none',
      alwaysShowContent: true,
      axisPointer: {
        type: 'line',
      },
      backgroundColor: panelColor,
      borderColor: splitLineColor,
      textStyle: {
        color: textColor,
      },
      formatter: (params: unknown) => {
        const axisItems = Array.isArray(params) ? params : []
        const firstItem = axisItems[0] as { axisValue?: number } | undefined
        const index = clamp(Math.round(firstItem?.axisValue ?? 0), 0, ticks.length - 1)
        const tick = ticks[index]
        if (!tick) {
          return ''
        }

        return `
          <div style="min-width: 220px;">
            <div style="font-family: Geist Mono, monospace; font-size: 11px; letter-spacing: 0.18em; text-transform: uppercase; color: ${textColor};">
              ${formatShortTime(tick.summary.ts, locale)}
            </div>
            <div style="margin-top: 8px; font-weight: 600; color: ${similarityColor};">
              ${labels.similarity}: ${formatWeight(tick.summary.similarity, locale)}
            </div>
            <div style="margin-top: 4px;">
              ${labels.gap}: ${formatWeight(tick.summary.similarityGap, locale)}
            </div>
            <div style="margin-top: 8px;">
              ${labels.activeTrack}: ${getTickPlaylistLabel(tick, 'active', t)}
            </div>
            <div style="margin-top: 4px;">
              ${labels.matchedTrack}: ${getTickPlaylistLabel(tick, 'matched', t)}
            </div>
          </div>
        `
      },
    },
    series: [
      {
        id: 'similarity',
        name: labels.similarity,
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 0,
        z: 3,
        showSymbol: false,
        smooth: 0.2,
        lineStyle: {
          color: similarityColor,
          width: 2.5,
        },
        areaStyle: {
          color: 'transparent',
        },
        emphasis: {
          disabled: true,
        },
        data: buildSimilaritySeries(ticks),
      },
      {
        id: 'gap',
        name: labels.gap,
        type: 'line',
        xAxisIndex: 0,
        yAxisIndex: 1,
        z: 2,
        showSymbol: false,
        smooth: 0.15,
        lineStyle: {
          color: gapColor,
          width: 1.5,
        },
        areaStyle: {
          color: gapColor,
          opacity: 0.22,
        },
        emphasis: {
          disabled: true,
        },
        data: buildGapSeries(ticks),
      },
      {
        ...buildEventSeries(ticks, 'switch', t),
        id: 'event-switch',
      },
      {
        ...buildEventSeries(ticks, 'cycle', t),
        id: 'event-cycle',
      },
      {
        id: 'track-active',
        name: labels.activeTrack,
        type: 'custom',
        xAxisIndex: 1,
        yAxisIndex: 2,
        z: 1,
        renderItem(params, api) {
          const start = api.value(0) as number
          const end = api.value(1) as number
          const rowIndex = api.value(2) as number
          const [startX = 0, startY = 0] = (api.coord?.([start - 0.45, rowIndex]) ??
            []) as number[]
          const [endX = startX] = (api.coord?.([end + 0.45, rowIndex]) ?? []) as number[]
          const [, rawRowHeight = 0] = (api.size?.([0, 1]) ?? []) as number[]
          const rowHeight = rawRowHeight * 0.54

          return {
            type: 'rect',
            shape: {
              x: startX,
              y: startY - rowHeight / 2,
              width: Math.max(endX - startX, 2),
              height: rowHeight,
              r: 6,
            },
            style: api.style(),
          }
        },
        data: buildTrackSegments(ticks, 0, 'active'),
        tooltip: {
          show: false,
        },
      },
      {
        id: 'track-matched',
        name: labels.matchedTrack,
        type: 'custom',
        xAxisIndex: 1,
        yAxisIndex: 2,
        z: 1,
        renderItem(params, api) {
          const start = api.value(0) as number
          const end = api.value(1) as number
          const rowIndex = api.value(2) as number
          const [startX = 0, startY = 0] = (api.coord?.([start - 0.45, rowIndex]) ??
            []) as number[]
          const [endX = startX] = (api.coord?.([end + 0.45, rowIndex]) ?? []) as number[]
          const [, rawRowHeight = 0] = (api.size?.([0, 1]) ?? []) as number[]
          const rowHeight = rawRowHeight * 0.54

          return {
            type: 'rect',
            shape: {
              x: startX,
              y: startY - rowHeight / 2,
              width: Math.max(endX - startX, 2),
              height: rowHeight,
              r: 6,
            },
            style: api.style(),
          }
        },
        data: buildTrackSegments(ticks, 1, 'matched'),
        tooltip: {
          show: false,
        },
      },
    ],
  }
}
