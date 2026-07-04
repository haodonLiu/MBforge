/** Global model download status + resources sync. */
import { useEffect, useState, useCallback, useRef } from 'react'
import { httpGet } from '../api/http/_utils'
import { resourcesCheck, type ResourceStatusItem } from '../api/http/environment'

export type ModelStatus = 'ready' | 'downloading' | 'missing' | 'failed' | 'unknown'

export interface DownloadState {
  resourceId: string
  status: 'idle' | 'connecting' | 'downloading' | 'completed' | 'failed'
  file: string
  fileProgress: number
  fileIndex: number
  totalFiles: number
  error: string
}

export interface ModelStatusSnapshot {
  status: ModelStatus
  total: number
  missing: number
  missingIds: string[]
}

const INITIAL_SNAPSHOT: ModelStatusSnapshot = {
  status: 'unknown',
  total: 0,
  missing: 0,
  missingIds: [],
}

const INITIAL_DOWNLOAD: DownloadState = {
  resourceId: '',
  status: 'idle',
  file: '',
  fileProgress: 0,
  fileIndex: 0,
  totalFiles: 0,
  error: '',
}

function isModelResource(r: ResourceStatusItem): boolean {
  return r.type === 'model' || r.type === 'Model'
}

function summarize(items: ResourceStatusItem[]): ModelStatusSnapshot {
  const models = items.filter(isModelResource)
  const missing = models.filter(r => r.status === 'not_found' || r.status === 'NotFound')
  return {
    status: models.length === 0
      ? 'unknown'
      : missing.length === 0
        ? 'ready'
        : 'missing',
    total: models.length,
    missing: missing.length,
    missingIds: missing.map(r => r.id),
  }
}

function toDownloadState(resourceId: string, p: {
  status: string
  file: string
  file_progress: number
  file_index: number
  total_files: number
  error: string
}): DownloadState {
  return {
    resourceId,
    status: p.status as DownloadState['status'],
    file: p.file,
    fileProgress: p.file_progress,
    fileIndex: p.file_index,
    totalFiles: p.total_files,
    error: p.error,
  }
}

function aggregateDownload(downloads: Record<string, DownloadState>): DownloadState {
  const values = Object.values(downloads)
  if (values.length === 0) return INITIAL_DOWNLOAD

  const active = values.filter(d => d.status === 'connecting' || d.status === 'downloading')
  if (active.length > 0) return active[active.length - 1]

  const terminal = values.filter(d => d.status === 'failed' || d.status === 'completed')
  if (terminal.length > 0) return terminal[terminal.length - 1]

  return values[values.length - 1]
}

export function useModelDownloadStatus(): {
  snapshot: ModelStatusSnapshot
  download: DownloadState
  downloads: Record<string, DownloadState>
  refresh: () => Promise<void>
} {
  const [snapshot, setSnapshot] = useState<ModelStatusSnapshot>(INITIAL_SNAPSHOT)
  const [downloads, setDownloads] = useState<Record<string, DownloadState>>({})
  const lastTerminalRef = useRef<Set<string>>(new Set())

  const refresh = useCallback(async () => {
    try {
      const report = await resourcesCheck()
      setSnapshot(summarize(report.resources))
    } catch (e) {
      console.warn('[useModelDownloadStatus] resources_check failed:', e)
    }
  }, [])

  useEffect(() => {
    void refresh()
    let cancelled = false
    let timer: ReturnType<typeof setInterval> | null = null

    const poll = async () => {
      if (cancelled) return
      try {
        const data = await httpGet<{
          resource_id: string
          status: string
          file: string
          file_progress: number
          file_index: number
          total_files: number
          error: string
        }>('/api/v1/models/download-status')
        if (cancelled) return
        const resourceId = data.resource_id
        if (!resourceId) return

        const next = toDownloadState(resourceId, data)
        setDownloads(prev => ({ ...prev, [resourceId]: next }))

        const isTerminal = data.status === 'completed' || data.status === 'failed'
        if (isTerminal && !lastTerminalRef.current.has(resourceId)) {
          lastTerminalRef.current.add(resourceId)
          void refresh()
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
  }, [refresh])

  const download = aggregateDownload(downloads)

  const effective: ModelStatusSnapshot = download.status === 'downloading' || download.status === 'connecting'
    ? { ...snapshot, status: 'downloading' as ModelStatus }
    : download.status === 'failed' && snapshot.status === 'ready'
      ? { ...snapshot, status: 'failed' as ModelStatus }
      : snapshot

  return { snapshot: effective, download, downloads, refresh }
}
