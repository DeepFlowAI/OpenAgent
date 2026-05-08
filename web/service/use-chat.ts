'use client'

import type {
  ConversationCreatedEvent,
  RoundStartEvent,
  ThinkingDeltaEvent,
  ContentDeltaEvent,
  ToolCallEvent,
  ToolResultEvent,
  LlmStepCreatedEvent,
  AssistantResetEvent,
  DoneEvent,
  ChatErrorEvent,
  WatchdogConfig,
} from '@/models/conversation'
import { telemetry, createStreamMetrics, type StreamMetricsCollector } from '@/service/telemetry'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'

// ── SSE Resilience Tuning (sub-req 1 + 4) ────────────────────────
// Watchdog defaults. The server overrides these on every `round_start`
// (sub-req 4) — see `_StreamState.watchdog`. Defaults must still be sane
// for the *very first read* before the round_start frame arrives.
//
// First-chunk timeout MUST exceed the server's LLM_FIRST_CHUNK_TIMEOUT_SEC
// (30s) so we don't trip while a thinking model is starting up. Between-
// chunks timeout is sized for SSE heartbeat × 3 + buffer.
const DEFAULT_FIRST_CHUNK_TIMEOUT_MS = 35_000
const DEFAULT_CHUNK_IDLE_TIMEOUT_MS = 15_000
const DEFAULT_OVERALL_TIMEOUT_MS = 240_000
// Hard upper bound on a single sendChatMessage call (including all retries).
// Even when the server-pushed watchdog says "give it 5 minutes", we cap
// total wall-clock at this value to bound the worst case.
const HARD_OVERALL_TIMEOUT_CAP_MS = 600_000
// Backoff jitter ratio. Spreads simultaneous reconnects after mass disconnects.
const JITTER_RATIO = 0.25
// Retry-After header is clamped to a sane upper bound so a misbehaving server
// can't park the client for hours.
const RETRY_AFTER_MAX_MS = 60_000

// Wire-format gate for resume cursors. Pre-round frames carry `pre-e{n}` ids
// that the server's ChatRequest schema rejects, so we only persist round-
// scoped ids (`r{round}-e{seq}`) into `lastEventId`.
const _ROUND_EVENT_ID_RE = /^r\d+-e\d+$/

export type ChatEventHandlers = {
  onConversationCreated?: (data: ConversationCreatedEvent) => void
  /**
   * Sent at the top of every round (sub-req 4). Carries server-tuned
   * watchdog config and the `client_message_id` echo so the client can
   * verify the server is processing the right turn.
   */
  onRoundStart?: (data: RoundStartEvent) => void
  onThinkingDelta?: (data: ThinkingDeltaEvent) => void
  onContentDelta?: (data: ContentDeltaEvent) => void
  onToolCall?: (data: ToolCallEvent) => void
  onToolResult?: (data: ToolResultEvent) => void
  onLlmStepCreated?: (data: LlmStepCreatedEvent) => void
  onDone?: (data: DoneEvent) => void
  onError?: (data: ChatErrorEvent) => void
  /** Called before each automatic CLIENT-side retry (network failure / unexpected stream end). */
  onRetry?: (attempt: number, maxAttempts: number) => void
  /**
   * Called when the BACKEND tells us to wipe the partial assistant message
   * before restreaming (the stream-level retry spec, stream-level retry). The SSE keeps flowing
   * after this event — handle it as a "reset and keep listening" signal, not
   * a stream-end sentinel.
   */
  onAssistantReset?: (data: AssistantResetEvent) => void
}

export type RetryOptions = {
  /** Max retry attempts (default 2, total 3 attempts) */
  maxRetries?: number
  /** Base delay in ms for exponential backoff (default 1000) */
  baseDelay?: number
}

export type ChatStreamController = AbortController & {
  /** Resolves when the SSE stream reaches done/error, exhausts retry, or is aborted. */
  completion: Promise<void>
}

const DEFAULT_RETRY: Required<RetryOptions> = { maxRetries: 2, baseDelay: 1000 }

/**
 * Generate a short, human-readable per-request correlation id. Sent in the
 * chat request body as `request_id` and printed in backend log lines, so the
 * same id is searchable in your log backend via the MCP for cross-stack debugging.
 */
function _generateRequestId(): string {
  // 9 chars of base36 randomness ≈ 47 bits, plenty unique for one user's logs.
  const rnd = Math.random().toString(36).slice(2, 11)
  return `req_${rnd}`
}

/**
 * Generate a stable per-user-turn idempotency key (sub-req 3). This UUID is
 * created ONCE per `sendChatMessage` call and reused across every retry so
 * the server can detect "this is the same logical submission" and force-resume
 * instead of producing a duplicate user_message + LLM round.
 *
 * Falls back to a manual UUIDv4 implementation when `crypto.randomUUID` is
 * missing — older Android WebViews and some embedded browsers ship without it.
 */
