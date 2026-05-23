'use client'

import type { ReportOverview } from '@/models/conversation-report'

type Props = {
  data: ReportOverview | undefined
  isLoading: boolean
}

function formatInt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString('en-US')
}

function formatRate(rate: number | null | undefined): string {
  if (rate === null || rate === undefined) return '—'
  return `${rate.toFixed(1)}%`
}

type CardProps = {
  label: string
  primary: string
  secondary?: string | null
  isSkeleton?: boolean
}

function MetricCard({ label, primary, secondary, isSkeleton }: CardProps) {
  return (
    <div className="flex flex-col gap-1.5 rounded-[10px] border border-[#E4E4E7] bg-white p-4">
      <span className="text-[13px] text-[#71717A]">{label}</span>
      {isSkeleton ? (
        <span className="h-7 w-20 animate-pulse rounded bg-[#F4F4F5]" />
      ) : (
        <span className="font-[var(--font-display,inherit)] text-[28px] font-bold leading-none text-[#18181B]">
          {primary}
        </span>
      )}
      {secondary ? (
        <span className="text-[13px] text-[#71717A]">{secondary}</span>
      ) : null}
    </div>
  )
}

export function OverviewSection({ data, isLoading }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <span className="text-[15px] font-semibold text-[#18181B]">概览</span>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="会话量"
          primary={formatInt(data?.session_count)}
          isSkeleton={isLoading}
        />
        <MetricCard
          label="有效会话数"
          primary={formatInt(data?.effective_session_count)}
          isSkeleton={isLoading}
        />
        <MetricCard
          label="用户消息数"
          primary={formatInt(data?.user_message_count)}
          isSkeleton={isLoading}
        />
        <MetricCard
          label="Agent消息数"
          primary={formatInt(data?.agent_message_count)}
          isSkeleton={isLoading}
        />
      </div>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <MetricCard
          label="回答率"
          primary={formatRate(data?.reply_rate)}
          isSkeleton={isLoading}
        />
        <MetricCard
          label="喜欢"
          primary={formatInt(data?.like_count)}
          secondary={data ? `占比 ${formatRate(data.like_rate)}` : null}
          isSkeleton={isLoading}
        />
        <MetricCard
          label="不喜欢"
          primary={formatInt(data?.dislike_count)}
          secondary={data ? `占比 ${formatRate(data.dislike_rate)}` : null}
          isSkeleton={isLoading}
        />
      </div>
    </div>
  )
}
