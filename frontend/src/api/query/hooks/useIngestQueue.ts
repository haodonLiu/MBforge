/** React Query hooks for the ingest queue (pipeline tasks). */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ingestList,
  ingestStats,
  ingestWorkerStatus,
  ingestCancel,
  ingestRetry,
  ingestDeleteTask,
} from '../../http/ingest_queue'
import { queryKeys } from '../keys'

/**
 * Polling-based queue task list.
 *
 * Refetches every 10 s to keep the ProcessingQueue in sync with the
 * backend — replaces the previous `useEffect` + `setInterval` pattern.
 */
export function useIngestQueue(libraryRoot: string) {
  return useQuery({
    queryKey: queryKeys.ingest.queue(libraryRoot),
    queryFn: () => ingestList(libraryRoot),
    refetchInterval: 10_000,
  })
}

/** Queue statistics (total / pending / processing / done / failed / …). */
export function useIngestStats(libraryRoot: string) {
  return useQuery({
    queryKey: queryKeys.ingest.stats(libraryRoot),
    queryFn: () => ingestStats(libraryRoot),
    refetchInterval: 10_000,
  })
}

/** Background worker status (alive / offline). */
export function useWorkerStatus() {
  return useQuery({
    queryKey: queryKeys.ingest.workerStatus(),
    queryFn: ingestWorkerStatus,
    refetchInterval: 30_000,
  })
}

// ── Mutations ────────────────────────────────────────────────────────

/** Cancel a running / pending pipeline task. */
export function useCancelTask() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({
      libraryRoot,
      taskId,
    }: {
      libraryRoot: string
      taskId: string
    }) => ingestCancel(libraryRoot, taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.ingest.all })
    },
  })
}

/** Retry a failed pipeline task. */
export function useRetryTask() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({
      libraryRoot,
      taskId,
    }: {
      libraryRoot: string
      taskId: string
    }) => ingestRetry(libraryRoot, taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.ingest.all })
    },
  })
}

/** Delete a pipeline task record. */
export function useDeleteTask() {
  const qc = useQueryClient()

  return useMutation({
    mutationFn: ({
      libraryRoot,
      taskId,
    }: {
      libraryRoot: string
      taskId: string
    }) => ingestDeleteTask(libraryRoot, taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.ingest.all })
    },
  })
}
