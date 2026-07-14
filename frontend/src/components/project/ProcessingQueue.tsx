import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { useVirtualizer } from '@tanstack/react-virtual'
import PageContainer from '../ui/PageContainer'
import { useTranslation } from 'react-i18next'
import Button from '../ui/Button'
import Switch from '../ui/Switch'
import EmptyState from '../ui/EmptyState'
import { QueueIcon, TrashIcon } from '../icons'
import { WorkerStatusBadge } from './WorkerStatusBadge'
import { StatPill } from './StatPill'
import { TaskRow } from './TaskRow'
import {
  ingestCleanup,
  ingestGetLogs,
  ingestCancel,
  ingestRetry,
  ingestDeleteTask,
  ingestSetPriority,
  type IngestLogEvent,
  type IngestTask,
} from '@/api/http/ingest_queue'
import {
  useIngestQueue,
  useIngestStats,
  useWorkerStatus,
} from '@/api/query/hooks'
import { useIngestSSE } from '@/api/query/useIngestSSE'
import { showToast } from '@/hooks/useToast'

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

export default function ProcessingQueue() {
  const { libraryRoot } = useAppContext()
  const { t } = useTranslation()

  // ── React Query data ─────────────────────────────────────────
  const { data: tasks = [], isLoading } = useIngestQueue(libraryRoot)
  const { data: stats } = useIngestStats(libraryRoot)
  const { data: workerData } = useWorkerStatus()
  const workerStatus = workerData?.status === 'online' ? 'online' : 'offline' as 'online' | 'offline' | 'unknown'

  // ── Local UI state ────────────────────────────────────────────
  const [actionId, setActionId] = useState<string | null>(null)
  const [filter, setFilter] = useState<FilterKey>('all')
  const [hideDone, setHideDone] = useState(true)
  const [logMap, setLogMap] = useState<Map<string, IngestLogEvent[]>>(new Map())
  const [expandedLogDocs, setExpandedLogDocs] = useState<Set<string>>(new Set())

  // Track the "most interesting" processing task for SSE subscription.
  const activeTaskId = useMemo(() => {
    const processing = tasks.find(t => t.status === 'processing')
    return processing?.id ?? null
  }, [tasks])

  // SSE bridge — pushes real-time progress into the query cache.
  useIngestSSE({ libraryRoot, taskId: activeTaskId })

  // Live "now" timestamp for elapsed-time displays.
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const hasProcessing = tasks.some((t) => t.status === 'processing')
    if (!hasProcessing) return
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [tasks])

  // ── Filters ───────────────────────────────────────────────────
  const FILTERS: { key: FilterKey; label: string }[] = useMemo(() => [
    { key: 'all', label: t('queue.all') },
    { key: 'pending', label: t('queue.pending') },
    { key: 'processing', label: t('queue.processing') },
    { key: 'failed', label: t('queue.failed') },
    { key: 'cancelled', label: t('queue.cancelled') },
    { key: 'done', label: t('queue.done') },
  ], [t])

  // ── Log fetching ──────────────────────────────────────────────
  const fetchLogsForDoc = useCallback(
    async (docId: string) => {
      try {
        const records = await ingestGetLogs(libraryRoot, docId, 500)
        if (records.length === 0) return
        setLogMap((prev) => {
          const list = prev.get(docId) ?? []
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

  // Pre-fetch logs for all tasks on first load.
  useEffect(() => {
    if (!libraryRoot) return
    const docIds = new Set(tasks.map((t) => t.doc_id))
    for (const docId of docIds) {
      void fetchLogsForDoc(docId)
    }
  }, [libraryRoot, tasks, fetchLogsForDoc])

  // ── Action handlers ───────────────────────────────────────────
  const handleCancel = useCallback(
    async (task: IngestTask) => {
      if (!libraryRoot) return
      setActionId(task.id)
      try {
        await ingestCancel(libraryRoot, task.id)
        showToast(t('queue.taskCancelled'), 'success')
      } catch (e) {
        console.error('[ProcessingQueue] cancel failed:', e)
        showToast(t('queue.cancelFailed', { error: String(e) }), 'error')
      } finally {
        setActionId(null)
      }
    },
    [libraryRoot, t],
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
      } catch (e) {
        console.error('[ProcessingQueue] retry failed:', e)
        showToast(t('queue.retryFailed', { error: String(e) }), 'error')
      } finally {
        setActionId(null)
      }
    },
    [libraryRoot, t],
  )

  const handleCleanup = useCallback(async () => {
    if (!libraryRoot) return
    try {
      const removed = await ingestCleanup(libraryRoot)
      showToast(t('queue.cleanedUp', { count: removed }), 'success')
    } catch (e) {
      console.error('[ProcessingQueue] cleanup failed:', e)
      showToast(t('queue.cleanupFailed', { error: String(e) }), 'error')
    }
  }, [libraryRoot, t])

  const handleSetPriority = useCallback(
    async (task: IngestTask) => {
      if (!libraryRoot) return
      setActionId(task.id)
      try {
        const nextPriority = task.priority > 0 ? 0 : 1
        await ingestSetPriority(libraryRoot, task.id, nextPriority)
        showToast(nextPriority > 0 ? t('queue.taskPinned') : t('queue.taskUnpinned'), 'success')
      } catch (e) {
        console.error('[ProcessingQueue] set priority failed:', e)
        showToast(t('queue.pinFailed', { error: String(e) }), 'error')
      } finally {
        setActionId(null)
      }
    },
    [libraryRoot, t],
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
      } catch (e) {
        console.error('[ProcessingQueue] delete failed:', e)
        showToast(t('queue.deleteFailed', { error: String(e) }), 'error')
      } finally {
        setActionId(null)
      }
    },
    [libraryRoot, t],
  )

  const toggleLogs = useCallback(
    (docId: string) => {
      setExpandedLogDocs((prev) => {
        const next = new Set(prev)
        if (next.has(docId)) next.delete(docId)
        else next.add(docId)
        return next
      })
      void fetchLogsForDoc(docId)
    },
    [fetchLogsForDoc],
  )

  // ── Filter + sort ─────────────────────────────────────────────
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

  const avgTotalMs =
    stats?.avg_stage_durations_ms?.reduce((a: number, b: number) => a + b, 0) ?? 0

  if (isLoading) {
    return (
      <PageContainer>
        <div className="workspace-loading">Loading...</div>
      </PageContainer>
    )
  }

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
              {stats.processing !== undefined && stats.processing > 0 && (
                <StatPill
                  label={t('queue.processing')}
                  value={stats.processing ?? 0}
                  tone="info"
                  pulse
                />
              )}
              {((stats.pending ?? 0) > 0) && (
                <StatPill
                  label={t('queue.pending')}
                  value={stats.pending ?? 0}
                  tone="warning"
                />
              )}
              {((stats.failed ?? 0) > 0) && (
                <StatPill
                  label={t('queue.failed')}
                  value={stats.failed ?? 0}
                  tone="danger"
                />
              )}
              {((stats.done ?? 0) > 0) && (
                <StatPill
                  label={t('queue.done')}
                  value={stats.done ?? 0}
                  tone="success"
                />
              )}
              {((stats.cancelled ?? 0) > 0) && (
                <StatPill
                  label={t('queue.cancelled')}
                  value={stats.cancelled ?? 0}
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
          <QueueTaskList
            tasks={visibleTasks}
            now={now}
            expandedLogDocs={expandedLogDocs}
            logMap={logMap}
            actionId={actionId}
            onToggleLogs={toggleLogs}
            onCancel={handleCancel}
            onRetry={handleRetry}
            onDelete={handleDelete}
            onTogglePin={handleSetPriority}
          />
        )}
      </div>
    </PageContainer>
  )
}

