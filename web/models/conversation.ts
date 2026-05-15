// Conversation response type (matches ConversationResponse schema)
export type Conversation = {
  id: number
  tenant_id: string
  agent_id: number
  external_id: string
  external_user_id: string | null
  source: 'chat' | 'api' | 'embed'
  status: 'active' | 'ended'
  title: string | null
  display_name: string | null
  email: string | null
  phone: string | null
  avatar_url: string | null
  started_at: string | null
  ended_at: string | null
  round_count: number
  llm_call_count: number
  tool_call_count: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  created_at: string | null
  updated_at: string | null
}

// Extended detail with duration
export type ConversationDetail = Conversation & {
  duration_seconds: number | null
}

// Step types for the execution timeline
export type StepType = 'user_message' | 'llm_call' | 'tool_call' | 'assistant_message'
/**
 * Backend persists `'incomplete'` for partial llm_call rows whose stream was
 * cut off mid-flight (sub-req 2). The public timeline endpoint filters those
 * out for end-user history reconstruction; the admin/log timeline keeps them
 * visible for debugging. Either way, the type lives at the API boundary so
 * stale clients don't crash on the new value.
 */
export type StepStatus = 'pending' | 'running' | 'success' | 'error' | 'incomplete'

// Lightweight step for timeline rendering
export type StepTimelineItem = {
  id: number
  conversation_id: number
  round_number: number
  step_order: number
  step_type: StepType
  client_message_id: string | null
  content: string | null

  // LLM summary fields
  model_name: string | null
  provider: string | null
  thinking_enabled: boolean | null
  thinking_content: string | null
  finish_reason: string | null
  request_id: string | null
  input_tokens: number | null
  output_tokens: number | null
  total_tokens: number | null
  duration_ms: number | null
  response_tool_calls: unknown[] | null

  // Tool call summary fields
  tool_name: string | null
  tool_type: string | null
  tool_call_id: string | null
  brief: string | null

  // Relationships
  parent_step_id: number | null

  // Common
  status: StepStatus
  error_message: string | null
  created_at: string | null
}

// Tool call step detail (embedded in LLM step response)
export type ToolCallStepItem = {
  id: number
  step_order: number
  tool_name: string | null
  tool_type: string | null
  tool_call_id: string | null
  tool_arguments: Record<string, unknown> | null
  tool_response: string | null
  brief: string | null
  status: StepStatus
  error_message: string | null
  duration_ms: number | null
  created_at: string | null
}

// Full step detail for LLM modal
export type StepDetail = StepTimelineItem & {
  request_messages: unknown[] | null
  request_tools: unknown[] | null
  request_params: Record<string, unknown> | null
  tool_arguments: Record<string, unknown> | null
  tool_response: string | null
  tool_call_steps: ToolCallStepItem[]
}

// Timeline response wrapper
export type ConversationTimelineResponse = {
  conversation_id: number
  steps: StepTimelineItem[]
  total_steps: number
}

// Source label mapping
export const SOURCE_LABELS: Record<string, string> = {
  chat: '对话窗口',
  api: 'API',
  embed: '嵌入式',
}

// Status label mapping
export const STATUS_LABELS: Record<string, string> = {
  active: '进行中',
  ended: '已结束',
}

// ── Chat SSE Event Types ──

export type ChatSSEEventType =
  | 'conversation_created'
  | 'round_start'
  | 'thinking_delta'
  | 'content_delta'
  | 'tool_call'
  | 'tool_result'
  | 'llm_step_created'
  | 'assistant_reset'
  | 'done'
  | 'error'

/**
 * Server-driven watchdog timeouts (sub-req 4). Sent on every `round_start`
 * so the SDK can adopt model-appropriate values (thinking models legitimately
 * need 60–120s first-chunk windows; fast models 30s is plenty). Replaces the
 * old hardcoded constants on the client.
 */
