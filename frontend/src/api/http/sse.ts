/** SSE (Server-Sent Events) client for real-time streaming from FastAPI backend. */

const API_BASE = 'http://127.0.0.1:18792'

export interface SSEEvent {
  type: string
  data: Record<string, unknown>
}

export interface ConnectSSEOptions {
  /** Maximum consecutive reconnect attempts before giving up. Default: 5. */
  maxRetries?: number
  /** Initial backoff in milliseconds; doubled each subsequent retry. Default: 1000. */
  baseDelayMs?: number
  /** Optional hook fired on each reconnect attempt (useful for UI status). */
  onRetry?: (attempt: number, delayMs: number) => void
}

/**
 * Connect to a server-sent-events endpoint and stream events to `onEvent`.
 *
 * Built-in exponential reconnect: when the EventSource closes or hits an
 * `onerror`, the client waits `baseDelayMs * 2^attempt` (capped at 30 s) and
 * reopens. After `maxRetries` failed attempts the connection is reported to
 * `onError` once and the returned cleanup function becomes a no-op.
 *
 * Why this exists: a flaky loopback mid-stream used to silently truncate
 * agent chat answers (TODO R-5). The backoff keeps transient drops
 * survivable while bounded so we don't thrash.
 */
export function connectSSE(
  path: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Event) => void,
  options: ConnectSSEOptions = {},
): () => void {
  const maxRetries = options.maxRetries ?? 5
  const baseDelayMs = options.baseDelayMs ?? 1000
  const MAX_DELAY_MS = 30_000

  let attempt = 0
  let es: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let disposed = false
  let gaveUp = false

  function open() {
    if (disposed || gaveUp) return
    const url = `${API_BASE}${path}`
    es = new EventSource(url)
    es.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onEvent({ type: data.event || data.type || 'message', data })
      } catch {
        onEvent({ type: 'raw', data: { text: event.data } })
      }
    }
    es.onerror = (err) => {
      console.error('[SSE] Error:', err)
      // EventSource auto-retries at the browser level, but we layer our own
      // backoff + cap on top so an offline backend doesn't loop forever.
      if (disposed) return
      if (attempt >= maxRetries) {
        gaveUp = true
        es?.close()
        onError?.(err)
        return
      }
      const delay = Math.min(MAX_DELAY_MS, baseDelayMs * 2 ** attempt)
      attempt += 1
      options.onRetry?.(attempt, delay)
      es?.close()
      es = null
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        open()
      }, delay)
    }
  }

  open()

  return () => {
    disposed = true
    if (reconnectTimer != null) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    es?.close()
    es = null
  }
}

export async function fetchSSE<T = unknown>(path: string, params?: Record<string, string>): Promise<T[]> {
  const url = new URL(`${API_BASE}${path}`)
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v))
  const resp = await fetch(url.toString())
  if (!resp.ok) throw new Error(`SSE fetch failed: ${resp.status}`)
  const reader = resp.body?.getReader()
  if (!reader) return []
  const decoder = new TextDecoder()
  const events: T[] = []
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const data = JSON.parse(line.slice(6))
          if (data.type === 'done' || data.event === 'done') break
          events.push(data as T)
        } catch {}
      }
    }
  }
  return events
}
