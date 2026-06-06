/** Agent session management + post-process PDF reporting. */

import { EVT } from '../tauri-events'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'
import type { PdfParseResult } from './pdf'

// ---- agent (session-based, per-conversation isolation) ----

export interface ChatMessage {
  role: string
  content: string
}

export async function agentInit(config: {
  provider: string
  base_url: string
  api_key: string
  model_name: string
  max_tokens: number
  temperature: number
  top_p: number
}, sidecarUrl: string): Promise<void> {
  await invokeWithError(
    () => invoke('agent_init', { config, sidecarUrl }),
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

export interface DocumentReport {
  metadata: DocumentMetadata
  compounds: CompoundEntry[]
  activities: ActivityEntry[]
  key_findings: FindingEntry[]
  sar_analysis: string
  uncertain_items: UncertainItem[]
  report_markdown: string
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

// ---- post_process ----

export interface CompoundEntry {
  name: string
  smiles: string | null
  category: string | null
  description: string
  source_ref: string
  confidence: string
  uncertainty_reason: string | null
}

export interface ActivityEntry {
  compound: string
  activity_type: string
  value: number
  units: string
  target: string | null
  source_quote: string
  source_ref: string
  confidence: string
  uncertainty_reason: string | null
}

export interface FindingEntry {
  finding: string
  evidence: string
  source_ref: string
  confidence: string
  uncertainty_reason: string | null
}

export interface UncertainItem {
  item_type: string
  content: string
  reason: string
  suggested_action: string
}

export interface DocumentMetadata {
  title: string | null
  authors: string[]
  document_type: string
  key_targets: string[]
  source_file: string | null
}

export interface StructuredData {
  metadata: DocumentMetadata
  summary: string
  compounds: CompoundEntry[]
  activities: ActivityEntry[]
  key_findings: FindingEntry[]
  uncertain_items: UncertainItem[]
}

export interface PostProcessResult {
  report: string
  data: StructuredData
  model: string
  tokens_used: number | null
  batch_count: number
}

export async function postProcessPdf(parseResult: PdfParseResult): Promise<PostProcessResult> {
  return invokeWithError(
    () => invoke<PostProcessResult>('post_process_pdf', { parseResult }),
    ErrorCode.PdfParse,
  )
}
