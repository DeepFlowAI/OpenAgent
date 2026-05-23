'use client'

import { useMemo } from 'react'

import type {
  ReportGranularity,
  ReportTrendBucket,
} from '@/models/conversation-report'
import { cn } from '@/utils/classnames'

import {
  METRIC_COLOR,
  METRIC_LABEL,
  type RateMetric,
  type VolumeMetric,
} from '../_constants'

const CHART_HEIGHT = 220
const BAR_WIDTH = 10
const BAR_GAP = 3

type Props = {
  buckets: ReportTrendBucket[]
  granularity: ReportGranularity
  selectedVolumes: VolumeMetric[]
  selectedRates: RateMetric[]
  isLoading: boolean
}

function formatTick(iso: string, granularity: ReportGranularity): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  const mm = pad(d.getMonth() + 1)
  const dd = pad(d.getDate())
  const hh = pad(d.getHours())
  const mi = pad(d.getMinutes())
  switch (granularity) {
    case 'half_hour':
    case 'hour':
      return `${hh}:${mi}`
    case 'day':
      return `${mm}-${dd}`
    case 'month':
      return `${d.getFullYear()}-${mm}`
  }
}

function niceMax(value: number): number {
  if (value <= 0) return 10
  const power = Math.pow(10, Math.floor(Math.log10(value)))
  const norm = value / power
  let mult = 1
  if (norm > 5) mult = 10
  else if (norm > 2) mult = 5
  else if (norm > 1) mult = 2
  return mult * power
}

export function TrendChart({
  buckets,
  granularity,
  selectedVolumes,
  selectedRates,
  isLoading,
}: Props) {
  const { volumeMax, ticks } = useMemo(() => {
    let max = 0
    for (const b of buckets) {
      for (const m of selectedVolumes) {
        max = Math.max(max, b[m] ?? 0)
      }
    }
    const top = niceMax(max)
    const ticks = [0, 1, 2, 3, 4].map((i) => Math.round((top / 4) * (4 - i)))
    return { volumeMax: top, ticks }
  }, [buckets, selectedVolumes])

  if (isLoading) {
    return (
      <div className="flex w-full animate-pulse items-end gap-1" style={{ height: CHART_HEIGHT }}>
        <div className="h-full w-full rounded bg-[#F4F4F5]" />
      </div>
    )
  }

  if (buckets.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-[#A1A1AA]"
        style={{ height: CHART_HEIGHT }}
      >
        当前条件下暂无数据
      </div>
    )
  }

  const hasRate = selectedRates.length > 0
  const showVolume = selectedVolumes.length > 0

  // Polyline points for each rate series
  const linesData = selectedRates.map((metric) => {
    const segments: string[][] = []
    let current: string[] = []
    buckets.forEach((b, i) => {
      const v = b[metric]
      if (v === null || v === undefined) {
        if (current.length) {
          segments.push(current)
          current = []
        }
        return
      }
      const xPct = ((i + 0.5) / buckets.length) * 100
      const yPct = 100 - Math.min(100, Math.max(0, v))
      current.push(`${xPct},${yPct}`)
    })
    if (current.length) segments.push(current)
    return { metric, segments }
  })

  return (
    <div className="flex w-full gap-2">
        {/* Left Y axis */}
        {showVolume ? (
          <div
            className="flex flex-col justify-between text-[11px] text-[#A1A1AA]"
            style={{ height: CHART_HEIGHT, minWidth: 32 }}
          >
            {ticks.map((t, idx) => (
              <span key={idx} className="leading-none">
                {t.toLocaleString('en-US')}
              </span>
            ))}
          </div>
        ) : null}

        {/* Chart body */}
        <div className="relative flex-1">
          {/* Grid baseline */}
          <div
            className="relative w-full overflow-hidden"
            style={{ height: CHART_HEIGHT }}
          >
            {/* Horizontal grid lines */}
            <div className="absolute inset-0 flex flex-col justify-between">
              {ticks.map((_, idx) => (
                <div
                  key={idx}
                  className={cn('h-px w-full', idx === ticks.length - 1 ? 'bg-[#E4E4E7]' : 'bg-[#F4F4F5]')}
                />
              ))}
            </div>

            {/* Bars row */}
            <div
              className="absolute inset-0 flex items-end justify-between px-1"
            >
              {buckets.map((b, i) => (
                <div key={i} className="flex items-end" style={{ gap: BAR_GAP }}>
                  {selectedVolumes.map((m) => {
                    const v = b[m] ?? 0
                    const h = volumeMax > 0 ? (v / volumeMax) * CHART_HEIGHT : 0
                    return (
                      <div
                        key={m}
                        title={`${METRIC_LABEL[m]}: ${v}`}
                        className="rounded-t-[2px]"
                        style={{
                          width: BAR_WIDTH,
                          height: h,
                          backgroundColor: METRIC_COLOR[m],
                        }}
                      />
                    )
                  })}
                </div>
              ))}
            </div>

            {/* Line overlay */}
            {hasRate ? (
              <svg
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                className="pointer-events-none absolute inset-0 h-full w-full"
              >
                {linesData.map(({ metric, segments }) =>
                  segments.map((pts, idx) => (
                    <polyline
                      key={`${metric}-${idx}`}
                      points={pts.join(' ')}
                      fill="none"
                      stroke={METRIC_COLOR[metric]}
                      strokeWidth="0.6"
                      vectorEffect="non-scaling-stroke"
                    />
                  )),
                )}
              </svg>
            ) : null}
          </div>

          {/* X axis labels */}
          <div className="mt-1 flex w-full items-start justify-between px-1 text-[11px] text-[#A1A1AA]">
            {buckets.map((b, i) => (
              <span
                key={i}
                className="text-center"
                style={{ minWidth: 0, flex: 1 }}
              >
                {formatTick(b.ts, granularity)}
              </span>
            ))}
          </div>
        </div>

        {/* Right Y axis (rates) */}
        {hasRate ? (
          <div
            className="flex flex-col justify-between text-[11px] text-[#F97316]"
            style={{ height: CHART_HEIGHT, minWidth: 32 }}
          >
            {[100, 75, 50, 25, 0].map((p) => (
              <span key={p} className="leading-none">
                {p}%
              </span>
            ))}
          </div>
        ) : null}
      </div>
  )
}
