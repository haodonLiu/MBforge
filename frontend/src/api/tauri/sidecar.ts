/** Sidecar lifecycle — health probe + manual restart. */

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
