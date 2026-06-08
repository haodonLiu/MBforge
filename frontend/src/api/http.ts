export async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!resp.ok) {
    const text = await resp.text()
    throw new Error(`HTTP ${resp.status}: ${text}`)
  }
  return resp.json() as Promise<T>
}

export function sseStream<T>(
  url: string,
  body: unknown,
  onEvent: (event: T) => void,
  onError?: (error: string) => void,
): () => void {
  const controller = new AbortController()
  ;(async () => {
    try {
      const resp = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body != null ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })
      if (!resp.ok || !resp.body) {
        onError?.(`HTTP ${resp.status}`)
        return
      }
      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try { onEvent(JSON.parse(line.slice(6))) } catch { /* skip */ }
          }
        }
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        onError?.(String(e))
      }
    }
  })()
  return () => controller.abort()
}
