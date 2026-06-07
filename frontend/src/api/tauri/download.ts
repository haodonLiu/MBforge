/** 模型下载 — Tauri 原生（替代 Python sidecar HTTP 端点） */

import { invoke } from '@tauri-apps/api/core'
import { listen, type UnlistenFn } from '@tauri-apps/api/event'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface DownloadProgress {
  status: string       // "connecting" | "downloading" | "completed" | "failed"
  file: string
  file_progress: number
  file_index: number
  total_files: number
  error: string
}

/**
 * 下载模型（Rust 原生，通过 Tauri 事件推送进度）
 *
 * @param resourceId - 资源 ID（如 "embedding", "molscribe"）
 * @param onProgress - 进度回调
 * @returns 取消函数
 */
export function downloadModelTauri(
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