function _generateClientMessageId(): string {
  const c = (typeof crypto !== 'undefined' ? crypto : null) as Crypto | null
  if (c && typeof c.randomUUID === 'function') {
    return c.randomUUID()
  }
  const bytes = new Uint8Array(16)
  if (c && typeof c.getRandomValues === 'function') {
    c.getRandomValues(bytes)
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256)
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

/**
 * Send a chat message via SSE streaming (authenticated).
 * Returns an AbortController that can be used to cancel the request.
 */
export function sendChatMessage(
  agentId: number,
  message: string,
  conversationId: number | null,
  handlers: ChatEventHandlers,
  retryOpts?: RetryOptions,
  conversationExternalId?: string | null,
): ChatStreamController {
  const controller = new AbortController() as ChatStreamController

  const url = `${API_BASE}v1/agents/${agentId}/chat`
  const token = localStorage.getItem('auth_token')

  // Mutable state: tracks ids across retries
  const state: _RetryState = {
    conversationId,
    conversationExternalId: conversationExternalId ?? null,
    requestId: _generateRequestId(),
    clientMessageId: _generateClientMessageId(),
    isRetry: false,
    lastEventId: null,
    sendStartedAtMs: Date.now(),
    retryCount: 0,
    trackedFirstChunk: false,
    streamMetrics: createStreamMetrics(),
    traceId: null,
    contentLen: 0,
    // Auth route has no channel token: telemetry events from this path
    // are intentionally dropped at the SDK layer so admin/internal
    // testing journeys can't co-mingle with the public-channel dataset
    // that real users produce.
    channelToken: null,
  }

  // Telemetry: top-of-turn marker. Carries ``channel_token: null`` so the
  // SDK drops it cleanly — kept in code rather than skipped to make the
  // observability contract uniform between auth and public routes.
  telemetry.track('message_send_start', {
    channel_token: state.channelToken,
    conversation_external_id: state.conversationExternalId,
    request_id: state.requestId,
    client_message_id: state.clientMessageId,
    props: {
      content_len: message.length,
      is_resume: false,
      auth: 'bearer',
    },
  })

  // Intercept conversation_created to capture both ids for retries / logs
  const wrappedHandlers: ChatEventHandlers = _instrumentTelemetry(handlers, state)

  const buildInit = (): RequestInit => ({
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message,
      conversation_id: state.conversationId,
      ...(state.conversationExternalId
        ? { conversation_external_id: state.conversationExternalId }
        : {}),
      request_id: state.requestId,
      client_message_id: state.clientMessageId,
      ...(state.isRetry ? { resume: true } : {}),
      // Sub-req 4: last_event_id is what unlocks the buffer fast-path on
      // the server. Only sent when we actually have one (no value on the
      // first attempt; on retries it's the most recent `id:` we saw).
      ...(state.lastEventId ? { last_event_id: state.lastEventId } : {}),
    }),
    signal: controller.signal,
  })

  controller.completion = _fetchSSEWithRetry(
    url,
    buildInit,
    wrappedHandlers,
    controller,
    state,
    retryOpts,
  )

  return controller
}

/**
 * Send a chat message via the public (no-auth) endpoint using channel token.
 */
export type CustomerContext = {
  external_user_id?: string
  display_name?: string
  source?: string
}

export function sendPublicChatMessage(
  channelToken: string,
  message: string,
  conversationId: number | null,
  handlers: ChatEventHandlers,
  embedToken?: string | null,
  customerContext?: CustomerContext | null,
  retryOpts?: RetryOptions,
  conversationExternalId?: string | null,
): ChatStreamController {
  const controller = new AbortController() as ChatStreamController

  let url = `${API_BASE}v1/public/channels/${channelToken}/chat`
  if (embedToken) {
    url += `?embed_token=${encodeURIComponent(embedToken)}`
  }

  // Mutable state: tracks ids across retries
  const state: _RetryState = {
    conversationId,
    conversationExternalId: conversationExternalId ?? null,
    requestId: _generateRequestId(),
    clientMessageId: _generateClientMessageId(),
    isRetry: false,
    lastEventId: null,
    sendStartedAtMs: Date.now(),
    retryCount: 0,
    trackedFirstChunk: false,
    streamMetrics: createStreamMetrics(),
    traceId: null,
    contentLen: 0,
    // Bind every telemetry track in this turn to the public channel
    // token. The SDK queues / persists / replays per-token, so two
    // sequential public chats on different channels in the same tab
    // never cross-contaminate each other's tenant_id/agent_id.
    channelToken,
  }

  telemetry.track('message_send_start', {
    channel_token: state.channelToken,
    conversation_external_id: state.conversationExternalId,
    request_id: state.requestId,
    client_message_id: state.clientMessageId,
    props: {
      content_len: message.length,
      is_resume: false,
      auth: 'channel_token',
      has_embed_token: !!embedToken,
    },
  })

  const wrappedHandlers: ChatEventHandlers = _instrumentTelemetry(handlers, state)

  const buildInit = (): RequestInit => ({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      conversation_id: state.conversationId,
      ...(state.conversationExternalId
        ? { conversation_external_id: state.conversationExternalId }
        : {}),
      request_id: state.requestId,
      client_message_id: state.clientMessageId,
      ...(state.isRetry ? { resume: true } : {}),
      ...(state.lastEventId ? { last_event_id: state.lastEventId } : {}),
      ...(!state.conversationId && customerContext ? { customer_context: customerContext } : {}),
    }),
    signal: controller.signal,
  })

  controller.completion = _fetchSSEWithRetry(
    url,
    buildInit,
    wrappedHandlers,
    controller,
    state,
    retryOpts,
  )

  return controller
}

