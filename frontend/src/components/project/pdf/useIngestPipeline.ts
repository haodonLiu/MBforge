import { useEffect, useState, useCallback } from 'react'
import { listen } from '@tauri-apps/api/event'
import { EVT } from '../../../api/tauri-events'
import {
  ingestList,
  type IngestTask,
  type IngestProgressEvent,
  type IngestQueueUpdateEvent,
  type IngestEmbedEvent,
} from '../../../api/tauri/ingest_queue'

// Re-export so consumers can import the type from one place
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

  const findTask = useCallback(async () => {
    if (!projectRoot) return
    try {
      const tasks = await ingestList(projectRoot)
      const sorted = tasks
        .filter((t) => t.doc_id === docId)
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
  }, [docId, projectRoot])

  useEffect(() => {
    void findTask()
  }, [findTask])

  useEffect(() => {
    let unlistenProgress: (() => void) | null = null
    let unlistenQueue: (() => void) | null = null
    let unlistenEmbed: (() => void) | null = null

    const setup = async () => {
      unlistenProgress = await listen<IngestProgressEvent>(EVT.IngestProgress, (event) => {
        if (event.payload.doc_id !== docId) return
        setProgressPct(event.payload.progress_pct)
        setDetails(event.payload.details)
      })
      unlistenQueue = await listen<IngestQueueUpdateEvent>(EVT.IngestQueueUpdate, (event) => {
        if (event.payload.doc_id !== docId) return
        void findTask()
      })
      unlistenEmbed = await listen<IngestEmbedEvent>(EVT.IngestEmbed, (event) => {
        if (event.payload.doc_id !== docId) return
        setEmbedState({
          action: event.payload.action,
          model: event.payload.model,
          progress: event.payload.progress,
        })
      })
    }

    void setup().catch((e: unknown) => {
      console.error('[useIngestPipeline] listen failed:', e)
    })

    return () => {
      unlistenProgress?.()
      unlistenQueue?.()
      unlistenEmbed?.()
    }
  }, [docId, findTask])

  return {
    task,
    progressPct,
    details,
    embedState,
  }
}
