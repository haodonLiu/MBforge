/** Global model download status + resources sync. */
import { useEffect, useState, useCallback } from 'react'
import { listen } from '@tauri-apps/api/event'
import { resourcesCheck, type ResourceStatusItem } from '../api/tauri/environment'

export type ModelStatus = 'ready' | 'downloading' | 'missing' | 'failed' | 'unknown'

export interface DownloadState {
  status: 'idle' | 'connecting' | 'downloading' | 'completed' | 'failed'
  file: string
  fileProgress: number
  fileIndex: number
  totalFiles: number
  error: string
}

export interface ModelStatusSnapshot {
  /** 'ready' = all present, 'missing' = at least one NotFound, 'unknown' = not yet checked */
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

/**
 * 单一 hook：返回当前模型资源状态 + 当前进行中的下载状态。
 * - 启动时拉一次 `resources_check` 计算初始状态
 * - 监听 `model-download-progress` 事件更新下载态
 * - 下载完成/失败后刷新资源状态
 */
export function useModelDownloadStatus(): {
  snapshot: ModelStatusSnapshot
  download: DownloadState
  refresh: () => Promise<void>
} {
  const [snapshot, setSnapshot] = useState<ModelStatusSnapshot>(INITIAL_SNAPSHOT)
  const [download, setDownload] = useState<DownloadState>(INITIAL_DOWNLOAD)

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
    let unlisten: (() => void) | null = null
    const setup = async () => {
      unlisten = await listen<{
        status: string
        file: string
        file_progress: number
        file_index: number
        total_files: number
        error: string
      }>('model-download-progress', (event) => {
        const p = event.payload
        setDownload({
          status: p.status as DownloadState['status'],
          file: p.file,
          fileProgress: p.file_progress,
          fileIndex: p.file_index,
          totalFiles: p.total_files,
          error: p.error,
        })
        if (p.status === 'completed' || p.status === 'failed') {
          // 重新拉一次资源状态
          void refresh()
        }
      })
    }
    void setup().catch(e => {
      console.error('[useModelDownloadStatus] listen failed:', e)
    })
    return () => {
      unlisten?.()
    }
  }, [refresh])

  // 下载中状态覆盖 missing/ready
  const effective: ModelStatusSnapshot = download.status === 'downloading' || download.status === 'connecting'
    ? { ...snapshot, status: 'downloading' as ModelStatus }
    : download.status === 'failed' && snapshot.status === 'ready'
      ? { ...snapshot, status: 'failed' as ModelStatus }
      : snapshot

  return { snapshot: effective, download, refresh }
}
