/** Ingest queue — 文档处理队列操作。 */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface IngestTask {
  id: string
  file_path: string
  doc_id: string
  status: 'pending' | 'processing' | 'done' | 'failed' | 'cancelled'
  stage: string
  progress_pct: number
  pages_total: number
  pages_done: number
  details: string
  retry_count: number
  max_retries: number
  error: string | null
  created_at: number
  updated_at: number
}

export interface QueueStats {
  total: number
  pending: number
  processing: number
  done: number
  failed: number
  cancelled: number
}

export interface IngestProgressEvent {
  doc_id: string
  stage: string
  progress_pct: number
  pages_done: number
  pages_total: number
  details: string
}

export interface IngestQueueUpdateEvent {
  doc_id: string
  stage: string
  stats: QueueStats
}

export async function ingestList(projectRoot: string): Promise<IngestTask[]> {
  return invokeWithError(
    () => invoke<IngestTask[]>('ingest_list', { projectRoot }),
    ErrorCode.TauriInvoke,
  )
}

export async function ingestStats(projectRoot: string): Promise<QueueStats> {
  return invokeWithError(
    () => invoke<QueueStats>('ingest_stats', { projectRoot }),
    ErrorCode.TauriInvoke,
  )
}

export async function ingestCancel(projectRoot: string, taskId: string): Promise<void> {
  return invokeWithError(
    () => invoke<void>('ingest_cancel', { projectRoot, taskId }),
    ErrorCode.TauriInvoke,
  )
}

export async function ingestRetry(projectRoot: string, taskId: string): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('ingest_retry', { projectRoot, taskId }),
    ErrorCode.TauriInvoke,
  )
}

export async function ingestCleanup(projectRoot: string): Promise<number> {
  return invokeWithError(
    () => invoke<number>('ingest_cleanup', { projectRoot }),
    ErrorCode.TauriInvoke,
  )
}
