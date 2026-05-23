// API response types for the conversation report endpoints.

export type ReportGranularity = 'half_hour' | 'hour' | 'day' | 'month'

export type ReportOverview = {
  session_count: number
  effective_session_count: number
  user_message_count: number
  agent_message_count: number
  reply_rate: number | null
  like_count: number
  dislike_count: number
  like_rate: number | null
  dislike_rate: number | null
}

export type ReportTrendBucket = {
  ts: string
  session_count: number
  effective_session_count: number
  user_message_count: number
  agent_message_count: number
  like_count: number
  dislike_count: number
  reply_rate: number | null
  like_rate: number | null
  dislike_rate: number | null
}

export type ReportTrendResponse = {
  granularity: ReportGranularity
  buckets: ReportTrendBucket[]
}
