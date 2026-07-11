/** Task row — display an IngestTask in the queue list. */

import { motion, AnimatePresence } from 'framer-motion'
import { useTranslation } from 'react-i18next'
import Badge from '../ui/Badge'
import Button from '../ui/Button'
import IconButton from '../ui/IconButton'
import ProgressBar from '../ui/ProgressBar'
import PdfPipelineFlow from './pdf/PdfPipelineFlow'
import IngestLogPanel from './IngestLogPanel'
import {
  ChevronDownIcon,
  ChevronUpIcon,
  XIcon,
  PinIcon,
  UnpinIcon,
  TrashIcon,
  RefreshCwIcon,
} from '../icons'
import type { IngestTask, IngestLogEvent } from '@/api/http/ingest_queue'

// ---------------------------------------------------------------------------
// Formatting helpers (shared across the queue module)
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

/** Format bytes as human-readable size. */
function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null || bytes < 0) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
}

/** Estimate remaining milliseconds. */
function estimateRemainingMs(elapsedMs: number, progressPct: number): number | null {
  if (progressPct <= 0 || progressPct >= 1 || elapsedMs <= 0) return null
  const rate = progressPct / elapsedMs
  const remainingProgress = 1 - progressPct
  return remainingProgress / rate
}

/** True if a processing task has not updated in 5 minutes. */
function isStale(task: IngestTask, now: number): boolean {
  if (task.status !== 'processing') return false
  return now - task.updated_at * 1000 > 5 * 60 * 1000
}

/** Return basename of a file path. */
function basename(p: string): string {
  if (!p) return ''
  const parts = p.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] ?? p
}

// ---------------------------------------------------------------------------
// Status display config
// ---------------------------------------------------------------------------

const STATUS_TONE: Record<IngestTask['status'], 'info' | 'warning' | 'success' | 'danger' | 'neutral'> = {
  processing: 'info',
  pending: 'warning',
  done: 'success',
  failed: 'danger',
  cancelled: 'neutral',
}

const STATUS_LABELS_I18N: Record<IngestTask['status'], string> = {
  pending: 'queue.pending',
  processing: 'queue.processing',
  done: 'queue.done',
  failed: 'queue.failed',
  cancelled: 'queue.cancelled',
}

// ---------------------------------------------------------------------------
// TaskRow
// ---------------------------------------------------------------------------

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

export const TaskRow = function TaskRow({
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
