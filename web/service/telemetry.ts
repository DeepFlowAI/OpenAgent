'use client'

/**
 * Frontend telemetry SDK (singleton).
 *
 * Buffers user-journey events in memory, flushes them in batches to
 * ``POST /v1/public/channels/{token}/telemetry/events``, and falls back
 * to ``localStorage`` when network/page-unload prevents an immediate
 * delivery. Events land in ``otel_logs`` via the existing OTel pipeline
 * — see ``develop/telemetry/数据库设计.md`` for the wire contract.
 *
 * Design priorities, in order:
 *   1. Never throw / never block the chat UI. Telemetry is best-effort.
 *   2. **No implicit global routing**. Every ``track()`` call carries the
 *      ``channel_token`` it belongs to. Queue, pending storage and
 *      replay are all keyed by token. Without this, a tab that visits
 *      channel A and then channel B would mis-route A's events to B's
 *      endpoint (and the backend would tag them with B's tenant/agent),
 *      which is far worse than dropping the events outright.
 *   3. Survive page navigation: ``pagehide`` triggers a best-effort
 *      final flush via ``navigator.sendBeacon`` so the last few events
 *      have a chance to ship. Beacon is fire-and-forget at the browser
 *      level — server-side rejection on unload is invisible to the
 *      SDK, so critical events should ride a normal idle/size-triggered
 *      flush instead of relying on unload.
 *   4. Survive transient network failures: failed batches are stashed
 *      in ``localStorage`` (keyed by their original token) and replayed
 *      to the SAME token on the next ``flush()``.
 *   5. Stay cheap: batch up to 20 events / 5s, drop quietly when the
 *      backend reports ``dropped > 0`` (signal: emit cadence too high).
 *
 * NON-goals:
 *   - Per-event ack semantics. The wire format is fire-and-forget.
 *   - Cross-tab coordination. Each tab has its own queue/session.
 *   - Encryption / authentication beyond the channel token. The
 *     endpoint is intentionally public.
 */

import type {
  TelemetryBatch,
  TelemetryCommon,
  TelemetryEvent,
  TelemetryBatchResponse,
} from '@/models/telemetry'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5001/api/'
const SDK_NAME = 'openagent-web'
const SDK_VERSION = '1.0.0'

// Queue size that triggers an immediate flush. Picked low enough that a
// typical chat round (~12 events) ships in 1-2 requests, high enough that
// idle pages aren't constantly POSTing for clicks-that-aren't-happening.
const FLUSH_BATCH_SIZE = 20
// Idle flush — even if the queue isn't full, ship the buffer this many
// ms after the last enqueue so events don't sit forever during a quiet
// period before page unload.
const FLUSH_IDLE_MS = 5_000
// Cap retained-batches in localStorage so a chronically offline client
// can't fill the storage budget. Picked at 5 batches × ~20 events × ~1KB
// = ~100 KB worst case, applied per-channel.
const MAX_PENDING_LOCALSTORAGE_BATCHES_PER_CHANNEL = 5
// Pending key shape: ``telemetry:pending:{token}:{ts}-{rand}``. The token
// segment is required so replay can target the original endpoint — see
// ``_parsePendingKey``. Channel tokens are generated as
// ``secrets.token_urlsafe(16)[:22]`` server-side and contain only base64url
// characters, so ``:`` is a safe separator.
const PENDING_KEY_PREFIX = 'telemetry:pending:'
const DEVICE_ID_KEY = 'telemetry:device_id'

// ─────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────

const _isBrowser = (): boolean => typeof window !== 'undefined'

