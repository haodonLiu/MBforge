import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { listen } from '@tauri-apps/api/event'
import Button from '../ui/Button'
import ProgressBar from '../ui/ProgressBar'
import { XIcon } from '../icons/actions'
import { ChevronDownIcon, ChevronUpIcon } from '../icons/ui'
import PdfPipelineFlow from './pdf/PdfPipelineFlow'
import IngestLogPanel from './IngestLogPanel'
import { EVT } from '../../api/tauri-events'
import {
  ingestCancel,
  ingestCleanup,
  ingestDeleteTask,
  ingestList,
  ingestRetry,
  ingestSetPriority,
  ingestStats,
  type IngestTask,
  type IngestQueueUpdateEvent,
  type IngestWorkerHeartbeatEvent,
  type IngestLogEvent,
  type QueueStats,
} from '../../api/tauri/ingest_queue'
import { showToast } from '../../hooks/useToast'

interface Props {
  projectRoot: string
}

type StatusKey = IngestTask['status']
type FilterKey = 'all' | StatusKey

// Status display labels and accent colors.
const STATUS_LABEL: Record<StatusKey, string> = {
  pending: '待处理',
  processing: '处理中',
  done: '完成',
  failed: '失败',
  cancelled: '已取消',
}

// Sort priority: actionable first (processing > pending > failed),
// then non-actionable (cancelled > done).
const STATUS_RANK: Record<StatusKey, number> = {
  processing: 0,
  pending: 1,
  failed: 2,
  cancelled: 3,
  done: 4,
}

// Filter chip definitions — order matters (left-to-right scan).
const FILTERS: { key: FilterKey; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待处理' },
  { key: 'processing', label: '处理中' },
  { key: 'failed', label: '失败' },
  { key: 'cancelled', label: '已取消' },
  { key: 'done', label: '已完成' },
]

/** Format a millisecond delta as a compact Chinese duration (e.g. "2 分 15 秒"). */
function formatElapsed(ms: number): string {
  if (ms < 0 || !Number.isFinite(ms)) return '—'
  const totalSec = Math.floor(ms / 1000)
  if (totalSec < 60) return `${totalSec} 秒`
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  if (min < 60) return `${min} 分 ${sec} 秒`
  const hr = Math.floor(min / 60)
  const m = min % 60
  return `${hr} 时 ${m} 分`
}

/** Format bytes as human-readable size (e.g. "1.2 MB"). */
function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || bytes < 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

/** Estimate remaining milliseconds based on current progress and elapsed time. */
function estimateRemainingMs(elapsedMs: number, progressPct: number): number | null {
  if (progressPct <= 0 || progressPct >= 1 || elapsedMs <= 0) return null
  const rate = progressPct / elapsedMs // progress per ms
  const remainingProgress = 1 - progressPct
  return remainingProgress / rate
}

/** True if a task has been in 'processing' state for too long (potential hang). */
function isStale(task: IngestTask, now: number): boolean {
  if (task.status !== 'processing') return false
  return now - task.updated_at * 1000 > 5 * 60 * 1000
}

/** Return the basename of a file path. */
function basename(p: string): string {
  if (!p) return ''
  const parts = p.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] ?? p
}

