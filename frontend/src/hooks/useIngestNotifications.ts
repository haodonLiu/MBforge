import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import { listen } from '@tauri-apps/api/event'
import { EVT } from '../api/tauri-events'
import {
  ingestList,
  isSelfTriggeredDoc,
  removeSelfTriggeredDoc,
  type IngestQueueUpdateEvent,
  type IngestTask,
} from '../api/tauri/ingest_queue'
import { toast } from '../components/ui/Toast'

export function useIngestNotifications(projectRoot: string): void {
  const location = useLocation()
  const projectRootRef = useRef(projectRoot)
  const lastStatusRef = useRef<Record<string, IngestTask['status']>>({})

  useEffect(() => {
    projectRootRef.current = projectRoot
  }, [projectRoot])

  // 切换项目后重置状态快照，避免把当前项目的已完成任务误当作“新完成”弹出 toast。
  useEffect(() => {
    lastStatusRef.current = {}
  }, [projectRoot])

  useEffect(() => {
    let unlisten: (() => void) | null = null

    const setup = async () => {
      unlisten = await listen<IngestQueueUpdateEvent>(EVT.IngestQueueUpdate, () => {
        const root = projectRootRef.current
        if (!root) return
        void (async () => {
          try {
            const tasks = await ingestList(root)
            const currentMap: Record<string, IngestTask['status']> = {}
            for (const task of tasks) {
              currentMap[task.id] = task.status
            }
            const prevMap = lastStatusRef.current
            // 首次运行（或刚切换项目）只播种状态，不弹 toast。
            if (Object.keys(prevMap).length === 0) {
              lastStatusRef.current = currentMap
              return
            }
            for (const task of tasks) {
              if (task.status === 'done' && prevMap[task.id] !== 'done') {
                if (isSelfTriggeredDoc(task.doc_id)) {
                  removeSelfTriggeredDoc(task.doc_id)
                } else if (location.pathname !== '/queue') {
                  toast.success(`文档处理完成：${task.doc_id}`, { duration: 4000 })
                }
              }
            }
            lastStatusRef.current = currentMap
          } catch (e: unknown) {
            console.error('[useIngestNotifications] diff failed:', e)
          }
        })()
      })
    }

    void setup().catch((e: unknown) => {
      console.error('[useIngestNotifications] listen failed:', e)
    })

    return () => {
      unlisten?.()
    }
  }, [location.pathname])
}