export type WatchdogConfig = {
  first_chunk_ms: number
  chunk_idle_ms: number
  overall_ms: number
}

/**
 * Sent at the top of every round (fresh AND resume). Carries the resume
 * cursor's frame of reference (`round_number`), the idempotency-key echo
 * for verification, and watchdog tuning the SDK should adopt for this
 * round's life. The frame's `id:` line (e.g. `r1-e0`) is the resume cursor
 * the client persists for Last-Event-ID reconnection.
 */
export type RoundStartEvent = {
  round_number: number
  resume: boolean
  client_message_id: string | null
  watchdog: WatchdogConfig
}

/**
 * Reason the backend gives for a stream-level reset retry (stream-level retry spec).
 *
 * - `first_chunk_timeout` / `idle_timeout` / `stream_error` /
 *   `missing_finish_reason`: emitted from the in-flight LLM stream retry
 *   loop right before re-streaming a fresh attempt for the same tool round.
 * - `resume_discard_incomplete`: emitted by the resume branch when the
 *   previous attempt persisted a partial llm_call (status='incomplete') and
 *   we're regenerating that tool round from scratch. Reuses the same UI
 *   handler so the assistant bubble is wiped before fresh deltas arrive.
 */
export type AssistantResetReason =
  | 'first_chunk_timeout'
  | 'idle_timeout'
  | 'stream_error'
  | 'missing_finish_reason'
  | 'resume_discard_incomplete'

export type ConversationCreatedEvent = {
  conversation_id: number
  external_id: string
}

export type ThinkingDeltaEvent = {
  content: string
}

export type ContentDeltaEvent = {
  content: string
}

export type ToolCallEvent = {
  step_id: number
  tool_name: string
  brief: string
  tool_call_id: string
}

export type ToolResultEvent = {
  tool_call_id: string
  result: string
}

export type LlmStepCreatedEvent = {
  step_id: number
}

/**
 * Backend tells the client to wipe the in-progress assistant message before
 * restreaming a fresh attempt (stream-level retry spec §4.5). NOT a stream-end sentinel —
 * SSE events keep flowing afterward as if a new round just started.
 */
export type AssistantResetEvent = {
  round_number: number
  tool_round: number
  reason: AssistantResetReason
}

export type DoneEvent = {
  assistant_step_id: number | null
  final_content?: string
}

export type ChatErrorEvent = {
  message: string
}

// ── Chat Message UI Types ──

export type ChatRole = 'user' | 'assistant'

export type ThinkingBlock = {
  id: string
  content: string
  llmStepId: number | null
  isStreaming: boolean
  timelineIndex: number
}

export type ToolBlock = {
  id: string
  toolName: string
  brief: string
  toolCallId: string
  stepId: number | null
  llmStepId: number | null
  isExecuting: boolean
  timelineIndex: number
}

export type ContentBlock = {
  id: string
  content: string
  llmStepId: number | null
  isStreaming: boolean
  timelineIndex: number
}

export type ChatMessage = {
  id: string
  role: ChatRole
  content: string
  timestamp: string
  isStreaming: boolean
  thinkingBlocks: ThinkingBlock[]
  contentBlocks: ContentBlock[]
  toolBlocks: ToolBlock[]
  llmStepId: number | null
  assistantStepId: number | null
  /**
   * Surface stream-level failures (network drop, server `event: error`,
   * exhausted retry budget) without overwriting any partial content already
   * shown. UI renders this as a separate error banner so the user can clearly
   * tell "model never finished" from "model said this on purpose".
   */
  errorMessage?: string | null
  /**
   * Soft reconnect indicator (sub-req 4). Set when the SDK fires onRetry,
   * cleared when fresh deltas arrive, when the stream completes, or when the
   * outer error path ultimately resolves. Lets the UI show "网络不稳，重连中
   * (n/max)" without overwriting partial content.
   */
  retryStatus?: { attempt: number; maxAttempts: number } | null
}
