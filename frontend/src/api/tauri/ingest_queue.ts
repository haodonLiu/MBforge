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
  file_size_bytes: number | null
  started_at: number | null
  created_at: number
  updated_at: number
  priority: number
}

export interface QueueStats {
  total: number
  pending: number
  processing: number
  done: number
  failed: number
  cancelled: number
  avg_stage_durations_ms: number[]
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

export interface IngestWorkerHeartbeatEvent {
  project_root: string
  ts: number
  alive: boolean
}

export interface IngestLogEvent {
  doc_id: string
  stage: string
  /** "info" | "warn" | "error" */
  level: string
  message: string
  /** Unix epoch milliseconds */
  ts_ms: number
}

/** Track C: 嵌入阶段子进度事件 */
export interface IngestEmbedEvent {
  doc_id: string
  action: 'start' | 'done' | 'failed' | 'skipped'
  model: string
  progress: number
  error?: string
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
    async () => {
      await invoke('ingest_cancel', { projectRoot, taskId })
    },
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

/** 手动将 PDF 加入处理队列。返回任务 ID。
 *
 * `force=true` 跳过同 hash 幂等检查 — 用于对已索引文件强制重新入队，
 * 新建任务而不复用现有 done 任务（保留历史记录）。
 */
export async function ingestEnqueue(
  projectRoot: string,
  filePath: string,
  docId: string,
  force?: boolean,
): Promise<string> {
  return invokeWithError(
    () => invoke<string>('ingest_enqueue', { projectRoot, filePath, docId, force: force ?? false }),
    ErrorCode.TauriInvoke,
  )
}

/** 当前会话内用户主动触发的 doc_id 集合，用于跨页 toast 去噪。 */
const selfTriggeredDocs = new Set<string>()

export function trackSelfTriggeredDoc(docId: string): void {
  selfTriggeredDocs.add(docId)
  // 避免集合无限增长：超过 100 时清理最旧的 50 个。
  if (selfTriggeredDocs.size > 100) {
    const iter = selfTriggeredDocs.values()
    for (let i = 0; i < 50; i++) {
      const value = iter.next().value
      if (value !== undefined) selfTriggeredDocs.delete(value)
    }
  }
}

export function isSelfTriggeredDoc(docId: string): boolean {
  return selfTriggeredDocs.has(docId)
}

export function removeSelfTriggeredDoc(docId: string): void {
  selfTriggeredDocs.delete(docId)
}

export async function ingestSetPriority(
  projectRoot: string,
  taskId: string,
  priority: number,
): Promise<void> {
  return invokeWithError(
    async () => {
      await invoke('ingest_set_priority', { projectRoot, taskId, priority })
    },
    ErrorCode.TauriInvoke,
  )
}

export async function ingestDeleteTask(
  projectRoot: string,
  taskId: string,
): Promise<boolean> {
  return invokeWithError(
    () => invoke<boolean>('ingest_delete_task', { projectRoot, taskId }),
    ErrorCode.TauriInvoke,
  )
}
