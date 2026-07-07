import { useEffect, useState, useCallback, useRef } from 'react'
import {
  ingestList,
  type IngestTask,
  type IngestEmbedEvent,
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
  const [embedState, setEmbedState] = useState<EmbedSubState | null>(null)
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
    let timer: ReturnType<typeof setInterval> | null = null

    const poll = async () => {
      if (cancelled) return
      try {
        const tasks = await ingestList(projectRoot)
        if (cancelled) return
        const match = tasks
          .filter((t) => t.doc_id === docIdRef.current)
          .sort((a, b) => b.created_at - a.created_at)[0]
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

    timer = setInterval(poll, 2000)
    return () => {
      cancelled = true
      if (timer !== null) clearInterval(timer)
    }
  }, [projectRoot])

  return {
    task,
    progressPct,
    details,
    embedState,
  }
}
