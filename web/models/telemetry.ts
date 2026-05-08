/**
 * Telemetry batch upload types — kept in lockstep with
 * ``server/app/schemas/telemetry.py``.
 *
 * The shape mirrors what the backend's ``TelemetryBatchRequest`` accepts so
 * a TS type error is the first signal of drift between FE and BE during
 * future schema changes.
 */

export type TelemetryLevel = 'info' | 'warn' | 'error'

/**
 * Shared metadata for the whole batch. Sent once per POST; the backend
 * fans it out across each event's ``log_attributes``. We deliberately
 * de-duplicate from Doubao's per-event ``common`` block (saves ~60-80%
 * payload bytes on a typical chat round).
 */
export type TelemetryCommon = {
  session_id: string
  device_id: string
  user_id?: string | null
  release?: string
  url?: string
  user_agent?: string
  network_type?: string | null
  viewport?: string
  sdk_name?: string
  sdk_version?: string
  /**
   * Rough wall-clock skew between client and server (ms). Sent so the
   * backend can correct timestamps on devices with bad clocks during
   * post-mortem timeline reconstruction.
   */
  ts_offset_ms?: number
}

/**
 * Single user-journey event.
 *
 * ``trace_id`` / ``conversation_external_id`` / ``request_id`` /
 * ``client_message_id`` are explicit (rather than buried inside
 * ``props``) because:
 *   1. They get bound to the matching backend log columns by the service
 *      layer's ``set_*()`` calls — this only works when the field name
 *      is canonical.
 *   2. log-analyzer Skill recipes filter on these directly.
 */
export type TelemetryEvent = {
  /** ASCII snake_case, ^[a-z][a-z0-9_]*$ — schema-enforced backend-side. */
  name: string
  /** Date.now() at emit. */
  ts: number
  /** Defaults to 'info' if omitted. */
  level?: TelemetryLevel
  trace_id?: string | null
  conversation_external_id?: string | null
  request_id?: string | null
  client_message_id?: string | null
  /**
   * Categorical / identity fields. Strings, numbers and booleans only —
   * they're flattened to ``props_<key>`` log attributes and stringified
   * by the backend, so nesting won't survive the round trip.
   */
  props?: Record<string, string | number | boolean> | null
  /** Numeric fields. Same flatten rule, prefixed ``metrics_<key>``. */
  metrics?: Record<string, number> | null
}

export type TelemetryBatch = {
  common: TelemetryCommon
  events: TelemetryEvent[]
}

export type TelemetryBatchResponse = {
  accepted: number
  /**
   * Number of events the backend trimmed (over-batch, over-prop-count,
   * or kill-switch). Useful for the SDK to log a ``console.warn`` and
   * back off its emit cadence.
   */
  dropped: number
}
