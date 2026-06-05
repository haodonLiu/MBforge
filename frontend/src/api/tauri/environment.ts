/** Resource manager — environment check, model paths, catalog. */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface ResourceStatusItem {
  id: string
  name: string
  type: string
  status: string
  local_path: string
  size_mb: number
  version: string
  error: string
}

export interface EnvironmentReport {
  python_version: string
  gpu_available: boolean
  gpu_name: string
  cuda_version: string
  summary: string
  resources: ResourceStatusItem[]
}

/** 全量环境检查（Rust native，不依赖 Python sidecar） */
export async function resourcesCheck(): Promise<EnvironmentReport> {
  return invokeWithError(
    () => invoke<EnvironmentReport>('resources_check'),
    ErrorCode.ApiError,
  )
}

/** 检查单个资源状态 */
export async function resourcesStatus(resourceId: string): Promise<ResourceStatusItem> {
  return invokeWithError(
    () => invoke<ResourceStatusItem>('resources_status', { resource_id: resourceId }),
    ErrorCode.ApiError,
  )
}

/** 获取已下载模型的本地路径 */
export async function resourcesGetModelPath(resourceId: string): Promise<string | null> {
  return invokeWithError(
    () => invoke<string | null>('resources_get_model_path', { resource_id: resourceId }),
    ErrorCode.ApiError,
  )
}

/** 获取资源目录（纯元数据） */
export async function resourcesCatalog(): Promise<Record<string, unknown>[]> {
  return invoke<Record<string, unknown>[]>('resources_catalog')
}
