import { useEffect, useState, useCallback, useRef } from 'react'
import {
  ingestList,
  subscribeIngestEvents,
  type IngestTask,
} from '@/api/http/ingest_queue'

export type EmbedSubState = {
  action: 'start' | 'done' | 'failed' | 'skipped'
  model: string
  progress: number
}

interface IngestPipelineState {
  task: IngestTask | null
  progressPct: number
  details: string
  embedState: EmbedSubState | null
}

export function useIngestPipeline(docId: string, projectRoot: string): IngestPipelineState {
  const [task, setTask] = useState<IngestTask | null>(null)
  const [progressPct, setProgressPct] = useState(0)
  const [details, setDetails] = useState('')
  const [embedState] = useState<EmbedSubState | null>(null)
  const docIdRef = useRef(docId)

  useEffect(() => {
    docIdRef.current = docId
  }, [docId])

  const findTask = useCallback(async () => {
    if (!projectRoot) return
    try {
      const tasks = await ingestList(projectRoot)
      const sorted = tasks
        .filter((t) => t.doc_id === docIdRef.current)
        .sort((a, b) => b.created_at - a.created_at)
      const match = sorted.length > 0 ? sorted[0] : undefined
      if (match) {
        setTask(match)
        setProgressPct(match.progress_pct)
        setDetails(match.details)
      } else {
        setTask(null)
        setProgressPct(0)
        setDetails('')
      }
    } catch (e: unknown) {
      console.error('[useIngestPipeline] findTask failed:', e)
    }
  }, [projectRoot])

  useEffect(() => {
    void findTask()
  }, [findTask])

  useEffect(() => {
    let cancelled = false

    const poll = async () => {
      if (cancelled) return
      try {
        const tasks = await ingestList(projectRoot)
        // Guard against state updates after the component unmounts.
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
        if (cancelled) return
        const sorted = tasks
          .filter((t) => t.doc_id === docIdRef.current)
          .sort((a, b) => b.created_at - a.created_at)
        const match = sorted.length > 0 ? sorted[0] : undefined
        if (match) {
          setTask(match)
          setProgressPct(match.progress_pct)
          setDetails(match.details)
        } else {
          setTask(null)
          setProgressPct(0)
          setDetails('')
        }
      } catch {
        // polling — ignore transient errors
      }
    }

    const timer = setInterval(poll, 2000)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [projectRoot])

  // Incremental SSE subscription for real-time error/warning events.
  useEffect(() => {
    if (!projectRoot || !task || task.status !== 'processing') return

    const sub = subscribeIngestEvents(projectRoot, task.id, {
      onEvent: (ev) => {
        if ('progress_pct' in ev) {
          setProgressPct(ev.progress_pct)
          setDetails(ev.details)
          return
        }

        const { stage, event, message, data } = ev
        if (event === 'error') {
          // Runtime defensive guard: backend may send a string or nullish payload.
          // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
          const errorCode = typeof data === 'object' && data !== null && 'error_code' in data ? String(data.error_code) : 'error'
          setDetails(`[${stage}] ${errorCode}: ${message}`)
          setTask((prev) => (prev ? { ...prev, status: 'failed', error: message } : prev))
        } else if (event === 'warning') {
          setDetails(`[${stage}] warning: ${message}`)
        } else {
          setDetails(message)
        }
      },
      onError: (err) => {
        console.error('[useIngestPipeline] SSE error:', err)
      },
    })

    return () => {
      sub.close()
    }
    // Intentionally use id/status primitives to avoid re-subscribing on every
    // poll update while still closing the connection when the task is done/failed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectRoot, task?.id, task?.status])

  return {
    task,
    progressPct,
    details,
    embedState,
  }
}
