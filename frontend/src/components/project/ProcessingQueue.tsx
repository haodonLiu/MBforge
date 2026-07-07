import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import PageContainer from '../ui/PageContainer'
import Button from '../ui/Button'
import IconButton from '../ui/IconButton'
import Badge from '../ui/Badge'
import Switch from '../ui/Switch'
import ProgressBar from '../ui/ProgressBar'
import EmptyState from '../ui/EmptyState'
import { ChevronDownIcon, ChevronUpIcon, QueueIcon } from '../icons/ui'
import { XIcon, PinIcon, UnpinIcon, TrashIcon, RefreshCwIcon } from '../icons/actions'
import PdfPipelineFlow from './pdf/PdfPipelineFlow'
import IngestLogPanel from './IngestLogPanel'
import {
  ingestCancel,
  ingestCleanup,
  ingestDeleteTask,
  ingestGetLogs,
  ingestList,
  ingestRetry,
  ingestSetPriority,
  ingestStats,
  type IngestTask,
  type QueueStats,
} from '../../api/http/ingest_queue'
import { showToast } from '../../hooks/useToast'

import { useAppContext } from '../../context/AppContext'

type StatusKey = IngestTask['status']
type FilterKey = 'all' | StatusKey

// Sort priority: actionable first (processing > pending > failed),
// then non-actionable (cancelled > done).
const STATUS_RANK: Record<StatusKey, number> = {
  processing: 0,
  pending: 1,
  failed: 2,
  cancelled: 3,
  done: 4,
}

