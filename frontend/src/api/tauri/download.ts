/** 模型下载 — Tauri 原生（替代 Python sidecar HTTP 端点） */

import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface DownloadModel {
  id: string
  name: string
  type: string
  description: string
  ms_repo: string
  downloaded: boolean
  downloading: boolean
  local_path: string
  license: string
  license_url: string
  size_mb: number
  source_url: string
}

export interface DownloadedModel {
  id: string
  name: string
  path: string
  size_mb: number
  type: string
  in_catalog: boolean
}

export interface DownloadProgress {
  status: string       // "connecting" | "downloading" | "completed" | "failed"
  file: string
  file_progress: number
  file_index: number
  total_files: number
  error: string
}

/** 根据资源 ID 推断前端展示用的模型类别（与 ModelsTab typeLabels 对齐）。 */
function inferModelType(id: string): string {
  if (id === 'embedding') return 'embedding'
  if (id === 'reranker') return 'reranker'
  if (id === 'moldet' || id === 'molscribe') return 'detection'
  return 'model'
}

/**
 * 列出所有可用模型（catalog + 实时状态）。
 * 内部组合 `resources_catalog` 与 `resources_status`。
 */
export async function listModels(): Promise<{ success: boolean; models: DownloadModel[]; error?: string }> {
  try {
    const catalog = await invoke<Record<string, unknown>[]>('resources_catalog')
    const models: DownloadModel[] = []
    for (const item of catalog) {
      const id = String(item.id ?? '')
      if (!id) continue
      const status = await invokeWithError(
        () => invoke<{ status: string; local_path: string; size_mb: number }>('resources_status', { resourceId: id }),
        ErrorCode.ApiError,
      )
      models.push({
        id,
        name: String(item.name ?? id),
        type: inferModelType(id),
        description: String(item.description ?? ''),
        ms_repo: String(item.ms_repo ?? ''),
        downloaded: status.status === 'ready',
        downloading: false,
        local_path: status.local_path ?? '',
        license: String(item.license ?? ''),
        license_url: '',
        size_mb: Number(item.size_mb ?? 0),
        source_url: '',
      })
    }
    return { success: true, models }
  } catch (e) {
    return { success: false, models: [], error: String(e) }
  }
}

/**
 * 列出已下载模型。
 * 基于 catalog 过滤出状态为 ready 的条目。
 */
export async function listDownloaded(): Promise<{ success: boolean; models: DownloadedModel[]; model_dir: string; error?: string }> {
  try {
    const catalog = await invoke<Record<string, unknown>[]>('resources_catalog')
    const models: DownloadedModel[] = []
    for (const item of catalog) {
      const id = String(item.id ?? '')
      if (!id) continue
      const status = await invokeWithError(
        () => invoke<{ status: string; local_path: string; size_mb: number }>('resources_status', { resourceId: id }),
        ErrorCode.ApiError,
      )
      if (status.status === 'ready') {
        models.push({
          id,
          name: String(item.name ?? id),
          path: status.local_path ?? '',
          size_mb: status.size_mb ?? 0,
          type: inferModelType(id),
          in_catalog: true,
        })
      }
    }
    const dirInfo = await invoke<{ mbforge: { path: string } }>('models_cache_dir_info')
    return { success: true, models, model_dir: dirInfo.mbforge?.path ?? '' }
  } catch (e) {
    return { success: false, models: [], model_dir: '', error: String(e) }
  }
}

/**
 * 下载模型（Rust 原生，通过 Tauri 事件推送进度）
 *
 * @param resourceId - 资源 ID（如 "embedding", "molscribe"）
 * @param onProgress - 进度回调
 * @returns 取消函数
 */
export function downloadModel(
  resourceId: string,
  onProgress: (event: DownloadProgress) => void,
): () => void {
  let unlisten: UnlistenFn | null = null

  // 监听进度事件
  listen<DownloadProgress>('model-download-progress', (event) => {
    onProgress(event.payload)
  }).then((unlistenFn) => {
    unlisten = unlistenFn
  })

  // 发起下载
  invokeWithError(
    () => invoke<string>('models_download', { resourceId }),
    ErrorCode.ApiError,
  ).catch((err) => {
    onProgress({
      status: 'failed',
      file: '',
      file_progress: 0,
      file_index: 0,
      total_files: 0,
      error: String(err),
    })
  })

  // 返回取消函数
  return () => {
    unlisten?.()
    invoke('models_cancel_download', { resourceId }).catch(() => {})
  }
}

/** 删除已下载的模型 */
export async function deleteModel(resourceId: string): Promise<void> {
  await invokeWithError(
    () => invoke<void>('models_delete', { resourceId }),
    ErrorCode.ApiError,
  )
}