// ── Internal helpers ──

/**
 * Wrap the caller-provided handlers so each lifecycle event also fires a
 * matching telemetry track. Reasoning is centralised here so the actual
 * fetch / dispatch code stays focused on the wire protocol — this wrapper
 * only adds observability side-effects, never changes control flow.
 *
 * State invariants:
 *   * ``state.streamMetrics`` is created in ``send*ChatMessage`` and used
 *     here on every ``content_delta`` / ``done`` to compute aggregates
 *     without leaking timestamp arrays into the dispatcher hot path.
 *   * ``state.trackedFirstChunk`` is a one-shot guard so ``sse_first_chunk``
 *     fires exactly once per turn, even across retries (resume-replay
 *     would otherwise re-trigger it).
 */
function _instrumentTelemetry(
  handlers: ChatEventHandlers,
  state: _RetryState,
): ChatEventHandlers {
  const baseProps = (): Record<string, string | number | boolean> => ({})

  return {
    ...handlers,
    onConversationCreated: (data) => {
      state.conversationId = data.conversation_id
      state.conversationExternalId = data.external_id ?? state.conversationExternalId
      handlers.onConversationCreated?.(data)
    },
    onRoundStart: (data) => {
      telemetry.track('sse_round_start', {
        channel_token: state.channelToken,
        conversation_external_id: state.conversationExternalId,
        request_id: state.requestId,
        client_message_id: state.clientMessageId,
        trace_id: state.traceId,
        props: {
          ...baseProps(),
          round_number: data.round_number ?? 0,
          resume: !!data.resume,
        },
        metrics: data.watchdog
          ? {
              first_chunk_ms: data.watchdog.first_chunk_ms ?? 0,
              chunk_idle_ms: data.watchdog.chunk_idle_ms ?? 0,
              overall_ms: data.watchdog.overall_ms ?? 0,
            }
          : null,
      })
      handlers.onRoundStart?.(data)
    },
    onContentDelta: (data) => {
      // Stream-metrics accumulator. Cheap (one push to an array) so it's
      // safe to run on the chunk hot path.
      state.streamMetrics?.recordChunk()
      if (typeof data?.content === 'string') {
        state.contentLen = (state.contentLen ?? 0) + data.content.length
      }
      // Fire ``sse_first_chunk`` exactly once per turn. ``Date.now() -
      // sendStartedAtMs`` gives the user-visible TTFB which is what we
      // want to slice users by; the watchdog config can change mid-turn
      // but the start point shouldn't.
      if (!state.trackedFirstChunk && state.sendStartedAtMs) {
        state.trackedFirstChunk = true
        telemetry.track('sse_first_chunk', {
          channel_token: state.channelToken,
          conversation_external_id: state.conversationExternalId,
          request_id: state.requestId,
          client_message_id: state.clientMessageId,
          trace_id: state.traceId,
          metrics: {
            first_chunk_ms: Date.now() - state.sendStartedAtMs,
          },
        })
      }
      handlers.onContentDelta?.(data)
    },
    onAssistantReset: (data) => {
      telemetry.track('assistant_reset_received', {
        channel_token: state.channelToken,
        conversation_external_id: state.conversationExternalId,
        request_id: state.requestId,
        client_message_id: state.clientMessageId,
        trace_id: state.traceId,
        level: 'warn',
        props: {
          reason: data?.reason ?? 'unknown',
        },
      })
      handlers.onAssistantReset?.(data)
    },
    onDone: (data) => {
      const finishMetrics = state.streamMetrics?.finish() ?? {
        total_duration_ms: state.sendStartedAtMs
          ? Date.now() - state.sendStartedAtMs
          : 0,
        chunk_count: 0,
        avg_chunk_idle_ms: 0,
        p95_chunk_idle_ms: 0,
        lag_1s_count: 0,
      }
      telemetry.track('sse_done', {
        channel_token: state.channelToken,
        conversation_external_id: state.conversationExternalId,
        request_id: state.requestId,
        client_message_id: state.clientMessageId,
        trace_id: state.traceId,
        props: {
          retry_count: state.retryCount ?? 0,
          content_len: state.contentLen ?? 0,
        },
        metrics: { ...finishMetrics },
      })
      handlers.onDone?.(data)
    },
    onError: (data) => {
      // ``sse_failed`` is the terminal error event — fired here only
      // when the retry loop has given up (the dispatcher inside _doFetchSSE
      // either swallowed earlier transient errors or upgraded to ``done``).
      // We don't have a great way to distinguish "user-cancel via abort"
      // from "real failure" at this layer; the abort path generally bypasses
      // onError so what reaches here is the genuine give-up signal.
      telemetry.track('sse_failed', {
        channel_token: state.channelToken,
        conversation_external_id: state.conversationExternalId,
        request_id: state.requestId,
        client_message_id: state.clientMessageId,
        trace_id: state.traceId,
        level: 'error',
        props: {
          final_error: (data?.message ?? 'unknown').slice(0, 200),
          retry_count: state.retryCount ?? 0,
        },
      })
      handlers.onError?.(data)
    },
    onRetry: (attempt, maxAttempts) => {
      state.retryCount = attempt
      telemetry.track('sse_retry', {
        channel_token: state.channelToken,
        conversation_external_id: state.conversationExternalId,
        request_id: state.requestId,
        client_message_id: state.clientMessageId,
        trace_id: state.traceId,
        level: 'warn',
        props: {
          attempt,
          max_retries: maxAttempts,
          last_event_id: state.lastEventId ?? '',
        },
      })
      handlers.onRetry?.(attempt, maxAttempts)
    },
  }
}

