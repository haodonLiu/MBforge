/** Tauri IPC event names — must match `src-tauri/src/core/constants.rs`.
 *
 * Single source of truth for both Rust emitters and TS listeners.
 * Drift between the two silently breaks event delivery with no compile error,
 * so keep this file in sync with the Rust constants module.
 */

export const EVT = {
  DocProgress: 'doc-progress',
  DocResult: 'doc-result',
  SidecarLog: 'sidecar://log',
  SidecarStatus: 'sidecar://status',
  AgentStreamChunk: 'agent-stream-chunk',
  AgentStreamDone: 'agent-stream-done',
  KbSearchChunk: 'kb-search-chunk',
  ModelDownloadProgress: 'model-download-progress',
  IngestProgress: 'ingest-progress',
  IngestQueueUpdate: 'ingest-queue-update',
  IngestWorkerHeartbeat: 'ingest-worker-heartbeat',
  IngestEmbed: 'ingest-embed',
  IngestLog: 'ingest-log',
  OcrApiMissing: 'ocr-api-missing',
} as const

export type TauriEventName = (typeof EVT)[keyof typeof EVT]
