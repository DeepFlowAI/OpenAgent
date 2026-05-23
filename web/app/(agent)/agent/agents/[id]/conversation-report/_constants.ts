import type { ReportGranularity } from '@/models/conversation-report'

export const VOLUME_METRICS = [
  'session_count',
  'effective_session_count',
  'user_message_count',
  'agent_message_count',
  'like_count',
  'dislike_count',
] as const

export const RATE_METRICS = ['reply_rate', 'like_rate', 'dislike_rate'] as const

export type VolumeMetric = (typeof VOLUME_METRICS)[number]
export type RateMetric = (typeof RATE_METRICS)[number]

export const METRIC_LABEL: Record<VolumeMetric | RateMetric, string> = {
  session_count: '会话量',
  effective_session_count: '有效会话数',
  user_message_count: '用户消息数',
  agent_message_count: 'Agent消息数',
  like_count: '喜欢',
  dislike_count: '不喜欢',
  reply_rate: '回答率',
  like_rate: '喜欢率',
  dislike_rate: '不喜欢率',
}

export const METRIC_COLOR: Record<VolumeMetric | RateMetric, string> = {
  session_count: '#7CB3F0',
  effective_session_count: '#A78BFA',
  user_message_count: '#4ADE80',
  agent_message_count: '#FBBF24',
  like_count: '#10B981',
  dislike_count: '#EF4444',
  reply_rate: '#F97316',
  like_rate: '#10B981',
  dislike_rate: '#EF4444',
}

export const DEFAULT_VOLUME_SELECTED: Record<VolumeMetric, boolean> = {
  session_count: true,
  effective_session_count: true,
  user_message_count: true,
  agent_message_count: true,
  like_count: false,
  dislike_count: false,
}

export const DEFAULT_RATE_SELECTED: Record<RateMetric, boolean> = {
  reply_rate: false,
  like_rate: false,
  dislike_rate: false,
}

export const GRANULARITY_OPTIONS: { value: ReportGranularity; label: string }[] = [
  { value: 'half_hour', label: '半小时' },
  { value: 'hour', label: '小时' },
  { value: 'day', label: '日' },
  { value: 'month', label: '月' },
]

export const DEFAULT_GRANULARITY: ReportGranularity = 'hour'

// Default report range: today
export const DEFAULT_RANGE_DAYS = 1
export const MAX_RANGE_DAYS = 366

export const DEBOUNCE_MS = 300