type _RetryState = {
  conversationId: number | null
  conversationExternalId?: string | null
  requestId?: string
  clientMessageId?: string
  isRetry: boolean
  /**
   * SSE Last-Event-ID resume cursor (sub-req 4). The most recent `id:` line
   * the dispatcher consumed. Sent on every retry; the server uses it to
   * replay only the events the client missed, instead of restreaming the
   * whole round through the older step-replay path.
   */
  lastEventId?: string | null
  /**
   * Telemetry-only fields (don't influence wire protocol). Tracked here so
   * stable per-turn metrics — like ``first_chunk_ms`` measured from the
   * initial ``message_send_start`` and ``retry_count`` accumulated across
   * attempts — survive the inner ``_doFetchSSE`` boundary.
   */
  sendStartedAtMs?: number
  retryCount?: number
  trackedFirstChunk?: boolean
  /** Aggregated stream metrics across the whole turn. Created at send-time. */
  streamMetrics?: StreamMetricsCollector
  /** Server-issued trace_id (X-Trace-Id) — captured on first 200 response so
   *  every subsequent telemetry event in the same turn can carry it. */
  traceId?: string | null
  /** Last seen content length so ``sse_done`` props.content_len is accurate
   *  even when delta dispatches don't happen on every chunk. */
  contentLen?: number
  /**
   * Telemetry routing channel for THIS turn. ``null`` for auth routes
   * (admin Test Drawer etc.) — telemetry SDK drops events with a null
   * channel so authenticated traffic never pollutes the public channel
   * dataset. Carried on retryState so the inner ``_doFetchSSE`` and
   * ``_fetchSSEWithRetry`` helpers can emit per-turn telemetry without
   * relying on a global singleton state that any other turn could
   * mutate concurrently (the original review caught exactly that bug).
   */
  channelToken: string | null
}

/**
 * Per-stream state shared between _fetchSSEWithRetry and _doFetchSSE so the
 * visibility-change watcher (installed at the outer level) can observe the
 * inner reader's last activity timestamp and abort it when the tab returns
 * to foreground after a long idle period.
 */
type _StreamState = {
  /** Timestamp of the most recent successful read() (Date.now()). */
  lastChunkAt: number
  /** Set true once the first non-empty chunk has been received. */
  firstChunkReceived: boolean
  /** Abort the in-flight inner fetch (watchdog-style). Reset per attempt. */
  watchdogAbort: (() => void) | null
  /**
   * Effective watchdog config (sub-req 4). Defaults match the historical
   * client constants; on every `round_start` the server overrides them
   * with model-appropriate values. Idle/first-chunk reads consult these,
   * not the module-level constants.
   */
  watchdog: WatchdogConfig
}

/**
 * Parse an HTTP `Retry-After` header. Supports the `delta-seconds` form
 * (most common for 429/503) and HTTP-date. Returns ms clamped to a safe
 * upper bound, or null if the header is absent / unparseable.
 */
function _parseRetryAfter(value: string | null): number | null {
  if (!value) return null
  const trimmed = value.trim()
  if (!trimmed) return null
  // delta-seconds: digits only
  if (/^\d+$/.test(trimmed)) {
    const sec = parseInt(trimmed, 10)
    if (!Number.isFinite(sec) || sec < 0) return null
    return Math.min(sec * 1000, RETRY_AFTER_MAX_MS)
  }
  // HTTP-date
  const ts = Date.parse(trimmed)
  if (Number.isNaN(ts)) return null
  const ms = ts - Date.now()
  if (ms <= 0) return 0
  return Math.min(ms, RETRY_AFTER_MAX_MS)
}

/**
 * Race reader.read() against an idle timer. On timeout, abort the inner fetch
 * via the watchdog and surface a synthetic AbortError so the outer logic can
 * distinguish it from user cancellation (which fires on a different signal).
 */
async function _readWithIdleTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  idleMs: number,
  watchdogAbort: () => void,
  onIdleFired?: (idleMs: number) => void,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  let timer: ReturnType<typeof setTimeout> | null = null
  try {
    const timeoutPromise = new Promise<never>((_, reject) => {
      timer = setTimeout(() => {
        // Notify the caller before aborting so a telemetry track can fire
        // with the exact ``idleMs`` that was breached. We avoid putting
        // the track here directly — the helper has no access to the
        // retry state and we want a single source of truth.
        onIdleFired?.(idleMs)
        watchdogAbort()
        reject(new DOMException('SSE idle timeout', 'AbortError'))
      }, idleMs)
    })
    return await Promise.race([reader.read(), timeoutPromise])
  } finally {
    if (timer) clearTimeout(timer)
  }
}

