/** Agent session management + post-process PDF reporting via HTTP. */

import { httpPost, httpGet, httpPut, httpDelete, invokeWithError, API_BASE } from './_utils'
import { ErrorCode } from '@/utils/errors'

// ---- agent (session-based, per-conversation isolation) ----

export interface ChatMessage {
  role: string
  content: string
}

// ---- LLM env config (Settings UI editable with env precedence + link-status probe) ----

export type LlmLinkStatus =
  | 'not_configured'
  | 'ok'
  | 'unreachable'
  | 'http_error'
  | 'auth_error'

export interface LlmEnvStatus {
  provider: string
  base_url: string
  api_key_set: boolean
  model: string
  status: LlmLinkStatus
  error: string | null
  http_status: number | null
  latency_ms: number | null
}

/**
 * Initialize the agent subsystem.
 */
export async function agentInit(sidecarUrl: string): Promise<void> {
  await invokeWithError(
    () => httpPost('/api/v1/agent/init', { sidecar_url: sidecarUrl }),
    ErrorCode.Network,
  )
}

/**
 * Read the current env-derived LLM config for display.
 */
export async function getLlmEnvConfig(): Promise<LlmEnvStatus> {
  type LlmSettings = { provider?: string; base_url?: string; api_key?: string; model_name?: string }
  const resp = await invokeWithError(
    () => httpGet<{ success: boolean; settings?: { llm?: LlmSettings } }>('/api/v1/settings'),
    ErrorCode.Network,
  )
  const llm = resp.settings?.llm ?? {}
  return {
    provider: llm.provider ?? '',
    base_url: llm.base_url ?? '',
    api_key_set: Boolean(llm.api_key),
    model: llm.model_name ?? '',
    status: 'not_configured',
    error: null,
    http_status: null,
    latency_ms: null,
  }
}

/**
 * Probe the configured LLM endpoint with a minimal request.
 */
export async function testLlmConnection(): Promise<LlmEnvStatus> {
  const cfg = await getLlmEnvConfig()
  try {
    const start = Date.now()
    await httpGet<{ success: boolean }>('/api/v1/settings')
    return { ...cfg, status: 'ok', latency_ms: Date.now() - start }
  } catch (err) {
    return { ...cfg, status: 'unreachable', error: err instanceof Error ? err.message : String(err) }
  }
}

export async function agentCreateSession(sessionId: string, libraryRoot?: string): Promise<void> {
  await invokeWithError(
    () => httpPost('/api/v1/agent/session', { session_id: sessionId, library_root: libraryRoot ?? null }),
    ErrorCode.Network,
  )
}

export async function agentChat(sessionId: string, userInput: string): Promise<string> {
  const resp = await invokeWithError(
    () => httpPost<{ success: boolean; reply: string }>(
      `/api/v1/agent/session/${sessionId}/chat`,
      { user_input: userInput },
    ),
    ErrorCode.Network,
  )
  return resp.reply
}

export type AgentStreamEvent = {
  session_id: string
  delta: string
  finish_reason: string | null
}

function buildStreamUrl(sessionId: string, userInput: string): string {
  const params = new URLSearchParams({ user_input: userInput })
  return `${API_BASE}/agent/session/${sessionId}/chat/stream?${params}`
}

export function agentChatStream(
  sessionId: string,
  userInput: string,
  onChunk: (delta: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): Promise<() => void> {
  const url = buildStreamUrl(sessionId, userInput)
  const es = new EventSource(url)

  es.onmessage = (event: MessageEvent<string>) => {
    try {
      const data = JSON.parse(event.data) as Record<string, unknown>
      if (data.event === 'done') {
        onDone()
        es.close()
        return
      }
      if (typeof data.delta === 'string') {
        onChunk(data.delta)
      }
    } catch {
      onError(`Failed to parse SSE: ${event.data}`)
    }
  }

  es.onerror = () => {
    onError('SSE connection error')
    es.close()
  }

  return Promise.resolve(() => es.close())
}

export async function agentSwitchProject(sessionId: string, libraryRoot: string, _projectName: string): Promise<void> {
  await invokeWithError(
    () => httpPut(`/api/v1/agent/session/${sessionId}/project`, { library_root: libraryRoot }),
    ErrorCode.Network,
  )
}

export async function agentClear(sessionId: string): Promise<void> {
  await invokeWithError(
    () => httpPost(`/api/v1/agent/session/${sessionId}/clear`),
    ErrorCode.Network,
  )
}

export async function agentDestroySession(sessionId: string): Promise<void> {
  await invokeWithError(
    () => httpDelete(`/api/v1/agent/session/${sessionId}`),
    ErrorCode.Network,
  )
}

export async function agentGetHistory(sessionId: string): Promise<ChatMessage[]> {
  const resp = await invokeWithError(
    () => httpGet<{ success: boolean; messages: ChatMessage[] }>(
      `/api/v1/agent/session/${sessionId}/history`,
    ),
    ErrorCode.Network,
  )
  return resp.messages
}
