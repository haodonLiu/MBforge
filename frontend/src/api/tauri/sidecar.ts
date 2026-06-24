/** Sidecar-dependent commands.
 *
 * - `sidecarStatus` / `sidecarRestart`: sidecar process lifecycle.
 * - `environmentCheck`: probes Python via the sidecar HTTP API; lives here
 *   (not in `environment.ts`) because it requires the sidecar to be online.
 *   For a Rust-native env probe see `resourcesCheck` in `environment.ts`.
 */

import { invoke } from '@tauri-apps/api/core'
import { invokeWithError } from './_utils'
import { ErrorCode } from '../../utils/errors'

export interface SidecarStatus {
  healthy: boolean
  restartCount: number
  state: 'online' | 'offline'
  uptimeSecs: number
  lastError: string | null
}

/** Read sidecar health + restart count + uptime. */
export async function sidecarStatus(): Promise<SidecarStatus> {
  return invokeWithError(
    () => invoke<SidecarStatus>('sidecar_status'),
    ErrorCode.ApiError,
  )
}

/** Force-restart the Python sidecar (kills existing process + respawns). */
export async function sidecarRestart(): Promise<void> {
  await invokeWithError(
    () => invoke<{ success: boolean }>('sidecar_restart'),
    ErrorCode.ApiError,
  )
}

/** 探测 Python sidecar 环境信息（Python 版本、GPU、CUDA、库依赖）。 */
export async function environmentCheck(): Promise<unknown> {
  return invokeWithError(
    () => invoke<unknown>('environment_check'),
    ErrorCode.ApiError,
  )
}