interface QueueTaskListProps {
  tasks: IngestTask[]
  now: number
  expandedLogDocs: Set<string>
  logMap: Map<string, IngestLogEvent[]>
  actionId: string | null
  onToggleLogs: (docId: string) => void
  onCancel: (task: IngestTask) => void
  onRetry: (task: IngestTask) => void
  onDelete: (task: IngestTask) => void
  onTogglePin: (task: IngestTask) => void
}

/** Keep the common queue small and animated; virtualize only genuinely long queues. */
function QueueTaskList({
  tasks,
  now,
  expandedLogDocs,
  logMap,
  actionId,
  onToggleLogs,
  onCancel,
  onRetry,
  onDelete,
  onTogglePin,
}: QueueTaskListProps) {
  const parentRef = useRef<HTMLDivElement>(null)
  const shouldVirtualize = tasks.length > 80
  const virtualizer = useVirtualizer({
    count: shouldVirtualize ? tasks.length : 0,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 220,
    measureElement: (element) => element.getBoundingClientRect().height,
    overscan: 6,
  })

  const renderTask = (task: IngestTask) => (
    <TaskRow
      key={task.id}
      task={task}
      now={now}
      isLogsExpanded={expandedLogDocs.has(task.doc_id)}
      logs={logMap.get(task.doc_id) ?? []}
      isActioning={actionId === task.id}
      onToggleLogs={() => onToggleLogs(task.doc_id)}
      onCancel={() => onCancel(task)}
      onRetry={() => onRetry(task)}
      onDelete={() => onDelete(task)}
      onTogglePin={() => onTogglePin(task)}
    />
  )

  if (!shouldVirtualize) {
    return (
      <motion.div
        className="queue-list"
        initial="hidden"
        animate="visible"
        variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.03 } } }}
      >
        <AnimatePresence initial={false}>
          {tasks.map(renderTask)}
        </AnimatePresence>
      </motion.div>
    )
  }

  return (
    <div ref={parentRef} className="queue-list queue-list-virtual">
      <div
        className="queue-list-virtual-inner"
        style={{ height: `${virtualizer.getTotalSize()}px` }}
      >
        {virtualizer.getVirtualItems().map((virtualItem) => (
          <div
            key={tasks[virtualItem.index].id}
            ref={virtualizer.measureElement}
            data-index={virtualItem.index}
            className="queue-list-virtual-item"
            style={{ transform: `translateY(${virtualItem.start}px)` }}
          >
            {renderTask(tasks[virtualItem.index])}
          </div>
        ))}
      </div>
    </div>
  )
}

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