/**
 * Core SSE fetch with automatic retry on network failures.
 *
 * Retry triggers: network errors, unexpected stream disconnect (no done/error event).
 * Non-retryable: HTTP 4xx errors, user abort, received done/error event.
 *
 * On retry, sets state.isRetry=true so buildInit sends `resume: true` to the backend.
 * The backend replays saved steps and continues from the breakpoint.
 */
async function _fetchSSEWithRetry(
  url: string,
  buildInit: () => RequestInit,
  handlers: ChatEventHandlers,
  controller: AbortController,
  state: _RetryState,
  retryOpts?: RetryOptions,
) {
  const { maxRetries, baseDelay } = { ...DEFAULT_RETRY, ...retryOpts }
  let attempt = 0

  // Shared with _doFetchSSE so the visibility-change watcher can probe and
  // abort an inner fetch that's been idle while the tab was hidden.
  const streamState: _StreamState = {
    lastChunkAt: Date.now(),
    firstChunkReceived: false,
    watchdogAbort: null,
    watchdog: {
      first_chunk_ms: DEFAULT_FIRST_CHUNK_TIMEOUT_MS,
      chunk_idle_ms: DEFAULT_CHUNK_IDLE_TIMEOUT_MS,
      overall_ms: DEFAULT_OVERALL_TIMEOUT_MS,
    },
  }

  // Wall-clock cap: protects users from indefinite spinning across many
  // retries. The server can extend the BUDGET via `round_start.watchdog`
  // (thinking models can legitimately want >240s), but the timer always
  // counts from `overallStartedAt` — re-arming on every round_start would
  // otherwise let a sequence of resumes stretch the user-visible
  // "single sendChatMessage call" indefinitely. `HARD_OVERALL_TIMEOUT_CAP_MS`
  // is the hard upper bound regardless of what the server pushes.
  const overallStartedAt = Date.now()
  let overallTimedOut = false
  let overallTimer: ReturnType<typeof setTimeout> | null = null
  const fireOverallTimeout = () => {
    overallTimedOut = true
    streamState.watchdogAbort?.()
    controller.abort()
    telemetry.track('sse_overall_timeout', {
      channel_token: state.channelToken,
      conversation_external_id: state.conversationExternalId,
      request_id: state.requestId,
      client_message_id: state.clientMessageId,
      trace_id: state.traceId,
      level: 'error',
      metrics: {
        overall_ms: streamState.watchdog.overall_ms,
        elapsed_ms: Date.now() - overallStartedAt,
      },
    })
  }
  const armOverallTimer = (budgetMs: number) => {
    if (overallTimer) clearTimeout(overallTimer)
    const cappedBudget = Math.min(budgetMs, HARD_OVERALL_TIMEOUT_CAP_MS)
    const remaining = cappedBudget - (Date.now() - overallStartedAt)
    // remaining<=0: the new (smaller-or-equal) budget is already exhausted.
    // Schedule the abort on the next tick rather than firing synchronously
    // so the in-flight microtask (often the round_start handler itself)
    // unwinds cleanly first.
    overallTimer = setTimeout(fireOverallTimeout, Math.max(0, remaining))
  }
  armOverallTimer(streamState.watchdog.overall_ms)

  // Wrap onRoundStart so we can adopt the server's watchdog config and
  // re-arm the overall timer with the new value. The handler chain still
  // sees the original event for any UI-side logging.
  const originalOnRoundStart = handlers.onRoundStart
  handlers = {
    ...handlers,
    onRoundStart: (data) => {
      if (data?.watchdog) {
        streamState.watchdog = { ...data.watchdog }
        armOverallTimer(streamState.watchdog.overall_ms)
      }
      originalOnRoundStart?.(data)
    },
  }

  // visibilitychange: timers can be throttled or paused while the tab is in
  // the background (esp. iOS WebView). When we return to foreground, if the
  // last chunk timestamp is older than the inter-chunk watchdog, the
  // underlying connection is almost certainly dead — abort the inner fetch
  // so the retry loop kicks in immediately instead of waiting out the
  // (possibly throttled) watchdog timer.
  const onVisibilityChange = () => {
    if (typeof document === 'undefined') return
    if (document.visibilityState !== 'visible') return
    if (!streamState.firstChunkReceived) return
    const idleMs = Date.now() - streamState.lastChunkAt
    if (idleMs >= streamState.watchdog.chunk_idle_ms) {
      streamState.watchdogAbort?.()
    }
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVisibilityChange)
  }

  // Helper: emit overall-timeout error exactly once per call. The timer can
  // fire during _doFetchSSE, between attempts, or during _waitForRetry; we
  // need every branch to dispatch the same user-visible message.
  let overallTimeoutEmitted = false
  const emitOverallTimeout = () => {
    if (overallTimeoutEmitted) return
    overallTimeoutEmitted = true
    handlers.onError?.({
      message: `网络连接已超过 ${Math.round(streamState.watchdog.overall_ms / 1000)} 秒未恢复，请稍后重试`,
    })
  }

  try {
    while (true) {
      // Pre-attempt guard: caller already aborted (user cancel or overall
      // timer fired before we even kicked off this attempt).
      if (controller.signal.aborted) {
        if (overallTimedOut) emitOverallTimeout()
        return
      }

      const result = await _doFetchSSE(url, buildInit(), handlers, controller, streamState, state)

      // Order matters: when the overall timer fired, _doFetchSSE returns
      // completed=true (it can't tell user-cancel from timeout). We MUST
      // check the timeout flag BEFORE the completed/nonRetryable early
      // return, otherwise the user sees a silent abort instead of the
      // "网络连接已超过 240 秒未恢复" banner.
      if (result.abortedByUserSignal && overallTimedOut) {
        emitOverallTimeout()
        return
      }

      // Stream completed normally (done/error event received) or non-retryable
      if (result.completed || result.nonRetryable) return

      // Defensive: handle the rare case where the user signal aborted during
      // _doFetchSSE but the function returned completed=false anyway (e.g.
      // a fetch-level network error that won the race against the abort).
      if (controller.signal.aborted) {
        if (overallTimedOut) emitOverallTimeout()
        return
      }

      attempt++
      if (attempt > maxRetries) {
        handlers.onError?.({ message: '网络连接失败，已重试多次仍无法恢复' })
        return
      }

      // Mark retry state + notify the UI BEFORE the backoff wait so the
      // "网络不稳，重连中 (n/max)" banner appears during the wait, not
      // only after it. Otherwise users sit on a blank bubble during the
      // (potentially multi-second) Retry-After / exponential backoff.
      state.isRetry = true
      handlers.onRetry?.(attempt, maxRetries)

      // Honor server-provided Retry-After when present (429/503 etc.).
      await _waitForRetry(attempt, baseDelay, controller.signal, result.retryAfterMs)
      if (controller.signal.aborted) {
        if (overallTimedOut) emitOverallTimeout()
        return
      }
    }
  } finally {
    if (overallTimer) clearTimeout(overallTimer)
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVisibilityChange)
    }
  }
}

