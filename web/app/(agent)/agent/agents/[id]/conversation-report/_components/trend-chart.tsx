'use client'

import { useEffect, useMemo, useRef } from 'react'
import { BarChart, LineChart } from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  type GridComponentOption,
  type TooltipComponentOption,
} from 'echarts/components'
import { init, use, type ComposeOption, type EChartsType } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import type { BarSeriesOption, LineSeriesOption } from 'echarts/charts'

import type {
  ReportGranularity,
  ReportTrendBucket,
} from '@/models/conversation-report'

import {
  METRIC_COLOR,
  METRIC_LABEL,
  type RateMetric,
  type VolumeMetric,
} from '../_constants'

use([BarChart, LineChart, GridComponent, TooltipComponent, CanvasRenderer])

type ChartOption = ComposeOption<
  BarSeriesOption | LineSeriesOption | GridComponentOption | TooltipComponentOption
>

type Props = {
  buckets: ReportTrendBucket[]
  granularity: ReportGranularity
  selectedVolumes: VolumeMetric[]
  selectedRates: RateMetric[]
  isLoading: boolean
}

function formatTick(iso: string, granularity: ReportGranularity): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (value: number) => String(value).padStart(2, '0')
  const month = pad(date.getMonth() + 1)
  const day = pad(date.getDate())
  const hour = pad(date.getHours())
  const minute = pad(date.getMinutes())

  if (granularity === 'half_hour' || granularity === 'hour') return `${hour}:${minute}`
  if (granularity === 'day') return `${month}-${day}`
  return `${date.getFullYear()}-${month}`
}

function niceMax(value: number): number {
  if (value <= 0) return 10
  const power = 10 ** Math.floor(Math.log10(value))
  const normalized = value / power
  if (normalized > 5) return 10 * power
  if (normalized > 2) return 5 * power
  if (normalized > 1) return 2 * power
  return power
}

export function TrendChart({
  buckets,
  granularity,
  selectedVolumes,
  selectedRates,
  isLoading,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<EChartsType | null>(null)

  const option = useMemo<ChartOption>(() => {
    const volumeMax = niceMax(
      Math.max(0, ...buckets.flatMap((bucket) => selectedVolumes.map((metric) => bucket[metric]))),
    )
    const hasVolumes = selectedVolumes.length > 0
    const hasRates = selectedRates.length > 0

    return {
      animationDuration: 200,
      grid: {
        top: 8,
        right: hasRates ? 48 : 12,
        bottom: 30,
        left: hasVolumes ? 44 : 12,
        containLabel: false,
      },
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        backgroundColor: '#18181B',
        borderWidth: 0,
        padding: [8, 10],
        textStyle: { color: '#FFFFFF', fontSize: 12 },
      },
      xAxis: {
        type: 'category',
        data: buckets.map((bucket) => formatTick(bucket.ts, granularity)),
        axisLine: { lineStyle: { color: '#E4E4E7' } },
        axisTick: { show: false },
        axisLabel: { color: '#A1A1AA', fontSize: 11, interval: 0 },
      },
      yAxis: [
        {
          type: 'value',
          show: hasVolumes,
          min: 0,
          max: volumeMax,
          minInterval: 1,
          splitNumber: volumeMax <= 5 ? volumeMax : 4,
          axisLabel: { color: '#A1A1AA', fontSize: 11 },
          splitLine: { lineStyle: { color: '#F4F4F5' } },
        },
        {
          type: 'value',
          show: hasRates,
          min: 0,
          max: 100,
          interval: 25,
          axisLabel: { color: '#A1A1AA', fontSize: 11, formatter: '{value}%' },
          splitLine: { show: false },
        },
      ],
      series: [
        ...selectedVolumes.map<BarSeriesOption>((metric) => ({
          name: METRIC_LABEL[metric],
          type: 'bar',
          data: buckets.map((bucket) => bucket[metric]),
          barMaxWidth: 10,
          itemStyle: { color: METRIC_COLOR[metric], borderRadius: [2, 2, 0, 0] },
          emphasis: { focus: 'series' },
        })),
        ...selectedRates.map<LineSeriesOption>((metric) => ({
          name: METRIC_LABEL[metric],
          type: 'line',
          yAxisIndex: 1,
          data: buckets.map((bucket) => bucket[metric]),
          connectNulls: false,
          showSymbol: true,
          symbolSize: 5,
          lineStyle: { color: METRIC_COLOR[metric], width: 2 },
          itemStyle: { color: METRIC_COLOR[metric] },
          emphasis: { focus: 'series' },
        })),
      ],
    }
  }, [buckets, granularity, selectedRates, selectedVolumes])

  useEffect(() => {
    if (!containerRef.current) return
    const chart = init(containerRef.current)
    const observer = new ResizeObserver(() => chart.resize())
    observer.observe(containerRef.current)
    chartRef.current = chart

    return () => {
      observer.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [])

  useEffect(() => {
    if (!chartRef.current) return
    if (isLoading || buckets.length === 0) {
      chartRef.current.clear()
      return
    }
    chartRef.current.setOption(option, { notMerge: true })
  }, [buckets.length, isLoading, option])

  return (
    <div className="relative h-[248px] w-full">
      <div ref={containerRef} className="h-full w-full" />
      {isLoading ? (
        <div className="absolute inset-0 animate-pulse rounded bg-[#F4F4F5]" />
      ) : null}
      {!isLoading && buckets.length === 0 ? (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-[#A1A1AA]">
          当前条件下暂无数据
        </div>
      ) : null}
    </div>
  )
}
