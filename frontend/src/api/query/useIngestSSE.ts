/** Bridge between the inline SSE subscription and React Query cache.
 *
 *  On mount, subscribes to pipeline SSE events for a given task and
 *  writes them into the React Query cache so polling consumers see
 *  real-time progress without waiting for the next refetch interval.
 *
 *  This is layered ON TOP of the existing polling (useIngestQueue).
 *  It does NOT replace it — it only shortens the feedback loop for
 *  in-progress tasks.
 */

import { useEffect, useRef } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { subscribeIngestEvents } from '../http/ingest_queue'
import { queryKeys } from './keys'
import type { IngestTask } from '../http/ingest_queue'

interface UseIngestSSEOptions {
  libraryRoot: string
  taskId: string | null
  /** If true, do not subscribe (e.g. no task is active). */
  disabled?: boolean
}

/**
 * Subscribe to SSE events for a single pipeline task and merge
 * progress updates into the React Query cache.
 *
 * Usage (inside ProcessingQueue or similar):
 *   useIngestSSE({ libraryRoot, taskId: activeTaskId })
 */
export function useIngestSSE({
  libraryRoot,
  taskId,
  disabled,
}: UseIngestSSEOptions): void {
  const qc = useQueryClient()
  const cleanupRef = useRef<(() => void) | null>(null)

  useEffect(() => {
    if (disabled || !taskId) return

    // Clean up previous subscription before creating a new one.
    cleanupRef.current?.()
    cleanupRef.current = null

    const sub = subscribeIngestEvents(libraryRoot, taskId, {
      onEvent: (event) => {
        // Optimistically update the matching task in the cached queue.
        // The next 10-second refetch will correct anything we miss.
        const ev = event as unknown as Record<string, unknown>
        qc.setQueryData<IngestTask[]>(
          queryKeys.ingest.queue(libraryRoot),
          (prev) =>
            prev?.map((t) =>
              t.id === taskId
                ? {
                    ...t,
                    progress_pct:
                      'progress_pct' in ev
                        ? (ev.progress_pct as number)
                        : t.progress_pct,
                    stage:
                      'stage' in ev
                        ? (ev.stage as string)
                        : t.stage,
                    details:
                      'details' in ev
                        ? (ev.details as string)
                        : t.details,
                  }
                : t,
            ),
        )
      },
      onError: () => {
        // SSE error — the browser EventSource will auto-reconnect.
        // We do not need to do anything; the polling fallback covers us.
      },
    })

    cleanupRef.current = sub.close

    return () => {
      sub.close()
      cleanupRef.current = null
    }
  }, [libraryRoot, taskId, disabled, qc])
}