/**
 * Single SSE fetch attempt. Returns status indicating whether to retry.
 *
 * Two-layer abort: the outer `userController` belongs to the caller (fired by
 * user cancel or wall-clock timeout); the inner `watchdogController` lives
 * for one attempt and fires when the idle watchdog trips. We forward outer
 * aborts to the inner signal so fetch listens to a single signal.
 */
async function _doFetchSSE(
  url: string,
  init: RequestInit,
  handlers: ChatEventHandlers,
  userController: AbortController,
  streamState: _StreamState,
  retryState: _RetryState,
): Promise<{
  completed: boolean
  nonRetryable: boolean
  retryAfterMs?: number | null
  /**
   * True when this attempt ended because `userController.signal` fired (user
   * cancel OR overall wall-clock timer). The outer loop uses this to decide
   * whether the abort was a "stop talking" or a "show timeout error" event,
   * since both look identical from inside this function.
   */
  abortedByUserSignal?: boolean
}> {
  const watchdogController = new AbortController()
  streamState.watchdogAbort = () => watchdogController.abort()
  // Reset per-attempt state so the first-chunk timeout applies after each retry.
  streamState.firstChunkReceived = false
  streamState.lastChunkAt = Date.now()

  // Forward user/overall aborts into the inner signal. AbortSignal.any would
  // be cleaner but isn't yet ubiquitous on mobile WebViews.
  const forwardAbort = () => watchdogController.abort()
  if (userController.signal.aborted) {
    watchdogController.abort()
  } else {
    userController.signal.addEventListener('abort', forwardAbort, { once: true })
  }

  // Discard the body-bound init.signal — we wire our own signal that races
  // user-cancel and watchdog-cancel together.
  const mergedInit: RequestInit = { ...init, signal: watchdogController.signal }

  let receivedDoneOrError = false

  try {
    const response = await fetch(url, mergedInit)

    if (!response.ok) {
      const text = await response.text()
      receivedDoneOrError = true
      const status = response.status
      const isRetryable = status >= 500 || status === 408 || status === 429
      const retryAfterMs = _parseRetryAfter(response.headers.get('Retry-After'))
      // Level reflects user-visible severity:
      //   * retryable (5xx/408/429) → ``warn`` because the next attempt
      //     may succeed; reserving ``error`` for the terminal give-up
      //     keeps the ``severity_text='error'`` count of otel_logs an
      //     accurate "actually failed turns" gauge instead of inflating
      //     it with every recoverable hiccup.
      //   * non-retryable (4xx other than 408/429) → ``error`` because
      //     the user will see ``onError`` immediately below.
      telemetry.track('message_send_failed', {
        channel_token: retryState.channelToken,
        conversation_external_id: retryState.conversationExternalId,
        request_id: retryState.requestId,
        client_message_id: retryState.clientMessageId,
        trace_id: retryState.traceId,
        level: isRetryable ? 'warn' : 'error',
        props: {
          http_status: status,
          retryable: isRetryable,
          error_excerpt: (text ?? '').slice(0, 200),
        },
      })
      // Only surface error to user when we've decided not to retry — otherwise
      // the next attempt may succeed silently.
      if (!isRetryable) {
        handlers.onError?.({ message: text || `HTTP ${status}` })
      }
      return { completed: false, nonRetryable: !isRetryable, retryAfterMs }
    }

    // Capture the server-issued trace_id once per attempt so all subsequent
    // telemetry events on this turn can join against backend logs by exact
    // match (the log-analyzer Skill's preferred path).
    const traceHeader = response.headers.get('X-Trace-Id')
    if (traceHeader && !retryState.traceId) {
      retryState.traceId = traceHeader
    }

    const reader = response.body?.getReader()
    if (!reader) {
      receivedDoneOrError = true
      handlers.onError?.({ message: 'No response body' })
      return { completed: false, nonRetryable: true }
    }

    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''
    let currentDataLines: string[] = []
    let currentEventId: string | null = null

    const dispatchBufferedEvent = () => {
      if (!currentEvent && currentDataLines.length === 0 && currentEventId === null) return

      const event = currentEvent
      const rawData = currentDataLines.join('\n')
      const eventId = currentEventId
      currentEvent = ''
      currentDataLines = []
      currentEventId = null

      if (!event) return

      // JSON.parse failures are tolerable — a flaky proxy can corrupt
      // a single frame; the retry path (or the next valid frame) covers
      // recovery. Swallowing them here keeps the connection alive.
      let data: unknown
      try {
        data = rawData ? JSON.parse(rawData) : {}
      } catch {
        return
      }

      // Critical ordering (sub-req 4): _dispatch happens BEFORE we touch
      // any state that influences the SDK's view of "did this frame
      // land". If a UI handler throws:
      //   - the exception bubbles out of _doFetchSSE's outer try/catch,
      //     which treats it as a transport-style failure and lets the
      //     retry loop fire from the un-advanced cursor — the server's
      //     buffer fast-path will then re-deliver the SAME frame on
      //     reconnect, giving the UI a real second chance.
      //   - we DO NOT mark `receivedDoneOrError` (the swallow-everything
      //     terminal-frame guard would otherwise short-circuit retry).
      //   - we DO NOT advance the resume cursor (a same-cmid retry would
      //     skip the failed frame in the buffer slice).
      _dispatch(event, data, handlers)
      if (event === 'done' || event === 'error') {
        receivedDoneOrError = true
      }
      if (eventId && _ROUND_EVENT_ID_RE.test(eventId)) {
        retryState.lastEventId = eventId
      }
    }

    while (true) {
      const idleMs = streamState.firstChunkReceived
        ? streamState.watchdog.chunk_idle_ms
        : streamState.watchdog.first_chunk_ms
      const { done, value } = await _readWithIdleTimeout(
        reader,
        idleMs,
        () => watchdogController.abort(),
        (firedIdleMs) => {
          telemetry.track('sse_idle_timeout', {
            channel_token: retryState.channelToken,
            conversation_external_id: retryState.conversationExternalId,
            request_id: retryState.requestId,
            client_message_id: retryState.clientMessageId,
            trace_id: retryState.traceId,
            level: 'warn',
            props: {
              phase: streamState.firstChunkReceived ? 'mid' : 'first',
              last_event_id: retryState.lastEventId ?? '',
            },
            metrics: {
              idle_ms: firedIdleMs,
              last_chunk_at_ms: streamState.lastChunkAt,
            },
          })
        },
      )
      if (done) {
        buffer += decoder.decode()
        break
      }

      // Mark progress for the visibility-change watcher and flip the first-
      // chunk flag so subsequent reads use the shorter inter-chunk timeout.
      streamState.lastChunkAt = Date.now()
      if (!streamState.firstChunkReceived && value && value.byteLength > 0) {
        streamState.firstChunkReceived = true
      }

      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        const normalizedLine = line.endsWith('\r') ? line.slice(0, -1) : line
        if (normalizedLine === '') {
          dispatchBufferedEvent()
        } else if (normalizedLine.startsWith('id:')) {
          currentEventId = normalizedLine.slice(3).trimStart()
        } else if (normalizedLine.startsWith('event:')) {
          currentEvent = normalizedLine.slice(6).trimStart()
        } else if (normalizedLine.startsWith('data:')) {
          currentDataLines.push(normalizedLine.slice(5).trimStart())
        }
      }
    }

    if (buffer) {
      const normalizedLine = buffer.endsWith('\r') ? buffer.slice(0, -1) : buffer
      if (normalizedLine.startsWith('id:')) {
        currentEventId = normalizedLine.slice(3).trimStart()
      } else if (normalizedLine.startsWith('event:')) {
        currentEvent = normalizedLine.slice(6).trimStart()
      } else if (normalizedLine.startsWith('data:')) {
        currentDataLines.push(normalizedLine.slice(5).trimStart())
      }
    }
    dispatchBufferedEvent()

    if (receivedDoneOrError) {
      return { completed: true, nonRetryable: false }
    }

    // Stream ended without done/error → unexpected disconnect, retryable
    return { completed: false, nonRetryable: false }
  } catch (err: unknown) {
    // Terminal-frame guard (sub-req 4): if `done` or `error` already
    // dispatched, the stream is logically complete. Anything thrown
    // here is just transport teardown noise — e.g. some servers close
    // the socket immediately after the final flush, which a slow client
    // observes as a network error on the next ``reader.read()``. Don't
    // count that as retryable: our cursor already points at ``done``,
    // so the buffer fast-path would either no-op (replay tail empty)
    // or, worse, the user gets a "网络不稳，重连中" banner on a turn
    // that already finished.
    if (receivedDoneOrError) {
      return { completed: true, nonRetryable: false }
    }
    if (err instanceof DOMException && err.name === 'AbortError') {
      // Distinguish user-cancel/overall-timeout from idle-watchdog. The
      // outer loop maps `abortedByUserSignal` + `overallTimedOut` to the
      // right onError message; here we just report which signal fired.
      if (userController.signal.aborted) {
        // ``sse_aborted`` is best-effort: we can't reliably tell user-cancel
        // from overall-timeout from this layer (the timeout fires the
        // ``sse_overall_timeout`` track separately), so we tag this as
        // ``user_signal`` and let post-mortem joins distinguish via the
        // overlapping timeout event.
        telemetry.track('sse_aborted', {
          channel_token: retryState.channelToken,
          conversation_external_id: retryState.conversationExternalId,
          request_id: retryState.requestId,
          client_message_id: retryState.clientMessageId,
          trace_id: retryState.traceId,
          level: 'warn',
          props: { reason: 'user_signal' },
        })
        return { completed: true, nonRetryable: true, abortedByUserSignal: true }
      }
      // Watchdog abort → treat as a recoverable network failure.
      return { completed: false, nonRetryable: false }
    }
    // Network error → retryable
    return { completed: false, nonRetryable: false }
  } finally {
    userController.signal.removeEventListener('abort', forwardAbort)
    streamState.watchdogAbort = null
  }
}

