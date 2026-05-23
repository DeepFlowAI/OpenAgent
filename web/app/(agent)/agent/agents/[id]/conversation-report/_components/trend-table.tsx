'use client'

import type {
  ReportGranularity,
  ReportTrendBucket,
} from '@/models/conversation-report'

import { METRIC_LABEL, RATE_METRICS, VOLUME_METRICS } from '../_constants'

type Props = {
  buckets: ReportTrendBucket[]
  granularity: ReportGranularity
  isLoading: boolean
}

function formatTime(iso: string, granularity: ReportGranularity): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  const yy = d.getFullYear()
  const mm = pad(d.getMonth() + 1)
  const dd = pad(d.getDate())
  const hh = pad(d.getHours())
  const mi = pad(d.getMinutes())
  if (granularity === 'half_hour' || granularity === 'hour') {
    return `${hh}:${mi}`
  }
  if (granularity === 'day') return `${yy}-${mm}-${dd}`
  return `${yy}-${mm}`
}

function formatRate(v: number | null): string {
  return v === null ? '—' : `${v.toFixed(1)}%`
}

export function TrendTable({ buckets, granularity, isLoading }: Props) {
  return (
    <div className="flex flex-col gap-2">
      <span className="text-[13px] font-medium text-[#52525B]">趋势数据</span>
      <div className="max-h-[320px] overflow-auto rounded-[8px] border border-[#E4E4E7]">
        <table className="w-full min-w-[760px] table-fixed border-collapse text-[12px]">
          <thead className="sticky top-0 z-10 bg-[#FAFAFA] text-left text-[#71717A]">
            <tr>
              <th className="px-3 py-2 font-medium">时间</th>
              {VOLUME_METRICS.map((m) => (
                <th key={m} className="px-3 py-2 font-medium">
                  {METRIC_LABEL[m]}
                </th>
              ))}
              {RATE_METRICS.map((m) => (
                <th key={m} className="px-3 py-2 font-medium">
                  {METRIC_LABEL[m]}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="text-[#18181B]">
            {isLoading ? (
              <tr>
                <td className="px-3 py-6 text-center text-[#A1A1AA]" colSpan={10}>
                  加载中…
                </td>
              </tr>
            ) : buckets.length === 0 ? (
              <tr>
                <td className="px-3 py-6 text-center text-[#A1A1AA]" colSpan={10}>
                  当前条件下暂无数据
                </td>
              </tr>
            ) : (
              buckets.map((b, i) => (
                <tr key={b.ts + i} className="border-t border-[#F4F4F5]">
                  <td className="px-3 py-2 whitespace-nowrap">{formatTime(b.ts, granularity)}</td>
                  {VOLUME_METRICS.map((m) => (
                    <td key={m} className="px-3 py-2">
                      {(b[m] ?? 0).toLocaleString('en-US')}
                    </td>
                  ))}
                  {RATE_METRICS.map((m) => (
                    <td key={m} className="px-3 py-2">
                      {formatRate(b[m] ?? null)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