export default function ProcessingQueue({ projectRoot }: Props) {
  const [tasks, setTasks] = useState<IngestTask[]>([])
  const [stats, setStats] = useState<QueueStats | null>(null)
  const [actionId, setActionId] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [hideDone, setHideDone] = useState(true)
  const [workerStatus, setWorkerStatus] = useState<'online' | 'offline' | 'unknown'>('unknown')
  const [lastHeartbeatTs, setLastHeartbeatTs] = useState<number | null>(null)
  const [logMap, setLogMap] = useState<Map<string, IngestLogEvent[]>>(new Map())
  const [expandedLogDocs, setExpandedLogDocs] = useState<Set<string>>(new Set())

  // Live "now" timestamp for elapsed-time displays. Only ticks every second
  // while there is at least one processing task — saves re-renders when the
  // queue is idle.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const hasProcessing = tasks.some((t) => t.status === 'processing')
    if (!hasProcessing) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [tasks])

  const load = useCallback(async () => {
    if (!projectRoot) return
    try {
      const [list, s] = await Promise.all([
        ingestList(projectRoot),
        ingestStats(projectRoot),
      ])
      setTasks(list)
      setStats(s)
    } catch (e) {
      console.error('[ProcessingQueue] load failed:', e)
    }
  }, [projectRoot])

  useEffect(() => {
    void load()
    let unlisten: (() => void) | null = null
    const setup = async () => {
      unlisten = await listen<IngestQueueUpdateEvent>(
        EVT.IngestQueueUpdate,
        () => {
          void load()
        },
      )
    }
    void setup().catch((e: unknown) => {
      console.error('[ProcessingQueue] listen failed:', e)
    })
    return () => {
      unlisten?.()
    }
  }, [load])

  // Worker heartbeat: update online status when a beat arrives.
  useEffect(() => {
    let unlisten: (() => void) | null = null
    const setup = async () => {
      unlisten = await listen<IngestWorkerHeartbeatEvent>(
        EVT.IngestWorkerHeartbeat,
        (event) => {
          setLastHeartbeatTs(event.payload.ts)
          setWorkerStatus('online')
        },
      )
    }
    void setup().catch((e: unknown) => {
      console.error('[ProcessingQueue] heartbeat listen failed:', e)
    })
    return () => {
      unlisten?.()
    }
  }, [])

  // Mark worker offline if no heartbeat is received for a while.
  useEffect(() => {
    if (lastHeartbeatTs == null) return
    const id = window.setInterval(() => {
      const elapsedMs = Date.now() - lastHeartbeatTs * 1000
      if (elapsedMs > 15_000) setWorkerStatus('offline')
    }, 1000)
    return () => window.clearInterval(id)
  }, [lastHeartbeatTs])

  // Subscribe to per-document ingest logs.
  useEffect(() => {
    let unlisten: (() => void) | null = null
    const setup = async () => {
      unlisten = await listen<IngestLogEvent>(EVT.IngestLog, (event) => {
        const payload = event.payload
        setLogMap((prev) => {
          const next = new Map(prev)
          const list = next.get(payload.doc_id) ?? []
          const updated = [...list, payload]
          if (updated.length > 200) updated.shift()
          next.set(payload.doc_id, updated)
          return next
        })
      })
    }
    void setup().catch((e: unknown) => {
      console.error('[ProcessingQueue] log listen failed:', e)
    })
    return () => {
      unlisten?.()
    }
  }, [])

  const handleCancel = useCallback(
    async (task: IngestTask) => {
      if (!projectRoot) return
      setActionId(task.id)
      try {
        await ingestCancel(projectRoot, task.id)
        showToast('已取消任务', 'success')
        await load()
      } catch (e) {
        console.error('[ProcessingQueue] cancel failed:', e)
        showToast('取消失败: ' + String(e), 'error')
      } finally {
        setActionId(null)
      }
    },
    [projectRoot, load],
  )

  const handleRetry = useCallback(
    async (task: IngestTask) => {
      if (!projectRoot) return
      setActionId(task.id)
      try {
        const ok = await ingestRetry(projectRoot, task.id)
        if (ok) {
          showToast('已重置任务，将重新处理', 'success')
        } else {
          showToast('任务重试次数已达上限', 'warning')
        }
        await load()
      } catch (e) {
        console.error('[ProcessingQueue] retry failed:', e)
        showToast('重试失败: ' + String(e), 'error')
      } finally {
        setActionId(null)
      }
    },
    [projectRoot, load],
  )

  const handleCleanup = useCallback(async () => {
    if (!projectRoot) return
    try {
      const removed = await ingestCleanup(projectRoot)
      showToast(`已清理 ${removed} 个完成任务`, 'success')
      await load()
    } catch (e) {
      console.error('[ProcessingQueue] cleanup failed:', e)
      showToast('清理失败: ' + String(e), 'error')
    }
  }, [projectRoot, load])

  const handleSetPriority = useCallback(
    async (task: IngestTask) => {
      if (!projectRoot) return
      setActionId(task.id)
      try {
        const nextPriority = task.priority > 0 ? 0 : 1
        await ingestSetPriority(projectRoot, task.id, nextPriority)
        showToast(nextPriority > 0 ? '已置顶任务' : '已取消置顶', 'success')
        await load()
      } catch (e) {
        console.error('[ProcessingQueue] set priority failed:', e)
        showToast('置顶失败: ' + String(e), 'error')
      } finally {
        setActionId(null)
      }
    },
    [projectRoot, load],
  )

  const handleDelete = useCallback(
    async (task: IngestTask) => {
      if (!projectRoot) return
      setActionId(task.id)
      try {
        const ok = await ingestDeleteTask(projectRoot, task.id)
        if (ok) {
          showToast('已删除任务', 'success')
        } else {
          showToast('只能删除已结束的任务', 'warning')
        }
        await load()
      } catch (e) {
        console.error('[ProcessingQueue] delete failed:', e)
        showToast('删除失败: ' + String(e), 'error')
      } finally {
        setActionId(null)
      }
    },
    [projectRoot, load],
  )

  const toggleLogs = useCallback((docId: string) => {
    setExpandedLogDocs((prev) => {
      const next = new Set(prev)
      if (next.has(docId)) next.delete(docId)
      else next.add(docId)
      return next
    })
  }, [])

  // Filter + sort — memoized so the list doesn't re-sort on every keystroke
  // elsewhere. Sort priority: processing → pending → failed → cancelled → done.
  const visibleTasks = useMemo(() => {
    let xs = tasks
    if (filter !== 'all') xs = xs.filter((t) => t.status === filter)
    if (hideDone && filter === 'all') xs = xs.filter((t) => t.status !== 'done')
    return [...xs].sort((a, b) => {
      const r = STATUS_RANK[a.status] - STATUS_RANK[b.status]
      if (r !== 0) return r
      return b.created_at - a.created_at
    })
  }, [tasks, filter, hideDone])

  // Per-filter counts for chip badges.
  const counts = useMemo(() => {
    const c: Record<FilterKey, number> = {
      all: tasks.length,
      pending: 0,
      processing: 0,
      done: 0,
      failed: 0,
      cancelled: 0,
    }
    for (const t of tasks) c[t.status]++
    return c
  }, [tasks])

  return (
    <div className="processing-queue">
      {/* ----- Sticky header ----- */}
      <div className="processing-queue-header">
        <span className="processing-queue-title">处理队列</span>
        <span
          className={`processing-queue-worker-status is-${workerStatus}`}
          title={
            workerStatus === 'online'
              ? 'Worker 心跳正常'
              : workerStatus === 'offline'
                ? 'Worker 心跳超时，可能已停止'
                : '等待 worker 心跳'
          }
        >
          {workerStatus === 'online'
            ? '● worker 在线'
            : workerStatus === 'offline'
              ? '● worker 离线'
              : '○ worker 未连接'}
        </span>

        {stats && (
          <div className="processing-queue-stats" aria-label="队列统计">
            <span className="processing-queue-stat">
              <span>总计</span>
              <span className="num">{stats.total}</span>
            </span>
            {stats.processing > 0 && (
              <span className="processing-queue-stat is-processing">
                <span>处理中</span>
                <span className="num">{stats.processing}</span>
              </span>
            )}
            {stats.pending > 0 && (
              <span className="processing-queue-stat is-pending">
                <span>待处理</span>
                <span className="num">{stats.pending}</span>
              </span>
            )}
            {stats.failed > 0 && (
              <span className="processing-queue-stat is-failed">
                <span>失败</span>
                <span className="num">{stats.failed}</span>
              </span>
            )}
            {stats.done > 0 && (
              <span className="processing-queue-stat is-done">
                <span>完成</span>
                <span className="num">{stats.done}</span>
              </span>
            )}
            {stats.cancelled > 0 && (
              <span className="processing-queue-stat is-cancelled">
                <span>已取消</span>
                <span className="num">{stats.cancelled}</span>
              </span>
            )}
            {(() => {
              const avgTotalMs = stats.avg_stage_durations_ms.reduce((a, b) => a + b, 0)
              return avgTotalMs > 0 ? (
                <span
                  className="processing-queue-stat is-throughput"
                  title="近 5 个完成任务的各阶段平均耗时之和"
                >
                  <span>近 5 篇</span>
                  <span className="num">平均 {formatElapsed(avgTotalMs)}/篇</span>
                </span>
              ) : null
            })()}
          </div>
        )}

        <div className="processing-queue-header-actions">
          <label
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: '0.8rem',
              color: 'var(--text-soft)',
              cursor: 'pointer',
            }}
          >
            <input
              type="checkbox"
              checked={hideDone}
              onChange={(e) => setHideDone(e.target.checked)}
              style={{ accentColor: 'var(--accent)' }}
            />
            隐藏已完成
          </label>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleCleanup}
            disabled={!stats || stats.done === 0}
          >
            清理已完成
          </Button>
        </div>
      </div>

      {/* ----- Filter chips ----- */}
      <div className="processing-queue-filters" role="tablist" aria-label="状态筛选">
        {FILTERS.map((f) => {
          const isActive = filter === f.key
          const count = counts[f.key]
          return (
            <button
              key={f.key}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`processing-queue-chip${isActive ? ' is-active' : ''}`}
              onClick={() => setFilter(f.key)}
            >
              <span>{f.label}</span>
              <span className="num">{count}</span>
            </button>
          )
        })}
      </div>

      {/* ----- Task list ----- */}
      {visibleTasks.length === 0 ? (
        <div className="processing-queue-empty">
          <div>
            <div className="processing-queue-empty-title">
              {tasks.length === 0 ? '队列空闲' : '当前筛选下无任务'}
            </div>
            <div className="processing-queue-empty-hint">
              {tasks.length === 0
                ? '导入文档或启用「自动入队」开关后，处理任务会出现在这里。'
                : '切换上方筛选，或关闭「隐藏已完成」查看历史任务。'}
            </div>
          </div>
        </div>
      ) : (
        <motion.div
          className="processing-queue-list"
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.02 } } }}
        >
          {visibleTasks.map((task) => {
            const canCancel =
              task.status === 'pending' || task.status === 'processing'
            const canRetry = task.status === 'failed'
            const canDelete = task.status === 'cancelled' || task.status === 'done' || task.status === 'failed'
            const canSetPriority = task.status === 'pending'
            const fileName = basename(task.file_path)
            const createdAtMs = task.created_at * 1000
            const startedAtMs = task.started_at ? task.started_at * 1000 : null
            const startTimeMs = startedAtMs ?? createdAtMs
            const elapsedMs = now - startTimeMs
            const showElapsed = task.status !== 'done' && task.status !== 'cancelled'
            const stale = isStale(task, now)
            const showPages =
              task.pages_total > 0 &&
              (task.status === 'processing' || task.status === 'failed')
            const etaMs =
              task.status === 'processing'
                ? estimateRemainingMs(now - (startedAtMs ?? createdAtMs), task.progress_pct)
                : null

            return (
              <motion.div
                key={task.id}
                variants={{
                  hidden: { opacity: 0, y: 4 },
                  visible: { opacity: 1, y: 0 },
                }}
                transition={{ duration: 0.2 }}
                className={`processing-queue-item is-${task.status}`}
              >
                {/* Top row: filename + doc_id on left, status + actions on right */}
                <div className="processing-queue-item-top">
                  <div className="processing-queue-item-info">
                    <div
                      className="processing-queue-item-title"
                      title={task.file_path || task.doc_id}
                    >
                      {fileName || task.doc_id}
                      <span className="doc-id">{task.doc_id}</span>
                      {task.file_size_bytes != null && (
                        <span className="processing-queue-item-size">
                          {formatBytes(task.file_size_bytes)}
                        </span>
                      )}
                    </div>
                    <div className="processing-queue-item-meta">
                      <span
                        className={`processing-queue-status-badge is-${task.status}`}
                      >
                        {STATUS_LABEL[task.status]}
                      </span>
                      <PdfPipelineFlow variant="compact" task={task} />
                      {showPages && (
                        <span className="processing-queue-item-pages">
                          {task.pages_done}/{task.pages_total} 页
                        </span>
                      )}
                      {showElapsed && (
                        <span
                          className={
                            'processing-queue-item-elapsed' +
                            (stale ? ' is-slow' : '')
                          }
                          title={
                            stale
                              ? '该任务在「处理中」停留过久，可能卡住'
                              : startedAtMs
                                ? '自任务开始处理起经过时间'
                                : '自任务创建起经过时间'
                          }
                        >
                          ⏱ {formatElapsed(elapsedMs)}
                        </span>
                      )}
                      {etaMs != null && (
                        <span
                          className="processing-queue-item-eta"
                          title="基于当前速度和进度估算的剩余时间"
                        >
                          预计还需 {formatElapsed(etaMs)}
                        </span>
                      )}
                      {task.retry_count > 0 && (
                        <span className="processing-queue-retry-info">
                          重试 {task.retry_count}/{task.max_retries}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="processing-queue-item-actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleLogs(task.doc_id)}
                      aria-label={expandedLogDocs.has(task.doc_id) ? '隐藏日志' : '显示日志'}
                      title={expandedLogDocs.has(task.doc_id) ? '隐藏日志' : '显示日志'}
                    >
                      {expandedLogDocs.has(task.doc_id) ? <ChevronUpIcon size={16} /> : <ChevronDownIcon size={16} />}
                    </Button>
                    {canCancel && (
                      <Button
                        variant="ghost"
                        size="sm"
                        loading={actionId === task.id}
                        onClick={() => handleCancel(task)}
                      >
                        取消
                      </Button>
                    )}
                    {canRetry && (
                      <Button
                        variant="secondary"
                        size="sm"
                        loading={actionId === task.id}
                        onClick={() => handleRetry(task)}
                      >
                        重试
                      </Button>
                    )}
                    {canSetPriority && (
                      <Button
                        variant="ghost"
                        size="sm"
                        loading={actionId === task.id}
                        onClick={() => handleSetPriority(task)}
                        title={task.priority > 0 ? '取消置顶' : '置顶任务'}
                      >
                        {task.priority > 0 ? '取消置顶' : '置顶'}
                      </Button>
                    )}
                    {canDelete && (
                      <Button
                        variant="ghost"
                        size="sm"
                        loading={actionId === task.id}
                        onClick={() => handleDelete(task)}
                      >
                        删除
                      </Button>
                    )}
                  </div>
                </div>

                {/* Progress (only when actively progressing) */}
                {(task.status === 'pending' || task.status === 'processing') && (
                  <div className="processing-queue-progress">
                    <ProgressBar
                      value={task.progress_pct}
                      showPercent={task.status === 'processing'}
                    />
                    {task.details && (
                      <span className="processing-queue-progress-detail">
                        {task.details}
                      </span>
                    )}
                  </div>
                )}

                {/* Error block (failed only) */}
                {task.status === 'failed' && task.error && (
                  <div className="processing-queue-error">
                    <XIcon size={12} />
                    {task.error}
                  </div>
                )}

                {/* Expandable log panel */}
                {expandedLogDocs.has(task.doc_id) && (
                  <div className="processing-queue-log-panel">
                    <IngestLogPanel logs={logMap.get(task.doc_id) ?? []} />
                  </div>
                )}
              </motion.div>
            )
          })}
        </motion.div>
      )}
    </div>
  )
}