/**
 * Wait with exponential backoff. If offline, also waits for the `online` event
 * so we retry immediately when network recovers (instead of wasting backoff time).
 *
 * `retryAfterMs` (optional): when the server returned a `Retry-After` header
 * (typical for 429 / 503), use the larger of computed backoff and the hint.
 * Jitter is applied on top of the chosen base delay (online path only — the
 * offline path already has its own settling logic).
 */
function _waitForRetry(
  attempt: number,
  baseDelay: number,
  signal: AbortSignal,
  retryAfterMs?: number | null,
): Promise<void> {
  const exp = Math.min(baseDelay * Math.pow(2, attempt - 1), 10_000)
  const baseMs = retryAfterMs != null ? Math.max(exp, retryAfterMs) : exp
  // ±JITTER_RATIO uniform jitter prevents reconnect storms after mass outages.
  const jittered = baseMs * (1 - JITTER_RATIO + Math.random() * JITTER_RATIO * 2)
  const delay = Math.round(jittered)

  return new Promise<void>((resolve) => {
    if (signal.aborted) { resolve(); return }

    let timer: ReturnType<typeof setTimeout> | null = null
    let onlineHandler: (() => void) | null = null
    let abortHandler: (() => void) | null = null

    const cleanup = () => {
      if (timer) clearTimeout(timer)
      if (onlineHandler) window.removeEventListener('online', onlineHandler)
      if (abortHandler) signal.removeEventListener('abort', abortHandler)
    }

    abortHandler = () => { cleanup(); resolve() }
    signal.addEventListener('abort', abortHandler, { once: true })

    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      // Offline: wait for online event, then apply a short settling delay
      onlineHandler = () => {
        if (timer) clearTimeout(timer)
        timer = setTimeout(() => { cleanup(); resolve() }, Math.min(baseDelay, 1000))
      }
      window.addEventListener('online', onlineHandler, { once: true })

      // Safety cap: don't wait forever for network
      timer = setTimeout(() => { cleanup(); resolve() }, 30_000)
    } else {
      timer = setTimeout(() => { cleanup(); resolve() }, delay)
    }
  })
}

function _dispatch(
  event: string,
  data: unknown,
  handlers: ChatEventHandlers,
) {
  switch (event) {
    case 'conversation_created':
      handlers.onConversationCreated?.(data as ConversationCreatedEvent)
      break
    case 'round_start':
      handlers.onRoundStart?.(data as RoundStartEvent)
      break
    case 'thinking_delta':
      handlers.onThinkingDelta?.(data as ThinkingDeltaEvent)
      break
    case 'content_delta':
      handlers.onContentDelta?.(data as ContentDeltaEvent)
      break
    case 'tool_call':
      handlers.onToolCall?.(data as ToolCallEvent)
      break
    case 'tool_result':
      handlers.onToolResult?.(data as ToolResultEvent)
      break
    case 'llm_step_created':
      handlers.onLlmStepCreated?.(data as LlmStepCreatedEvent)
      break
    case 'assistant_reset':
      handlers.onAssistantReset?.(data as AssistantResetEvent)
      break
    case 'done':
      handlers.onDone?.(data as DoneEvent)
      break
    case 'error':
      handlers.onError?.(data as ChatErrorEvent)
      break
  }
}