/** Map queue status to Badge tone. */
const STATUS_TONE: Record<StatusKey, 'info' | 'warning' | 'success' | 'danger' | 'neutral'> = {
  processing: 'info',
  pending: 'warning',
  done: 'success',
  failed: 'danger',
  cancelled: 'neutral',
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

/** Format elapsed milliseconds as "1m 23s" / "12s" / "2h 3m". */
function formatElapsed(ms: number): string {
  if (ms < 0 || !Number.isFinite(ms)) return '—'
  const totalSec = Math.floor(ms / 1000)
  if (totalSec < 60) return `${totalSec}s`
  const min = Math.floor(totalSec / 60)
  const sec = totalSec % 60
  if (min < 60) return `${min}m ${sec}s`
  const hr = Math.floor(min / 60)
  const m = min % 60
  return `${hr}h ${m}m`
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

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ProcessingQueue() {
  const { libraryRoot } = useAppContext()
  const [tasks, setTasks] = useState<IngestTask[]>([])

  const FILTERS: { key: FilterKey; label: string }[] = useMemo(() => [
    { key: 'all', label: t('queue.all') },
    { key: 'pending', label: t('queue.pending') },
    { key: 'processing', label: t('queue.processing') },
    { key: 'failed', label: t('queue.failed') },
    { key: 'cancelled', label: t('queue.cancelled') },
    { key: 'done', label: t('queue.done') },
  ], [t])

  const [stats, setStats] = useState<QueueStats | null>(null)
  const [actionId, setActionId] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [hideDone, setHideDone] = useState(true)
  const [workerStatus, setWorkerStatus] = useState<'online' | 'offline' | 'unknown'>('unknown')
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
    if (!libraryRoot) return
    try {
      const [list, s] = await Promise.all([
        ingestList(libraryRoot),
        ingestStats(libraryRoot),
      ])
      setTasks(list)
      setStats(s)
    } catch (e) {
      console.error('[ProcessingQueue] load failed:', e)
    }
  }, [libraryRoot])

  useEffect(() => {
    void load()
    // Web mode: poll instead of Tauri IPC listen
    const timer = setInterval(() => void load(), 10000)
    return () => {
      clearInterval(timer)
    }
  }, [load])

  // Worker status: poll backend API.
  useEffect(() => {
    const checkWorker = async () => {
      try {
        const resp = await fetch('http://127.0.0.1:18792/api/v1/pipeline/worker/status')
        if (resp.ok) {
          setWorkerStatus('online')
        } else {
          setWorkerStatus('offline')
        }
      } catch {
        setWorkerStatus('offline')
      }
    }
    void checkWorker()
    const timer = setInterval(checkWorker, 30000)
    return () => clearInterval(timer)
  }, [])

  // Subscribe to per-document ingest logs.
  // Web mode: no Tauri IPC — logs are fetched on demand via fetchLogsForDoc.

  // Subscribe to per-document ingest logs.
  // Web mode: no Tauri IPC — logs are fetched on demand via fetchLogsForDoc.
  useEffect(() => {
    // No-op in web mode
  }, [])

  /** DB 兜底通道：从 SQLite 拉取该 doc 的历史日志。 */
  const fetchLogsForDoc = useCallback(
    async (docId: string) => {
      try {
        const records = await ingestGetLogs(libraryRoot, docId, 500)
        if (records.length === 0) return
        setLogMap((prev) => {
          const list = prev.get(docId) ?? []
          // 合并 + 去重（ts_ms + message 复合键）
          const seen = new Set(list.map((e) => `${e.ts_ms}::${e.message}`))
          const merged = [...list]
          for (const r of records) {
            const key = `${r.ts_ms}::${r.message}`
            if (!seen.has(key)) {
              seen.add(key)
              merged.push(r)
            }
          }
          merged.sort((a, b) => a.ts_ms - b.ts_ms)
          const trimmed = merged.length > 200 ? merged.slice(-200) : merged
          const next = new Map(prev)
          next.set(docId, trimmed)
          return next
        })
      } catch (e) {
        console.error('[ProcessingQueue] fetchLogsForDoc failed:', e)
      }
    },
    [libraryRoot],
  )

  /** 任务列表加载完后，对每个 doc 预拉一次历史日志（覆盖早期事件丢失场景）。 */
  useEffect(() => {
    if (!libraryRoot) return
    const docIds = new Set(tasks.map((t) => t.doc_id))
    for (const docId of docIds) {
      void fetchLogsForDoc(docId)
    }
    // 只在 tasks 变化时拉取（数量或成员变化）
  }, [libraryRoot, tasks, fetchLogsForDoc])

  const handleCancel = useCallback(
    async (task: IngestTask) => {
      if (!libraryRoot) return
      setActionId(task.id)
      try {
        await ingestCancel(libraryRoot, task.id)
        showToast(t('queue.taskCancelled'), 'success')
        await load()
      } catch (e) {
        console.error('[ProcessingQueue] cancel failed:', e)
        showToast(t('queue.cancelFailed', { error: String(e) }), 'error')
      } finally {
        setActionId(null)
      }
    },
    [libraryRoot, load, t],
  )

  const handleRetry = useCallback(
    async (task: IngestTask) => {
      if (!libraryRoot) return
      setActionId(task.id)
      try {
        const ok = await ingestRetry(libraryRoot, task.id)
        if (ok) {
          showToast(t('queue.taskRetried'), 'success')
        } else {
          showToast(t('queue.retryLimitReached'), 'warning')
        }
        await load()
      } catch (e) {
        console.error('[ProcessingQueue] retry failed:', e)
        showToast(t('queue.retryFailed', { error: String(e) }), 'error')
      } finally {
        setActionId(null)
      }
    },
    [libraryRoot, load, t],
  )

  const handleCleanup = useCallback(async () => {
    if (!libraryRoot) return
    try {
      const removed = await ingestCleanup(libraryRoot)
      showToast(t('queue.cleanedUp', { count: removed }), 'success')
      await load()
    } catch (e) {
      console.error('[ProcessingQueue] cleanup failed:', e)
      showToast(t('queue.cleanupFailed', { error: String(e) }), 'error')
    }
  }, [libraryRoot, load, t])

  const handleSetPriority = useCallback(
    async (task: IngestTask) => {
      if (!libraryRoot) return
      setActionId(task.id)
      try {
        const nextPriority = task.priority > 0 ? 0 : 1
        await ingestSetPriority(libraryRoot, task.id, nextPriority)
        showToast(nextPriority > 0 ? t('queue.taskPinned') : t('queue.taskUnpinned'), 'success')
        await load()
      } catch (e) {
        console.error('[ProcessingQueue] set priority failed:', e)
        showToast(t('queue.pinFailed', { error: String(e) }), 'error')
      } finally {
        setActionId(null)
      }
    },
    [libraryRoot, load, t],
  )

  const handleDelete = useCallback(
    async (task: IngestTask) => {
      if (!libraryRoot) return
      setActionId(task.id)
      try {
        const ok = await ingestDeleteTask(libraryRoot, task.id)
        if (ok) {
          showToast(t('queue.taskDeleted'), 'success')
        } else {
          showToast(t('queue.canOnlyDeleteFinished'), 'warning')
        }
        await load()
      } catch (e) {
        console.error('[ProcessingQueue] delete failed:', e)
        showToast(t('queue.deleteFailed', { error: String(e) }), 'error')
      } finally {
        setActionId(null)
      }
    },
    [libraryRoot, load, t],
  )

  const toggleLogs = useCallback(
    (docId: string) => {
      let willExpand = false
      setExpandedLogDocs((prev) => {
        willExpand = !prev.has(docId)
        const next = new Set(prev)
        if (willExpand) next.add(docId)
        else next.delete(docId)
        return next
      })
      // 展开时重拉一次（fetchLogsForDoc 内部会去重，重复调用开销低）
      if (willExpand) void fetchLogsForDoc(docId)
    },
    [fetchLogsForDoc],
  )

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

  const avgTotalMs = stats?.avg_stage_durations_ms?.reduce((a: number, b: number) => a + b, 0) ?? 0

  return (
    <PageContainer>
      <div className="queue-page">
        {/* ----- Hero / header ----- */}
        <header className="queue-page-header">
          <div className="queue-page-title-row">
            <div className="queue-page-title">
              <span className="queue-page-icon" aria-hidden>
                <QueueIcon size={22} />
              </span>
              <h1 className="queue-page-title-text">{t('queue.title')}</h1>
              <WorkerStatusBadge status={workerStatus} />
            </div>
            <div className="queue-page-header-actions">
              <label className="queue-hide-done-toggle">
                <Switch
                  size="sm"
                  checked={hideDone}
                  onChange={setHideDone}
                />
                <span>{t('queue.hideDone')}</span>
              </label>
              <Button
                variant="secondary"
                size="sm"
                icon={<TrashIcon size={14} />}
                onClick={handleCleanup}
                disabled={!stats || stats.done === 0}
              >
                {t('queue.cleanupDone')}
              </Button>
            </div>
          </div>

          {/* ----- Stats row ----- */}
          {stats && (
            <div className="queue-stats-row">
              <StatPill
                label={t('queue.total')}
                value={stats.total}
                tone="neutral"
                icon={<QueueIcon size={14} />}
              />
              {stats.processing > 0 && (
                <StatPill
                  label={t('queue.processing')}
                  value={stats.processing}
                  tone="info"
                  pulse
                />
              )}
              {stats.pending > 0 && (
                <StatPill
                  label={t('queue.pending')}
                  value={stats.pending}
                  tone="warning"
                />
              )}
              {stats.failed > 0 && (
                <StatPill
                  label={t('queue.failed')}
                  value={stats.failed}
                  tone="danger"
                />
              )}
              {stats.done > 0 && (
                <StatPill
                  label={t('queue.done')}
                  value={stats.done}
                  tone="success"
                />
              )}
              {stats.cancelled > 0 && (
                <StatPill
                  label={t('queue.cancelled')}
                  value={stats.cancelled}
                  tone="neutral"
                />
              )}
              {avgTotalMs > 0 && (
                <StatPill
                  label={t('queue.recent5')}
                  value={t('queue.avgPer', { time: formatElapsed(avgTotalMs) })}
                  tone="neutral"
                />
              )}
            </div>
          )}
        </header>

        {/* ----- Filter chips ----- */}
        <div className="queue-filters" role="tablist" aria-label="状态筛选">
          {FILTERS.map((f) => {
            const isActive = filter === f.key
            const count = counts[f.key]
            return (
              <button
                key={f.key}
                type="button"
                role="tab"
                aria-selected={isActive}
                className={`queue-filter-chip${isActive ? ' is-active' : ''}`}
                onClick={() => setFilter(f.key)}
              >
                <span>{f.label}</span>
                <span className="queue-filter-chip-count">{count}</span>
              </button>
            )
          })}
        </div>

        {/* ----- Task list ----- */}
        {visibleTasks.length === 0 ? (
          <EmptyState
            className="queue-empty"
            message={tasks.length === 0 ? t('queue.emptyHint') : t('queue.filterHint')}
            icon={
              <div className="queue-empty-icon">
                <QueueIcon size={28} />
              </div>
            }
          />
        ) : (
          <motion.div
            className="queue-list"
            initial="hidden"
            animate="visible"
            variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.03 } } }}
          >
            <AnimatePresence initial={false}>
              {visibleTasks.map((task) => (
                <TaskRow
                  key={task.id}
                  task={task}
                  now={now}
                  isLogsExpanded={expandedLogDocs.has(task.doc_id)}
                  logs={logMap.get(task.doc_id) ?? []}
                  isActioning={actionId === task.id}
                  onToggleLogs={() => toggleLogs(task.doc_id)}
                  onCancel={() => handleCancel(task)}
                  onRetry={() => handleRetry(task)}
                  onDelete={() => handleDelete(task)}
                  onTogglePin={() => handleSetPriority(task)}
                />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </div>
    </PageContainer>
  )
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface WorkerStatusBadgeProps {
  status: 'online' | 'offline' | 'unknown'
}

const WORKER_STATUS_CONFIG = {
  online:  { i18nKey: 'queue.workerOnline',  titleKey: 'queue.workerOnlineTitle' },
  offline: { i18nKey: 'queue.workerOffline', titleKey: 'queue.workerOfflineTitle' },
  unknown: { i18nKey: 'queue.workerUnknown', titleKey: 'queue.workerUnknownTitle' },
} as const

function WorkerStatusBadge({ status }: WorkerStatusBadgeProps) {
  const { t } = useTranslation()
  const config = WORKER_STATUS_CONFIG[status]
  return (
    <span
      className={`queue-worker-status is-${status}`}
      title={t(config.titleKey)}
    >
      <span className="queue-worker-dot" />
      {t(config.i18nKey)}
    </span>
  )
}

interface StatPillProps {
  label: string
  value: number | string
  tone: 'neutral' | 'info' | 'success' | 'warning' | 'danger'
  icon?: React.ReactNode
  pulse?: boolean
}

function StatPill({ label, value, tone, icon, pulse = false }: StatPillProps) {
  return (
    <div className={`queue-stat-pill is-${tone}`}>
      {icon && <span className="queue-stat-pill-icon">{icon}</span>}
      <div className="queue-stat-pill-body">
        <div className="queue-stat-pill-label">{label}</div>
        <div className={`queue-stat-pill-value${pulse ? ' is-pulse' : ''}`}>{value}</div>
      </div>
    </div>
  )
}

interface TaskRowProps {
  task: IngestTask
  now: number
  isLogsExpanded: boolean
  logs: IngestLogEvent[]
  isActioning: boolean
  onToggleLogs: () => void
  onCancel: () => void
  onRetry: () => void
  onDelete: () => void
  onTogglePin: () => void
}

const STATUS_LABELS_I18N = {
  pending: 'queue.pending',
  processing: 'queue.processing',
  done: 'queue.done',
  failed: 'queue.failed',
  cancelled: 'queue.cancelled',
} as const

function TaskRow({
  task,
  now,
  isLogsExpanded,
  logs,
  isActioning,
  onToggleLogs,
  onCancel,
  onRetry,
  onDelete,
  onTogglePin,
}: TaskRowProps) {
  const { t } = useTranslation()
  const canCancel = task.status === 'pending' || task.status === 'processing'
  const canRetry = task.status === 'failed'
  const canDelete = task.status === 'cancelled' || task.status === 'done' || task.status === 'failed'
  const canSetPriority = task.status === 'pending'

  const fileName = basename(task.file_path) || task.doc_id
  const startedAtMs = task.started_at ? task.started_at * 1000 : null
  const createdAtMs = task.created_at * 1000
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
  const isProcessing = task.status === 'processing'

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2 }}
      className={`queue-task is-${task.status}${isProcessing ? ' is-processing' : ''}`}
    >
      {/* Accent edge for status */}
      <div className="queue-task-edge" aria-hidden />

      <div className="queue-task-body">
        {/* Top row: filename + status + actions */}
        <div className="queue-task-top">
          <div className="queue-task-info">
            <div className="queue-task-title-row">
              <h3 className="queue-task-title" title={task.file_path || task.doc_id}>
                {fileName}
              </h3>
              <Badge tone={STATUS_TONE[task.status]} size="sm" dot>
                {t(STATUS_LABELS_I18N[task.status])}
              </Badge>
              {task.priority > 0 && (
                <Badge tone="info" size="sm">
                  {t('queue.pinTask')}
                </Badge>
              )}
            </div>
            <div className="queue-task-subtitle">
              <span className="queue-task-doc-id">{task.doc_id}</span>
              {task.file_size_bytes != null && (
                <>
                  <span className="queue-task-sep">·</span>
                  <span>{formatBytes(task.file_size_bytes)}</span>
                </>
              )}
              {showPages && (
                <>
                  <span className="queue-task-sep">·</span>
                  <span className="queue-task-pages">
                    {t('queue.pagesUnit', { done: task.pages_done, total: task.pages_total })}
                  </span>
                </>
              )}
              {task.retry_count > 0 && (
                <>
                  <span className="queue-task-sep">·</span>
                  <span className="queue-task-retry">
                    {t('queue.retryCount', { count: task.retry_count, max: task.max_retries })}
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="queue-task-meta">
            {showElapsed && (
              <span
                className={`queue-task-elapsed${stale ? ' is-stale' : ''}`}
                title={
                  stale
                    ? t('queue.staleHint')
                    : startedAtMs
                      ? t('queue.elapsedSinceStart')
                      : t('queue.elapsedSinceCreate')
                }
              >
                {formatElapsed(elapsedMs)}
              </span>
            )}
            {etaMs != null && (
              <span
                className="queue-task-eta"
                title={t('queue.etaTitle')}
              >
                {t('queue.estimated', { time: formatElapsed(etaMs) })}
              </span>
            )}
          </div>
        </div>

        {/* Pipeline flow */}
        <PdfPipelineFlow variant="compact" task={task} />

        {/* Progress (only when actively progressing) */}
        {(task.status === 'pending' || task.status === 'processing') && (
          <div className="queue-task-progress">
            <ProgressBar
              value={task.progress_pct}
              showPercent={task.status === 'processing'}
              color="var(--accent)"
              height={4}
            />
            {task.details && (
              <span className="queue-task-progress-detail">{task.details}</span>
            )}
          </div>
        )}

        {/* Error block (failed only) */}
        {task.status === 'failed' && task.error && (
          <div className="queue-task-error">
            <XIcon size={12} />
            <span>{task.error}</span>
          </div>
        )}

        {/* Bottom action bar */}
        <div className="queue-task-actions">
          <div className="queue-task-actions-left">
            {logs.length > 0 && (
              <span className="queue-task-log-count">
                {t('queue.logCount', { count: logs.length })}
              </span>
            )}
          </div>
          <div className="queue-task-actions-right">
            {canSetPriority && (
              <Button
                variant="ghost"
                size="sm"
                icon={task.priority > 0 ? <UnpinIcon size={14} /> : <PinIcon size={14} />}
                loading={isActioning}
                onClick={onTogglePin}
                title={task.priority > 0 ? t('queue.unpinTask') : t('queue.pinTask')}
              >
                {task.priority > 0 ? t('queue.unpinTask') : t('queue.pinTask')}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              icon={isLogsExpanded ? <ChevronUpIcon size={14} /> : <ChevronDownIcon size={14} />}
              onClick={onToggleLogs}
              title={isLogsExpanded ? t('queue.hideLogs') : t('queue.showLogs')}
            >
              {isLogsExpanded ? t('queue.hideLogs') : t('queue.showLogs')}
            </Button>
            {canRetry && (
              <Button
                variant="primary"
                size="sm"
                icon={<RefreshCwIcon size={14} />}
                loading={isActioning}
                onClick={onRetry}
              >
                {t('queue.retryTask')}
              </Button>
            )}
            {canCancel && (
              <Button
                variant="secondary"
                size="sm"
                loading={isActioning}
                onClick={onCancel}
              >
                {t('queue.cancelTask')}
              </Button>
            )}
            {canDelete && (
              <IconButton
                size={32}
                title={t('queue.deleteTask')}
                onClick={onDelete}
              >
                <TrashIcon size={14} />
              </IconButton>
            )}
          </div>
        </div>

        {/* Expandable log panel */}
        <AnimatePresence initial={false}>
          {isLogsExpanded && (
            <motion.div
              key="logs"
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.18 }}
              className="queue-task-logs"
            >
              <IngestLogPanel logs={logs} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  )
}
