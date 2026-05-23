'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'next/navigation'

import { useToast } from '@/app/components/base/toast'
import { getErrorMessage } from '@/service/base'
import type { ReportGranularity } from '@/models/conversation-report'
import {
  useReportOverview,
  useReportTrend,
  type ReportTimeRange,
} from '@/service/use-conversation-report'

import {
  dateRangeToApi,
  getDefaultDateRange,
  matchPreset,
  parseDateRangeFromQuery,
  resolvePresetRange,
  validateDateRange,
  type DateRangeDraft,
  type QuickRangePresetId,
} from './_date-range'
import {
  DEBOUNCE_MS,
  DEFAULT_GRANULARITY,
  DEFAULT_RATE_SELECTED,
  DEFAULT_VOLUME_SELECTED,
  GRANULARITY_OPTIONS,
  type RateMetric,
  type VolumeMetric,
} from './_constants'
import { FilterBar } from './_components/filter-bar'
import { OverviewSection } from './_components/overview-section'
import { TrendSection } from './_components/trend-section'

function isValidGranularity(value: string | null): value is ReportGranularity {
  return !!value && GRANULARITY_OPTIONS.some((opt) => opt.value === value)
}

function toAppliedRange(range: DateRangeDraft): ReportTimeRange {
  const api = dateRangeToApi(range)
  return {
    startedAtFrom: api.startedAtFrom,
    startedAtTo: api.startedAtTo,
  }
}

export default function ConversationReportPage() {
  const params = useParams()
  const searchParams = useSearchParams()
  const agentId = Number(params.id)
  const { toast } = useToast()

  const initialRange = useMemo(() => {
    const fromQs = searchParams.get('started_at_from')
    const toQs = searchParams.get('started_at_to')
    return parseDateRangeFromQuery(fromQs, toQs) ?? getDefaultDateRange()
  }, [searchParams])

  const [draftRange, setDraftRange] = useState<DateRangeDraft>(initialRange)
  const [appliedRange, setAppliedRange] = useState<ReportTimeRange | null>(() => {
    const err = validateDateRange(initialRange)
    return err ? null : toAppliedRange(initialRange)
  })

  const activePreset = useMemo(() => matchPreset(draftRange), [draftRange])

  const [granularity, setGranularity] = useState<ReportGranularity>(() => {
    const fromQs = searchParams.get('granularity')
    return isValidGranularity(fromQs) ? fromQs : DEFAULT_GRANULARITY
  })

  const [volumeSelected, setVolumeSelected] = useState<Record<VolumeMetric, boolean>>(
    () => ({ ...DEFAULT_VOLUME_SELECTED }),
  )
  const [rateSelected, setRateSelected] = useState<Record<RateMetric, boolean>>(
    () => ({ ...DEFAULT_RATE_SELECTED }),
  )

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastShownErrorRef = useRef<string | null>(null)

  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    debounceTimerRef.current = setTimeout(() => {
      const err = validateDateRange(draftRange)
      if (err) {
        if (err !== lastShownErrorRef.current) {
          toast(err, 'error')
          lastShownErrorRef.current = err
        }
        setAppliedRange(null)
        return
      }
      lastShownErrorRef.current = null
      setAppliedRange(toAppliedRange(draftRange))
    }, DEBOUNCE_MS)
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current)
    }
  }, [draftRange, toast])

  const syncedKeyRef = useRef('')
  useEffect(() => {
    if (!appliedRange) return
    const key = `${draftRange.startDate}|${draftRange.endDate}|${granularity}`
    if (syncedKeyRef.current === key) return
    syncedKeyRef.current = key
    const qs = new URLSearchParams()
    qs.set('started_at_from', draftRange.startDate)
    qs.set('started_at_to', draftRange.endDate)
    qs.set('granularity', granularity)
    const next = `${window.location.pathname}?${qs.toString()}`
    window.history.replaceState({}, '', next)
  }, [appliedRange, draftRange, granularity])

  const handleRangeChange = useCallback((next: DateRangeDraft) => {
    setDraftRange(next)
  }, [])

  const handlePresetSelect = useCallback((preset: QuickRangePresetId) => {
    setDraftRange(resolvePresetRange(preset))
  }, [])

  const overviewQuery = useReportOverview(agentId, appliedRange)
  const trendQuery = useReportTrend(agentId, appliedRange, granularity)

  const lastErrRef = useRef<unknown>(null)
  useEffect(() => {
    const err = overviewQuery.error ?? trendQuery.error
    if (!err || err === lastErrRef.current) return
    lastErrRef.current = err
    void getErrorMessage(err).then((msg) => toast(msg, 'error'))
  }, [overviewQuery.error, trendQuery.error, toast])

  return (
    <div className="flex h-full flex-col">
      <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[#ECECEC] bg-white px-6 py-4">
        <span className="text-base font-semibold text-[#18181B]">会话报表</span>
      </div>

      <div className="flex flex-1 flex-col gap-6 overflow-auto p-6">
        <FilterBar
          range={draftRange}
          activePreset={activePreset}
          onRangeChange={handleRangeChange}
          onPresetSelect={handlePresetSelect}
        />

        <OverviewSection
          data={overviewQuery.data}
          isLoading={overviewQuery.isLoading}
        />

        <TrendSection
          data={trendQuery.data}
          isLoading={trendQuery.isLoading}
          granularity={granularity}
          onGranularityChange={setGranularity}
          volumeSelected={volumeSelected}
          rateSelected={rateSelected}
          onVolumeChange={setVolumeSelected}
          onRateChange={setRateSelected}
        />
      </div>
    </div>
  )
}
