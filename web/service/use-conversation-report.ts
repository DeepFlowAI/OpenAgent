import { useQuery } from '@tanstack/react-query'

import { get } from './base'
import type {
  ReportGranularity,
  ReportOverview,
  ReportTrendResponse,
} from '@/models/conversation-report'

const NS = 'conversation-report'

export const reportKeys = {
  all: [NS] as const,
  overview: (params: Record<string, unknown>) =>
    [...reportKeys.all, 'overview', params] as const,
  trend: (params: Record<string, unknown>) =>
    [...reportKeys.all, 'trend', params] as const,
}

export type ReportTimeRange = {
  startedAtFrom: string
  startedAtTo: string
}

export const useReportOverview = (
  agentId: number,
  range: ReportTimeRange | null,
) =>
  useQuery({
    queryKey: reportKeys.overview({ agentId, ...range }),
    queryFn: () =>
      get<ReportOverview>(
        `v1/agents/${agentId}/conversation-report/overview`,
        {
          searchParams: {
            started_at_from: range!.startedAtFrom,
            started_at_to: range!.startedAtTo,
          },
        },
      ),
    enabled: Boolean(agentId && range),
  })

export const useReportTrend = (
  agentId: number,
  range: ReportTimeRange | null,
  granularity: ReportGranularity,
) =>
  useQuery({
    queryKey: reportKeys.trend({ agentId, granularity, ...range }),
    queryFn: () =>
      get<ReportTrendResponse>(
        `v1/agents/${agentId}/conversation-report/trend`,
        {
          searchParams: {
            started_at_from: range!.startedAtFrom,
            started_at_to: range!.startedAtTo,
            granularity,
          },
        },
      ),
    enabled: Boolean(agentId && range && granularity),
  })
