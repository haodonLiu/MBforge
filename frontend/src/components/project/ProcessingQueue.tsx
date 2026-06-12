import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { listen } from '@tauri-apps/api/event'
import Card from '../ui/Card'
import BodyText from '../ui/BodyText'
import Button from '../ui/Button'
import Badge from '../ui/Badge'
import ProgressBar from '../ui/ProgressBar'
import EmptyState from '../ui/EmptyState'
import { EVT } from '../../api/tauri-events'
import {
  ingestList,
  ingestStats,
  ingestCancel,
  ingestRetry,
  ingestCleanup,
  type IngestTask,
  type QueueStats,
  type IngestQueueUpdateEvent,
} from '../../api/tauri/ingest_queue'
import { showToast } from '../../hooks/useToast'

interface Props {
  projectRoot: string
}

const statusLabel: Record<string, string> = {
  pending: '待处理',
  processing: '处理中',
  done: '完成',
  failed: '失败',
  cancelled: '已取消',
}

const statusVariant: Record<string, 'neutral' | 'warning' | 'success' | 'danger'> = {
  pending: 'neutral',
  processing: 'warning',
  done: 'success',
  failed: 'danger',
  cancelled: 'neutral',
}

const stageLabel: Record<string, string> = {
  inspector: '文档检测',
  text_extract: '文本提取',
  ocr: 'OCR 识别',
  moldet: '分子扫描',
  index: '索引构建',
}

export default function ProcessingQueue({ projectRoot }: Props) {
  const [tasks, setTasks] = useState<IngestTask[]>([])
  const [stats, setStats] = useState<QueueStats | null>(null)
  const [actionId, setActionId] = useState<string | null>(null)

  const load = useCallback(async () => {
    if (!projectRoot) return
    try {
      const [list, s] = await Promise.all([ingestList(projectRoot), ingestStats(projectRoot)])
      setTasks(list)
      setStats(s)
    } catch (e) {
      console.error('[ProcessingQueue] load failed:', e)
    }
  }, [projectRoot])

  useEffect(() => {
    load()

    let unlisten: (() => void) | null = null
    const setup = async () => {
      unlisten = await listen<IngestQueueUpdateEvent>(EVT.IngestQueueUpdate, () => {
        load()
      })
    }
    setup().catch((e) => {
      console.error('[ProcessingQueue] listen failed:', e)
    })

    return () => {
      unlisten?.()
    }
  }, [load])

  const handleCancel = async (task: IngestTask) => {
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
  }

  const handleRetry = async (task: IngestTask) => {
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
  }

  const handleCleanup = async () => {
    if (!projectRoot) return
    try {
      const removed = await ingestCleanup(projectRoot)
      showToast(`已清理 ${removed} 个完成任务`, 'success')
      await load()
    } catch (e) {
      console.error('[ProcessingQueue] cleanup failed:', e)
      showToast('清理失败: ' + String(e), 'error')
    }
  }

  return (
    <div className="processing-queue">
      <div className="processing-queue-header">
        <BodyText size="lg" style={{ fontWeight: 600 }}>处理队列</BodyText>
        {stats && (
          <div className="processing-queue-stats">
            <Badge variant="neutral">总计 {stats.total}</Badge>
            <Badge variant="warning">待处理 {stats.pending}</Badge>
            <Badge variant="warning">处理中 {stats.processing}</Badge>
            <Badge variant="success">完成 {stats.done}</Badge>
            {stats.failed > 0 && <Badge variant="danger">失败 {stats.failed}</Badge>}
            {stats.cancelled > 0 && <Badge variant="neutral">已取消 {stats.cancelled}</Badge>}
          </div>
        )}
        <Button variant="secondary" size="sm" onClick={handleCleanup}>
          清理已完成
        </Button>
      </div>

      {tasks.length === 0 ? (
        <EmptyState message="暂无处理任务" />
      ) : (
        <div className="processing-queue-list">
          {tasks.map((task, index) => {
            const canCancel = task.status === 'pending' || task.status === 'processing'
            const canRetry = task.status === 'failed'
            const label = stageLabel[task.stage] || task.stage

            return (
              <motion.div
                key={task.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.03, duration: 0.3 }}
              >
                <Card padding="12px 16px" className="processing-queue-item">
                  <div className="processing-queue-item-row">
                    <div className="processing-queue-item-info">
                      <BodyText size="sm" style={{ fontWeight: 500 }} className="processing-queue-doc-id">
                        {task.doc_id}
                      </BodyText>
                      <div className="processing-queue-item-meta">
                        <Badge variant={statusVariant[task.status] ?? 'neutral'}>
                          {statusLabel[task.status] || task.status}
                        </Badge>
                        <BodyText size="sm" muted>{label}</BodyText>
                      </div>
                    </div>
                    <div className="processing-queue-item-actions">
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
                    </div>
                  </div>

                  <ProgressBar
                    value={task.progress_pct}
                    label={task.details || label}
                    showPercent={task.status === 'processing'}
                    style={{ marginTop: '10px' }}
                  />

                  {task.error && (
                    <BodyText size="sm" className="processing-queue-error">
                      {task.error}
                    </BodyText>
                  )}
                </Card>
              </motion.div>
            )
          })}
        </div>
      )}
    </div>
  )
}
