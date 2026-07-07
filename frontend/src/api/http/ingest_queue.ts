/** Ingest queue — 文档处理队列操作 via HTTP. */

import { httpPost, invokeWithError } from './_utils'
import { ErrorCode } from '@/utils/errors'

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
  /** 关联 task id（仅 DB 落库通道携带） */
  task_id?: string | null
}

/** DB 落库通道的日志行（与 IngestLogEvent 同构）。 */
export type IngestLogRecord = IngestLogEvent

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
    () => httpPost('/api/v1/pipeline/queue', { project_root: projectRoot })
      .then((r: any) => Array.isArray(r?.tasks) ? r.tasks : []),
    ErrorCode.TauriInvoke,
  )
}

export async function ingestStats(projectRoot: string): Promise<QueueStats> {
  return invokeWithError(
    () => httpPost('/api/v1/pipeline/queue/stats', { project_root: projectRoot })
      .then((r: any) => r?.stats ?? {}),
    ErrorCode.TauriInvoke,
  )
}

export async function ingestWorkerStatus(): Promise<{ status: string; ts: number }> {
  try {
    const resp = await httpGet<{ status: string; ts: number }>('/api/v1/pipeline/worker/status')
    return resp ?? { status: 'offline', ts: 0 }
  } catch {
    return { status: 'offline', ts: 0 }
  }
}

/** 获取某 doc_id 的最近 N 条 ingest 日志（DB 兜底通道）。
 *  默认 limit=500；可按需调小。 */
export async function ingestGetLogs(
  projectRoot: string,
  docId: string,
  limit?: number,
): Promise<IngestLogRecord[]> {
  return invokeWithError(
    () => httpPost<IngestLogRecord[]>('/api/v1/pipeline/queue/logs', {
      project_root: projectRoot,
      doc_id: docId,
      limit,
    }),
    ErrorCode.TauriInvoke,
  )
}

export async function ingestCancel(projectRoot: string, taskId: string): Promise<void> {
  return invokeWithError(
    async () => {
      await httpPost(`/api/v1/pipeline/queue/${taskId}/cancel`, { project_root: projectRoot })
    },
    ErrorCode.TauriInvoke,
  )
}

export async function ingestRetry(projectRoot: string, taskId: string): Promise<boolean> {
  return invokeWithError(
    () => httpPost<boolean>(`/api/v1/pipeline/queue/${taskId}/retry`, { project_root: projectRoot }),
    ErrorCode.TauriInvoke,
  )
}

export async function ingestCleanup(projectRoot: string): Promise<number> {
  return invokeWithError(
    () => httpPost<number>('/api/v1/pipeline/queue/cleanup', { project_root: projectRoot }),
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
    () => httpPost<string>('/api/v1/pipeline/enqueue', {
      project_root: projectRoot,
      file_path: filePath,
      doc_id: docId,
      force: force ?? false,
    }),
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
      await httpPost(`/api/v1/pipeline/queue/${taskId}/priority`, {
        project_root: projectRoot,
        priority,
      })
    },
    ErrorCode.TauriInvoke,
  )
}

export async function ingestDeleteTask(
  projectRoot: string,
  taskId: string,
): Promise<boolean> {
  return invokeWithError(
    () => httpPost<boolean>(`/api/v1/pipeline/queue/${taskId}/delete`, {
      project_root: projectRoot,
    }),
    ErrorCode.TauriInvoke,
  )
}
