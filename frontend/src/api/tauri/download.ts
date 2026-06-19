/** 模型下载 — Tauri 原生（替代 Python sidecar HTTP 端点） */

import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'
import { EVT } from '../tauri-events'

export interface SubfileStatus {
  label: string          // 友好标签，如 "doc" / "general"
  relpath: string        // 相对仓库根路径
  local_path: string     // 完整本地路径
  ready: boolean
  size_mb: number
}

export interface DownloadModel {
  id: string
  name: string
  type: string
  description: string
  ms_repo: string
  downloaded: boolean
  downloading: boolean
  local_path: string
  /** 期望路径（模型应该被检测到的位置）。download 按钮用它提示用户。 */
  expected_path: string
  license: string
  license_url: string
  size_mb: number
  source_url: string
  /** 多文件资源（如 MolDetv2）的逐文件状态。空数组 = 单文件资源。 */
  subfiles: SubfileStatus[]
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
  resource_id: string  // 模型/资源 ID，区分同时下载的多个模型
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
  if (id === 'moldet' || id === 'moldet_coref' || id === 'molscribe') return 'detection'
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
      // 只展示模型；Python 包 (torch/transformers/...) 属于依赖，状态由 System 页展示
      if (String(item.type ?? '') !== 'model') continue
      const status = await invokeWithError(
        () => invoke<{
          status: string
          local_path: string
          size_mb: number
          expected_path: string
          subfiles: { label: string; relpath: string; local_path: string; ready: boolean; size_mb: number }[]
        }>('resources_status', { resourceId: id }),
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
        expected_path: status.expected_path ?? '',
        license: String(item.license ?? ''),
        license_url: '',
        size_mb: Number(item.size_mb ?? 0),
        source_url: '',
        subfiles: status.subfiles ?? [],
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
  let aborted = false
  const logPrefix = `[downloadModel ${resourceId}]`
  console.log(`${logPrefix} starting, registering listener...`)

  const start = async () => {
    try {
      unlisten = await listen<DownloadProgress>(EVT.ModelDownloadProgress, (event) => {
        if (event.payload.resource_id !== resourceId) {
          // 忽略其他模型的进度事件
          return
        }
        console.log(`${logPrefix} received progress event:`, event.payload)
        onProgress(event.payload)
      })
      console.log(`${logPrefix} listener registered`)
      if (aborted) {
        unlisten()
        return
      }

      console.log(`${logPrefix} invoking models_download...`)
      const path = await invokeWithError(
        () => invoke<string>('models_download', { resourceId }),
        ErrorCode.ApiError,
      )
      console.log(`${logPrefix} models_download returned:`, path)
    } catch (err) {
      if (aborted) return
      console.error(`${logPrefix} failed:`, err)
      onProgress({
        resource_id: resourceId,
        status: 'failed',
        file: '',
        file_progress: 0,
        file_index: 0,
        total_files: 0,
        error: String(err),
      })
    }
  }
  void start()

  // 返回取消函数
  return () => {
    console.log(`${logPrefix} cleanup called`)
    aborted = true
    unlisten?.()
    invoke('models_cancel_download', { resourceId }).catch((e) => console.warn('cancel download failed:', e))
  }
}

/** 删除已下载的模型 */
export async function deleteModel(resourceId: string): Promise<void> {
  await invokeWithError(
    () => invoke<void>('models_delete', { resourceId }),
    ErrorCode.ApiError,
  )
}

/** 下载多文件资源中的单个子文件 */
export function downloadModelSubfile(
  resourceId: string,
  subpath: string,
  onProgress: (event: DownloadProgress) => void,
): () => void {
  let unlisten: UnlistenFn | null = null
  let aborted = false

  const start = async () => {
    try {
      unlisten = await listen<DownloadProgress>(EVT.ModelDownloadProgress, (event) => {
        if (event.payload.resource_id !== resourceId) return
        onProgress(event.payload)
      })
      if (aborted) {
        unlisten()
        return
      }
      await invokeWithError(
        () => invoke<string>('models_download_subfile', { resourceId, subpath }),
        ErrorCode.ApiError,
      )
    } catch (err) {
      if (aborted) return
      onProgress({
        resource_id: resourceId,
        status: 'failed',
        file: subpath,
        file_progress: 0,
        file_index: 0,
        total_files: 0,
        error: String(err),
      })
    }
  }
  void start()

  return () => {
    aborted = true
    unlisten?.()
    invoke('models_cancel_download', { resourceId }).catch((e) => console.warn('cancel download failed:', e))
  }
}

/** 删除多文件资源中的单个子文件 */
export async function deleteModelSubfile(resourceId: string, subpath: string): Promise<void> {
  await invokeWithError(
    () => invoke<void>('models_delete_subfile', { resourceId, subpath }),
    ErrorCode.ApiError,
  )
}

/** 测试模型：实际加载到内存 + 最小推理。返回 {ok, error, duration_ms} */
export interface ModelTestResult {
  ok: boolean
  error: string
  duration_ms: number
}

export async function testModel(
  resourceId: string,
  subpath?: string,
): Promise<ModelTestResult> {
  return invokeWithError(
    () => invoke<ModelTestResult>('models_test', { resourceId, subpath }),
    ErrorCode.ApiError,
  )
}
