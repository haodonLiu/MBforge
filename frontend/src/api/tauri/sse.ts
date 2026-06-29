/** SSE (Server-Sent Events) client for real-time streaming from FastAPI backend. */

const API_BASE = 'http://127.0.0.1:18792'

export interface SSEEvent {
  type: string
  data: Record<string, unknown>
}

export function connectSSE(
  path: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Event) => void,
): () => void {
  const url = `${API_BASE}${path}`
  const es = new EventSource(url)
  es.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      onEvent({ type: data.event || data.type || 'message', data })
    } catch { onEvent({ type: 'raw', data: { text: event.data } }) }
  }
  es.onerror = (err) => { console.error('[SSE] Error:', err); onError?.(err) }
  return () => es.close()
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