function _safeUUID(): string {
  if (_isBrowser()) {
    const c = window.crypto as Crypto | undefined
    if (c && typeof c.randomUUID === 'function') return c.randomUUID()
    if (c && typeof c.getRandomValues === 'function') {
      const b = new Uint8Array(16)
      c.getRandomValues(b)
      b[6] = (b[6] & 0x0f) | 0x40
      b[8] = (b[8] & 0x3f) | 0x80
      const hex = Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('')
      return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
    }
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function _readPersistentDeviceId(): string {
  if (!_isBrowser()) return _safeUUID()
  try {
    const existing = window.localStorage.getItem(DEVICE_ID_KEY)
    if (existing) return existing
    const fresh = _safeUUID()
    window.localStorage.setItem(DEVICE_ID_KEY, fresh)
    return fresh
  } catch {
    // Private mode / quota exceeded: fall back to ephemeral.
    return _safeUUID()
  }
}

function _readNetworkType(): string | null {
  if (!_isBrowser()) return null
  // ``connection`` is non-standard but widely available on Chrome/Edge/Android.
  // Safari + Firefox return null — that's fine, we just lose the field there.
  const conn = (navigator as Navigator & {
    connection?: { effectiveType?: string }
  }).connection
  return conn?.effectiveType ?? null
}

/**
 * Stable common fields — captured once per page load. ``user_agent`` and
 * ``release`` don't change inside a tab; ``session_id`` / ``device_id``
 * uniquely identify the SDK lifetime so they're correct only when set
 * once.
 */
type StableCommon = Pick<
  TelemetryCommon,
  | 'session_id'
  | 'device_id'
  | 'release'
  | 'user_agent'
  | 'sdk_name'
  | 'sdk_version'
  | 'ts_offset_ms'
>

function _buildStableCommon(): StableCommon {
  return {
    session_id: _safeUUID(),
    device_id: _readPersistentDeviceId(),
    release: process.env.NEXT_PUBLIC_APP_VERSION || SDK_VERSION,
    user_agent: _isBrowser() ? navigator.userAgent : undefined,
    sdk_name: SDK_NAME,
    sdk_version: SDK_VERSION,
    ts_offset_ms: 0,
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Stream metrics collector — used by use-chat.ts to compute the aggregate
// metrics shipped on the ``sse_done`` event without polluting that file.
// ─────────────────────────────────────────────────────────────────────────

export type StreamFinishMetrics = {
  total_duration_ms: number
  chunk_count: number
  avg_chunk_idle_ms: number
  p95_chunk_idle_ms: number
  /** Number of inter-chunk gaps > 1000ms — a useful "user perceived
   *  stutter" proxy that doesn't require eyeballing the histogram. */
  lag_1s_count: number
}

export type StreamMetricsCollector = {
  recordChunk: () => void
  finish: () => StreamFinishMetrics
}

/**
 * Build a tiny metrics collector. The implementation is allocation-free
 * for the hot path (``recordChunk``) and only does math at the end. Kept
 * inside this module so use-chat.ts doesn't grow another concept.
 */
export function createStreamMetrics(): StreamMetricsCollector {
  const startedAt = Date.now()
  let lastChunkAt = startedAt
  let chunkCount = 0
  const idleGapsMs: number[] = []

  return {
    recordChunk() {
      const now = Date.now()
      const gap = now - lastChunkAt
      lastChunkAt = now
      chunkCount += 1
      idleGapsMs.push(gap)
    },
    finish(): StreamFinishMetrics {
      const total = Date.now() - startedAt
      const sum = idleGapsMs.reduce((a, b) => a + b, 0)
      const avg = idleGapsMs.length === 0 ? 0 : sum / idleGapsMs.length
      // Sort a copy — keep the original array intact for reuse (defensive,
      // even though ``finish`` is only called once in practice).
      const sorted = [...idleGapsMs].sort((a, b) => a - b)
      const p95Index =
        sorted.length === 0 ? 0 : Math.min(sorted.length - 1, Math.floor(sorted.length * 0.95))
      const p95 = sorted.length === 0 ? 0 : sorted[p95Index]
      const lag1s = idleGapsMs.filter((g) => g > 1000).length
      return {
        total_duration_ms: total,
        chunk_count: chunkCount,
        avg_chunk_idle_ms: Math.round(avg),
        p95_chunk_idle_ms: Math.round(p95),
        lag_1s_count: lag1s,
      }
    },
  }
}

// ─────────────────────────────────────────────────────────────────────────
// Telemetry singleton
// ─────────────────────────────────────────────────────────────────────────

/**
 * Per-call input. ``channel_token`` is the **only** routing input the SDK
 * uses — there is no global default. Callers from auth-only surfaces
 * (e.g. the admin Test Drawer) pass null/undefined to drop the event
 * cleanly; non-null binds the event to that exact channel and persists
 * the binding through queue, pending storage and replay.
 */
type TrackInput = Omit<TelemetryEvent, 'name' | 'ts'> & {
  ts?: number
  channel_token?: string | null
}

class TelemetryClient {
  // Stable identity / version fields — never re-read after constructor.
  // Dynamic fields (``url`` / ``viewport`` / ``network_type``) are
  // re-captured at every flush so a SPA route change between batches
  // doesn't ship the previous URL with the new events. See
  // ``_buildCommon()``.
  private readonly _stableCommon: StableCommon
  // Per-channel queues. Keyed by channel token so a tab that browses
  // channel A then channel B never mixes A's pending events into B's
  // upload — which would mis-tag tenant_id/agent_id at the backend.
  private readonly _queues = new Map<string, TelemetryEvent[]>()
  private _flushTimer: ReturnType<typeof setTimeout> | null = null
  /**
   * In-flight flush tracker. Multiple ``flush()`` calls in a single tick —
   * e.g. an idle-timer firing while ``track()`` also crosses
   * ``FLUSH_BATCH_SIZE`` — would otherwise both enter
   * ``_replayPersistedBatches()``, both read the same localStorage keys,
   * and both POST the persisted batches before either deletes them. The
   * net effect is duplicated events in otel_logs which silently inflates
   * interruption / latency rates. Joining concurrent calls to a single
   * promise eliminates that race without needing per-key locks.
   */
  private _flushPromise: Promise<void> | null = null
  private _enabled = true
  private _initializedListeners = false

  constructor() {
    this._stableCommon = _buildStableCommon()
    this._initListenersOnce()
  }

  /** Combine stable identity fields with a fresh snapshot of url /
   *  viewport / network_type. Called per flush so SPA navigations and
   *  network type changes inside a tab show up in subsequent batches.
   *  Per-event accuracy isn't needed: a single batch carries one
   *  ``common`` block, and ``track()`` only fires inside chat turns
   *  which all run on the same URL. */
  private _buildCommon(): TelemetryCommon {
    return {
      ...this._stableCommon,
      url: _isBrowser() ? window.location.href : undefined,
      viewport: _isBrowser()
        ? `${window.innerWidth}x${window.innerHeight}`
        : undefined,
      network_type: _readNetworkType(),
    }
  }

  /** Master switch. ``false`` makes ``track`` a no-op; queued events
   *  stay queued so a temporary pause doesn't lose pending data. */
  setEnabled(enabled: boolean): void {
    this._enabled = enabled
  }

  /**
   * Enqueue a single event scoped to ``input.channel_token``. Calls without
   * a channel token return silently — the SDK can't pick a route for them
   * so the only safe thing is to drop. Other errors are swallowed via
   * console.warn so a misconfigured SDK can never break a chat round.
   */
  track(name: string, input: TrackInput = {}): void {
    if (!this._enabled) return
    if (!_isBrowser()) return
    const token = input.channel_token ?? null
    if (!token) return
    try {
      const event: TelemetryEvent = {
        name,
        ts: input.ts ?? Date.now(),
        level: input.level ?? 'info',
        trace_id: input.trace_id ?? null,
        conversation_external_id: input.conversation_external_id ?? null,
        request_id: input.request_id ?? null,
        client_message_id: input.client_message_id ?? null,
        props: input.props ?? null,
        metrics: input.metrics ?? null,
      }
      let q = this._queues.get(token)
      if (!q) {
        q = []
        this._queues.set(token, q)
      }
      q.push(event)
      // Total queued across all channels — a single channel near the
      // batch size should still trigger a flush even when other channels
      // are quiet. Cheap because Map.size is O(1) and lengths are tiny.
      const totalSize = this._totalQueued()
      if (totalSize >= FLUSH_BATCH_SIZE) {
        void this.flush()
      } else {
        this._scheduleIdleFlush()
      }
    } catch (e) {
      console.warn('[telemetry] track failed', e)
    }
  }

  /** Force a flush across all channels. Re-entrant calls join the
   *  in-flight promise so persisted-batch replay never double-POSTs. */
  async flush(): Promise<void> {
    if (!_isBrowser()) return
    if (this._flushPromise) return this._flushPromise
    const p = this._doFlush()
    this._flushPromise = p
    try {
      await p
    } finally {
      this._flushPromise = null
    }
  }

  private async _doFlush(): Promise<void> {
    if (this._flushTimer) {
      clearTimeout(this._flushTimer)
      this._flushTimer = null
    }
    // Drain pending-from-disk first so the head-of-line replay rule is
    // preserved. Each pending key carries its own token, so this is
    // safe even when no in-memory queue exists for that channel.
    await this._replayPersistedBatches()
    // Loop drains until the queues are empty. ``track()`` calls during
    // any of the awaits below would otherwise sit in the queue until
    // the next idle timer / pagehide — without this loop, a chat round
    // that overlaps a flush would ship its first 20 events but stall
    // the rest until the user's next interaction. The bound here is
    // implicit: ``_send`` returns once per drained batch, and each
    // batch retires its events from the queue, so the loop terminates
    // as soon as no new events arrive between iterations. A pathological
    // attacker calling ``track()`` in a tight loop on the same tab
    // could keep us iterating, but they can already do that without
    // any flush concept — the safe upper bound is the queue size cap
    // imposed by the page lifecycle.
    while (this._totalQueued() > 0) {
      const drained = this._drainQueues()
      // Build one ``common`` per iteration: a SPA route change between
      // back-to-back batches gets the right URL on the second batch.
      for (const [token, events] of drained) {
        const batch: TelemetryBatch = { common: this._buildCommon(), events }
        await this._send(token, batch, /*useBeacon*/ false)
      }
    }
  }

  // ── Internal ────────────────────────────────────────────────────────

  private _totalQueued(): number {
    let n = 0
    for (const q of this._queues.values()) n += q.length
    return n
  }

  /** Snapshot every per-channel queue and clear them. Empty channels
   *  are not yielded. */
  private _drainQueues(): Array<[string, TelemetryEvent[]]> {
    const out: Array<[string, TelemetryEvent[]]> = []
    for (const [token, q] of this._queues) {
      if (q.length === 0) continue
      out.push([token, q.splice(0, q.length)])
    }
    return out
  }

  private _scheduleIdleFlush(): void {
    if (this._flushTimer) return
    this._flushTimer = setTimeout(() => {
      this._flushTimer = null
      void this.flush()
    }, FLUSH_IDLE_MS)
  }

  private _initListenersOnce(): void {
    if (!_isBrowser()) return
    if (this._initializedListeners) return
    this._initializedListeners = true

    // ``pagehide`` is the most reliable cross-browser hook for
    // "page is unloading"; ``visibilitychange→hidden`` is a useful
    // backup since iOS / some PWA contexts skip pagehide on tab kill.
    const finalFlush = () => this._flushOnUnload()
    window.addEventListener('pagehide', finalFlush)
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'hidden') finalFlush()
    })
  }

  private _flushOnUnload(): void {
    if (this._totalQueued() === 0) return
    // ``sendBeacon`` is best-effort: a ``true`` return only means the
    // browser accepted the request into its outgoing queue, not that
    // the server returned 2xx. If the server later rejects the batch
    // (400 / 422 / 5xx) we have no way to know and no chance to stash,
    // because the page has already gone away. That's an inherent
    // Beacon API limitation, not a bug — the consequence is that
    // events sent on unload trade reliability for "always tries". To
    // keep this exposure small, ``_scheduleIdleFlush`` and the size-
    // triggered flush in ``track()`` ship the buffer well before page
    // unload in normal use; only the trailing ~5s of events typically
    // ride the beacon path.
    //
    // We send one beacon per channel so each batch lands on the right
    // ``/public/channels/{token}/telemetry/events`` endpoint. Common
    // is rebuilt here too — pagehide is the most common SPA cleanup
    // path and the URL at unload time is what an analyst will search
    // for in otel_logs.
    const drained = this._drainQueues()
    const common = this._buildCommon()
    for (const [token, events] of drained) {
      const batch: TelemetryBatch = { common, events }
      void this._send(token, batch, /*useBeacon*/ true)
    }
  }

  private _endpointFor(token: string): string {
    return `${API_BASE}v1/public/channels/${encodeURIComponent(token)}/telemetry/events`
  }

  /** ``true`` for HTTP statuses where a later flush could plausibly
   *  succeed (transient overload, throttling, server-side error). 4xx
   *  excluding 408/429 are permanent rejections — the request shape or
   *  channel token is wrong, retrying would never succeed. Stashing
   *  permanent failures in localStorage would otherwise resurface them
   *  on every page load forever. */
  private _isStatusRetryable(status: number): boolean {
    return status === 408 || status === 429 || status >= 500
  }

  private async _send(
    token: string, batch: TelemetryBatch, useBeacon: boolean,
  ): Promise<void> {
    const url = this._endpointFor(token)
    const body = JSON.stringify(batch)

    if (useBeacon && typeof navigator !== 'undefined' && navigator.sendBeacon) {
      try {
        const blob = new Blob([body], { type: 'application/json' })
        const ok = navigator.sendBeacon(url, blob)
        if (ok) return
        // Beacon returned false: usually means the queue is full or the
        // payload is over the per-origin beacon cap (~64KB on most
        // browsers). Treat as transient and fall through to fetch — if
        // that fails we'll stash via the catch handler below.
      } catch {
        // Fall through to fetch.
      }
    }

    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body,
        // ``keepalive`` tells the browser the request may outlive the
        // current document — important for the case where flush() races
        // a navigation but pagehide hasn't fired yet.
        keepalive: true,
      })
      if (!resp.ok) {
        if (this._isStatusRetryable(resp.status)) {
          // Server hiccup — stash and retry on next flush / page load.
          this._stash(token, batch)
        } else {
          // Permanent rejection (400 oversized body, 404 revoked token,
          // 422 schema violation). Drop the batch on the floor; a future
          // attempt cannot turn this into a success and stashing would
          // make the SDK re-POST the same bad payload forever.
          console.warn(
            '[telemetry] dropping batch on permanent %d for %s (events=%d)',
            resp.status, token, batch.events.length,
          )
        }
        return
      }
      // Optional: log dropped > 0 so devtools shows backpressure hints.
      try {
        const data: TelemetryBatchResponse = await resp.json()
        if (data.dropped > 0) {
          console.warn('[telemetry] backend dropped %d events', data.dropped)
        }
      } catch {
        // body parse failure is harmless — the POST succeeded.
      }
    } catch (e) {
      // Network error: TypeError from fetch (offline, CORS, DNS). Always
      // transient, always stash.
      console.warn('[telemetry] flush network error', e)
      this._stash(token, batch)
    }
  }

  private _pendingKey(token: string): string {
    const rand = Math.random().toString(36).slice(2, 6)
    return `${PENDING_KEY_PREFIX}${token}:${Date.now()}-${rand}`
  }

  /** Returns the channel token a pending key belongs to, or ``null`` for
   *  malformed / pre-multichannel-format keys (those are skipped at
   *  replay time so a stale value can't ever be sent to a wrong
   *  endpoint). */
  private _parsePendingKey(key: string): { token: string } | null {
    if (!key.startsWith(PENDING_KEY_PREFIX)) return null
    const rest = key.slice(PENDING_KEY_PREFIX.length)
    const colonIdx = rest.indexOf(':')
    if (colonIdx <= 0) return null
    const token = rest.slice(0, colonIdx)
    if (!token) return null
    return { token }
  }

  private _stash(token: string, batch: TelemetryBatch): void {
    if (!_isBrowser()) return
    try {
      window.localStorage.setItem(this._pendingKey(token), JSON.stringify(batch))
      // Trim oldest pending batches when this channel is over budget.
      // Per-channel cap so a busy channel can't starve a quiet one.
      const sameChannelKeys: string[] = []
      for (let i = 0; i < window.localStorage.length; i++) {
        const k = window.localStorage.key(i)
        if (!k) continue
        const parsed = this._parsePendingKey(k)
        if (parsed && parsed.token === token) sameChannelKeys.push(k)
      }
      sameChannelKeys.sort()
      while (sameChannelKeys.length > MAX_PENDING_LOCALSTORAGE_BATCHES_PER_CHANNEL) {
        const oldest = sameChannelKeys.shift()
        if (oldest) window.localStorage.removeItem(oldest)
      }
    } catch {
      // Storage budget exhausted — drop on the floor. Telemetry must
      // never page the user.
    }
  }

  private async _replayPersistedBatches(): Promise<void> {
    if (!_isBrowser()) return
    let keys: string[] = []
    try {
      for (let i = 0; i < window.localStorage.length; i++) {
        const k = window.localStorage.key(i)
        if (k && k.startsWith(PENDING_KEY_PREFIX)) keys.push(k)
      }
    } catch {
      return
    }
    if (keys.length === 0) return
    keys.sort()
    // Track per-token replay-blocked flags so a permanently bad channel
    // (e.g. token deleted on the server) doesn't block other channels'
    // replay in the same pass.
    const blocked = new Set<string>()
    for (const key of keys) {
      const parsed = this._parsePendingKey(key)
      if (!parsed) {
        // Unknown / legacy key shape: delete so it doesn't stick around
        // forever. Silent because the only way these exist is from a
        // pre-multichannel build, which has no in-flight users today.
        try {
          window.localStorage.removeItem(key)
        } catch {
          /* ignore */
        }
        continue
      }
      if (blocked.has(parsed.token)) continue

      let raw: string | null = null
      try {
        raw = window.localStorage.getItem(key)
      } catch {
        continue
      }
      if (!raw) continue

      let batch: TelemetryBatch
      try {
        batch = JSON.parse(raw) as TelemetryBatch
      } catch {
        try {
          window.localStorage.removeItem(key)
        } catch {
          /* ignore */
        }
        continue
      }

      const url = this._endpointFor(parsed.token)
      const removeKey = () => {
        try {
          window.localStorage.removeItem(key)
        } catch {
          /* ignore */
        }
      }
      try {
        const resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(batch),
          keepalive: true,
        })
        if (resp.ok) {
          removeKey()
        } else if (!this._isStatusRetryable(resp.status)) {
          // Permanent rejection — drop the key so we don't keep
          // re-POSTing the same broken batch on every future page load.
          // Channel token revoked (404), schema bumped past compatibility
          // (422), oversized stash (400) all land here.
          console.warn(
            '[telemetry] dropping persisted batch on permanent %d for %s',
            resp.status, parsed.token,
          )
          removeKey()
        } else {
          // Transient (5xx / 408 / 429): keep the key, but stop
          // replaying this channel in the current pass so we don't
          // hammer it.
          blocked.add(parsed.token)
        }
      } catch {
        // Network still bad — block this channel in the current pass.
        blocked.add(parsed.token)
      }
    }
  }
}

// Module-level singleton. Constructed lazily on first import in the
// browser; SSR contexts get a no-op-ish instance because ``track`` checks
// ``_isBrowser()`` per call.
export const telemetry = new TelemetryClient()
