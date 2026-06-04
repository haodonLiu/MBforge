/** Listen to sidecar lifecycle events (logs + health status).
 *
 * These events are emitted from Rust (`src-tauri/src/sidecar.rs`) and
 * provide real-time visibility into the Python sidecar process.
 */

import { useEffect } from 'react'
import { listen } from '@tauri-apps/api/event'
import { EVT } from '../api/tauri-events'

export interface SidecarLogEvent {
  stream: 'stdout' | 'stderr'
  line: string
  timestamp: number
}

export interface SidecarStatusEvent {
  healthy: boolean
  restartCount: number
  state: 'online' | 'offline'
  uptimeSecs: number
  lastError: string | null
}

export function useSidecarEvents() {
  useEffect(() => {
    let unlistenLog: (() => void) | null = null
    let unlistenStatus: (() => void) | null = null

    const setup = async () => {
      unlistenLog = await listen<SidecarLogEvent>(EVT.SidecarLog, (event) => {
        const { stream, line } = event.payload
        if (stream === 'stderr') {
          console.warn('[sidecar stderr]', line)
        } else {
          console.log('[sidecar stdout]', line)
        }
      })

      unlistenStatus = await listen<SidecarStatusEvent>(EVT.SidecarStatus, (event) => {
        const { state, healthy, restartCount, uptimeSecs, lastError } = event.payload
        console.log(
          `[sidecar status] state=${state} healthy=${healthy} restarts=${restartCount} uptime=${uptimeSecs}s`,
          lastError ? `error=${lastError}` : '',
        )
      })
    }

    setup().catch(console.error)

    return () => {
      unlistenLog?.()
      unlistenStatus?.()
    }
  }, [])
}
