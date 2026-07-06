/** Event-name constants used by the frontend SSE/HTTP bridges.
 *
 * Names are kept as a frozen object so they can be referenced both as
 * `EVT.X` and as `TauriEventName` (for `typeof` narrowing). The string
 * values mirror what the FastAPI sidecar emits over SSE; any rename must
 * be matched on the backend in `src/mbforge/utils/constants.py` (or the
 * router that emits the event).
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
