'use client'

import { useMemo } from 'react'

import { cn } from '@/utils/classnames'
import type {
  ReportGranularity,
  ReportTrendBucket,
  ReportTrendResponse,
} from '@/models/conversation-report'

import {
  GRANULARITY_OPTIONS,
  RATE_METRICS,
  VOLUME_METRICS,
  type RateMetric,
  type VolumeMetric,
} from '../_constants'
import { MetricToggles } from './metric-toggles'
import { TrendChart } from './trend-chart'
import { TrendTable } from './trend-table'

type Props = {
  data: ReportTrendResponse | undefined
  isLoading: boolean
  granularity: ReportGranularity
  onGranularityChange: (g: ReportGranularity) => void
  volumeSelected: Record<VolumeMetric, boolean>
  rateSelected: Record<RateMetric, boolean>
  onVolumeChange: (next: Record<VolumeMetric, boolean>) => void
  onRateChange: (next: Record<RateMetric, boolean>) => void
}

function percentage(numerator: number, denominator: number): number | null {
  if (denominator <= 0) return null
  return Math.round((numerator / denominator) * 1000) / 10
}

function naturalHourTs(hour: number): string {
  return new Date(2000, 0, 1, hour, 0, 0, 0).toISOString()
}

function toNaturalHourBuckets(
  buckets: ReportTrendBucket[],
  granularity: ReportGranularity,
): ReportTrendBucket[] {
  if (granularity !== 'half_hour' && granularity !== 'hour') return buckets

  const byHour = new Map<number, ReportTrendBucket>()
  for (const bucket of buckets) {
    const d = new Date(bucket.ts)
    if (Number.isNaN(d.getTime())) continue
    const hour = d.getHours()
    const current = byHour.get(hour) ?? {
      ts: naturalHourTs(hour),
      session_count: 0,
      effective_session_count: 0,
      user_message_count: 0,
      agent_message_count: 0,
      like_count: 0,
      dislike_count: 0,
      reply_rate: null,
      like_rate: null,
      dislike_rate: null,
    }

    current.session_count += bucket.session_count
    current.effective_session_count += bucket.effective_session_count
    current.user_message_count += bucket.user_message_count
    current.agent_message_count += bucket.agent_message_count
    current.like_count += bucket.like_count
    current.dislike_count += bucket.dislike_count
    byHour.set(hour, current)
  }

  return Array.from(byHour.values()).map((bucket) => {
    const feedbackTotal = bucket.like_count + bucket.dislike_count
    return {
      ...bucket,
      reply_rate: percentage(bucket.agent_message_count, bucket.user_message_count),
      like_rate: percentage(bucket.like_count, feedbackTotal),
      dislike_rate: percentage(bucket.dislike_count, feedbackTotal),
    }
  })
}

export function TrendSection({
  data,
  isLoading,
  granularity,
  onGranularityChange,
  volumeSelected,
  rateSelected,
  onVolumeChange,
  onRateChange,
}: Props) {
  const buckets = useMemo(
    () => toNaturalHourBuckets(data?.buckets ?? [], granularity),
    [data?.buckets, granularity],
  )
  const selectedVolumes = VOLUME_METRICS.filter((m) => volumeSelected[m])
  const selectedRates = RATE_METRICS.filter((m) => rateSelected[m])

  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <span className="text-[15px] font-semibold text-[#18181B]">趋势</span>
        <div className="flex h-9 items-center rounded-lg border border-[#E4E4E7] bg-white p-0.5">
          {GRANULARITY_OPTIONS.map((opt) => {
            const isActive = granularity === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => onGranularityChange(opt.value)}
                className={cn(
                  'h-8 rounded-md px-3 text-[13px] transition-colors',
                  isActive
                    ? 'bg-[#18181B] text-white'
                    : 'text-[#52525B] hover:text-[#18181B]',
                )}
              >
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>
      <div className="rounded-[10px] border border-[#E4E4E7] bg-white p-5">
        <TrendChart
          buckets={buckets}
          granularity={granularity}
          selectedVolumes={selectedVolumes}
          selectedRates={selectedRates}
          isLoading={isLoading}
        />
      </div>

      <MetricToggles
        volumeSelected={volumeSelected}
        rateSelected={rateSelected}
        onVolumeChange={onVolumeChange}
        onRateChange={onRateChange}
      />

      <TrendTable
        buckets={buckets}
        granularity={granularity}
        isLoading={isLoading}
      />
    </section>
  )
}
