/** Agent session management + LLM env-config probe + post-process PDF reporting. */

import { EVT } from '../tauri-events'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

// ---- agent (session-based, per-conversation isolation) ----

export interface ChatMessage {
  role: string
  content: string
}

// ---- LLM env config (Settings UI editable with env precedence + link-status probe) ----

/**
 * Link status as reported by the Rust side after `test_llm_connection`.
 * Mirrors `LlmLinkStatus` in `src-tauri/src/commands/llm.rs`.
 */
export type LlmLinkStatus =
  | 'not_configured'
  | 'ok'
  | 'unreachable'
  | 'http_error'
  | 'auth_error'

/**
 * Editable view of the LLM env config + last probe result. The
 * Settings UI can edit these values; env vars still take precedence
 * at runtime. The actual `api_key` is never returned — only
 * `api_key_set` so the UI can show a warning.
 */
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
 * Initialize the agent subsystem. The LLM has no per-session override —
 * Settings UI edits the global LLM config (env vars take precedence).
 * `sidecarUrl` is still needed for long-term-memory and
 * skill-summarization calls.
 */
export async function agentInit(sidecarUrl: string): Promise<void> {
  await invokeWithError(
    () => invoke('agent_init', { sidecarUrl }),
    ErrorCode.TauriInvoke,
  )
}

/**
 * Read the current env-derived LLM config for display. Does not perform
 * a network probe.
 */
export async function getLlmEnvConfig(): Promise<LlmEnvStatus> {
  return invokeWithError(
    () => invoke<LlmEnvStatus>('get_llm_env_config'),
    ErrorCode.TauriInvoke,
  )
}

/**
 * Probe the configured LLM endpoint with a minimal request and report
 * the link status. This is what the Settings UI calls to populate the
 * "Link status" indicator.
 */
export async function testLlmConnection(): Promise<LlmEnvStatus> {
  return invokeWithError(
    () => invoke<LlmEnvStatus>('test_llm_connection'),
    ErrorCode.TauriInvoke,
  )
}

export async function agentCreateSession(sessionId: string, projectRoot?: string): Promise<void> {
  await invokeWithError(
    () => invoke('agent_create_session', { sessionId, projectRoot: projectRoot ?? null }),
    ErrorCode.TauriInvoke,
  )
}

export async function agentChat(sessionId: string, userInput: string): Promise<string> {
  return invokeWithError(
    () => invoke<string>('agent_chat', { sessionId, userInput }),
    ErrorCode.TauriInvoke,
  )
}

export type AgentStreamEvent = {
  session_id: string
  delta: string
  finish_reason: string | null
}

export async function agentChatStream(
  sessionId: string,
  userInput: string,
  onChunk: (delta: string) => void,
  onDone: () => void,
  onError: (error: string) => void,
): Promise<() => void> {
  // Set up listeners BEFORE invoking to avoid missing early events
  const unlistenChunk = listen<AgentStreamEvent>(EVT.AgentStreamChunk, (event) => {
    if (event.payload.session_id === sessionId) {
      onChunk(event.payload.delta)
      if (event.payload.finish_reason) {
        onDone()
      }
    }
  })

  const unlistenDone = listen<{ session_id: string }>(EVT.AgentStreamDone, (event) => {
    if (event.payload.session_id === sessionId) {
      onDone()
    }
  })

  // Start streaming (await so errors propagate to caller)
  try {
    await invokeWithError(
      () => invoke('agent_chat_stream', { sessionId, userInput }),
      ErrorCode.TauriInvoke,
    )
  } catch (err) {
    onError(err instanceof Error ? err.message : String(err))
  }

  return () => {
    unlistenChunk.then(fn => fn())
    unlistenDone.then(fn => fn())
  }
}

export async function agentSwitchProject(sessionId: string, projectRoot: string, projectName: string): Promise<void> {
  await invokeWithError(
    () => invoke('agent_switch_project', { sessionId, projectRoot, projectName }),
    ErrorCode.TauriInvoke,
  )
}

export async function agentClear(sessionId: string): Promise<void> {
  await invokeWithError(
    () => invoke('agent_clear', { sessionId }),
    ErrorCode.TauriInvoke,
  )
}

export async function agentDestroySession(sessionId: string): Promise<void> {
  await invokeWithError(
    () => invoke('agent_destroy_session', { sessionId }),
    ErrorCode.TauriInvoke,
  )
}

export async function agentGetHistory(sessionId: string): Promise<ChatMessage[]> {
  return invokeWithError(
    () => invoke<ChatMessage[]>('agent_get_history', { sessionId }),
    ErrorCode.TauriInvoke,
  )
}
