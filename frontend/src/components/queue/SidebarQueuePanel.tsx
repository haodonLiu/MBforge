import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { listen } from '@tauri-apps/api/event'
import { EVT } from '../../api/tauri-events'
import { ingestList, type IngestTask, type IngestWorkerHeartbeatEvent } from '../../api/tauri/ingest_queue'
import ProgressBar from '../ui/ProgressBar'
import Button from '../ui/Button'
import ScrollColumn from '../ui/ScrollColumn'
import EmptyState from '../ui/EmptyState'

interface Props {
  projectRoot: string
  onViewAll: () => void
}

function basename(p: string): string {
  return p.split(/[\\/]/).pop() || p
}

const STAGE_LABEL: Record<string, string> = {
  inspector: '检测',
  text_extract: '文本',
  ocr: 'OCR',
  moldet: '分子',
  index: '索引',
}

export default function SidebarQueuePanel({ projectRoot, onViewAll }: Props) {
  const { t } = useTranslation()
  const [tasks, setTasks] = useState<IngestTask[]>([])
  const [workerOnline, setWorkerOnline] = useState(false)
  const [isLoading, setIsLoading] = useState(false)

  const load = useCallback(async () => {
    if (!projectRoot) return
    setIsLoading(true)
    try {
      const all = await ingestList(projectRoot)
      setTasks(all.filter((task) => task.status !== 'done' && task.status !== 'cancelled'))
    } catch (e) {
      console.error('[SidebarQueuePanel] load failed:', e)
    } finally {
      setIsLoading(false)
    }
  }, [projectRoot])

  useEffect(() => {
    void load()

    let unlistenQueue: (() => void) | null = null
    let unlistenHeartbeat: (() => void) | null = null

    const setup = async () => {
      unlistenQueue = await listen(EVT.IngestQueueUpdate, () => {
        void load()
      })
      unlistenHeartbeat = await listen<IngestWorkerHeartbeatEvent>(EVT.IngestWorkerHeartbeat, (event) => {
        if (event.payload.project_root !== projectRoot) return
        setWorkerOnline(event.payload.alive)
      })
    }

    void setup().catch((e: unknown) => {
      console.error('[SidebarQueuePanel] listen failed:', e)
    })

    return () => {
      unlistenQueue?.()
      unlistenHeartbeat?.()
    }
  }, [load, projectRoot])

  return (
    <div
      className="sidebar-queue-panel"
      style={{
        gridColumn: '3',
        gridRow: '1 / 4',
        background: 'var(--bg-surface)',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        width: '240px',
      }}
    >
      <div className="sidebar-queue-header">
        <span>{t('sidebarQueue.title') || '处理队列'}</span>
        <span
          className={`sidebar-queue-worker-status ${workerOnline ? 'is-online' : 'is-offline'}`}
          title={workerOnline ? 'Worker 在线' : 'Worker 离线'}
        />
      </div>

      <ScrollColumn>
        {isLoading && tasks.length === 0 ? (
          <EmptyState message={t('common.loading') || '加载中…'} />
        ) : tasks.length === 0 ? (
          <EmptyState message={t('sidebarQueue.empty') || '暂无处理中任务'} />
        ) : (
          <ul className="sidebar-queue-list">
            {tasks.map((task) => (
              <li key={task.id} className="sidebar-queue-item">
                <div className="sidebar-queue-item-row">
                  <span className="sidebar-queue-file" title={basename(task.file_path)}>
                    {basename(task.file_path)}
                  </span>
                  <span className={`sidebar-queue-status is-${task.status}`}>
                    {task.status}
                  </span>
                </div>
                <div className="sidebar-queue-item-row">
                  <span className="sidebar-queue-stage">{STAGE_LABEL[task.stage] || task.stage}</span>
                  <span className="sidebar-queue-progress-text">{Math.round(task.progress_pct)}%</span>
                </div>
                <ProgressBar value={task.progress_pct} height={4} showPercent={false} />
              </li>
            ))}
          </ul>
        )}
      </ScrollColumn>

      <div className="sidebar-queue-footer">
        <Button variant="secondary" size="sm" onClick={onViewAll} style={{ width: '100%' }}>
          {t('sidebarQueue.viewAll') || '查看全部'}
        </Button>
      </div>
    </div>
  )
}
