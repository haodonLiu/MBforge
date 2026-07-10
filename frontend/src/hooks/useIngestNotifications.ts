import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'
import {
  ingestList,
  isSelfTriggeredDoc,
  removeSelfTriggeredDoc,
  type IngestTask,
} from '../api/http/ingest_queue'
import { toast } from '../components/ui/Toast'

export function useIngestNotifications(libraryRoot: string): void {
  const location = useLocation()
  const libraryRootRef = useRef(libraryRoot)
  const lastStatusRef = useRef<Record<string, IngestTask['status']>>({})

  useEffect(() => {
    libraryRootRef.current = libraryRoot
  }, [libraryRoot])

  useEffect(() => {
    lastStatusRef.current = {}
  }, [libraryRoot])

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setInterval> | null = null

    const poll = async () => {
      if (cancelled) return
      const root = libraryRootRef.current
      if (!root) return
      try {
        const tasks = await ingestList(root)
        if (cancelled) return
        if (!Array.isArray(tasks)) return
        const currentMap: Record<string, IngestTask['status']> = {}
        for (const task of tasks) {
          currentMap[task.id] = task.status
        }
        const prevMap = lastStatusRef.current
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
        if (!cancelled) console.error('[useIngestNotifications] poll failed:', e)
      }
    }

    timer = setInterval(poll, 5000)
    return () => {
      cancelled = true
      if (timer !== null) clearInterval(timer)
    }
  }, [location.pathname])
}
